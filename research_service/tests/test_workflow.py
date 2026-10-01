from dataclasses import asdict
from datetime import date, timedelta
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import zipfile

from fastapi.testclient import TestClient
from jsonschema import ValidationError as JsonSchemaValidationError

from research_service.app import create_app
from research_service.data import validate_dataset, research_inputs, digest, score_sentiment_finbert
from research_service.engine import Engine, compute_usage, gate, derive_action, source_locked_fundamental
from research_service.models import messages_for, output_schema_for
from research_service.protocol import StudyProtocol, decision_plan
from research_service.reporting import export_job, study_report, pilot_diagnostics, hold_band_sensitivity
from research_service.storage import Store


def fixture():
    rows = []
    start = date(2024, 1, 1)
    for i in range(560):
        day = start + timedelta(days=i)
        if day.weekday() > 4:
            continue
        value = 100 + i * .05 + (i % 7) * .1
        rows.append({"date": day.isoformat(), "open": value, "high": value + 1, "low": value - 1, "close": value + .1})
    evidence = [{"evidence_id": domain + "-1", "domain": domain,
        "claim": "NVIDIA synthetic test evidence only" if domain == "sentiment" else "Synthetic test evidence only",
        "source": "unit-test-fixture", "available_at": "2024-12-20", **({"vintage_date": "2024-12-20"} if domain == "macro" else {}),
        **({"headline": "NVIDIA synthetic test evidence only", "sentiment_score": .2} if domain == "sentiment" else {})}
        for domain in ("fundamental", "sentiment", "macro")]
    # Three direct headlines: a kind with fewer than three scored headlines reports no sentiment indicator.
    evidence = evidence + [{**item, "evidence_id": f"sentiment-{number}"} for number in (2, 3)
                           for item in evidence if item["domain"] == "sentiment"]
    return {"ticker": "NVDA", "kind": "synthetic", "source": "unit-test-fixture", "price_basis": "adjusted_ohlc", "prices": rows, "evidence": evidence}


def fake_model(protocol, messages):
    if "neutral research agent" in messages[0]["content"]:
        items = json.loads(messages[1]["content"].split("Evidence: ")[1])
        result = {"summary": "Synthetic model fixture, not research performance", "evidence_ids": [items[0]["evidence_id"]], "risks": ["test"]}
    else:
        items = json.loads(messages[1]["content"])["report"]["evidence"]
        action = "Sell" if "action MUST be Sell" in messages[0]["content"] else "Buy"
        result = {"action": action, "expected_return_pct": -5.0 if action == "Sell" else 5.0,
                  "confidence": .8, "rationale": "Synthetic test decision",
                  "evidence_ids": [items[0]["evidence_id"]], "risks": ["test"]}
        if "assigned debate stance" in messages[0]["content"]:
            result["strongest_counterpoint"] = "Synthetic counterpoint supported by the shared evidence."
        if "role-switch round" in messages[0]["content"]:
            result["rebutted_claim"] = "Synthetic test decision"  # this agent's own round-1 rationale
            result["confidence_shift"] = 0.0
    return result, {"prompt_hash": digest(messages), "usage": {}, "raw_response": json.dumps(result)}


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(self.tmp.name)
        self.data = validate_dataset(fixture())
        self.dataset_id = self.store.add_dataset(self.data)
        self.protocol = StudyProtocol(dataset_kind="synthetic", bootstrap_replicates=199)

    def tearDown(self):
        self.tmp.cleanup()

    def create(self, analysis_date="2024-12-31"):
        return self.store.create({"ticker": "NVDA", "analysis_date": analysis_date, "dataset_id": self.dataset_id,
            "protocol": asdict(self.protocol), "protocol_hash": self.protocol.fingerprint})

    def complete(self, job):
        engine = Engine(self.store, fake_model)
        for _ in range(40):
            state = engine.advance(job)
            self.store.save_step(job["id"], state)
            job = self.store.get(job["id"])
            if job["status"] == "complete":
                return job
        self.fail("Workflow did not complete")

    def test_full_workflow_independence_exports_and_real_calculations(self):
        job = self.complete(self.create())
        state = job["state"]
        self.assertEqual(len(state["records"]), 22)
        self.assertEqual(len(state["cases"]), 48)
        self.assertTrue(all(row["status"] == "complete" for row in state["cases"]))
        hashes = {r["audit"]["prompt_hash"] for r in state["records"] if r["group"] in "AB"}
        self.assertEqual(len(hashes), 1)
        self.assertEqual(len({r["audit"]["seed"] for r in state["records"] if r["group"] == "B"}), 7)
        self.assertEqual({r["report_hash"] for r in state["records"]}, {state["report_hash"]})
        self.assertNotIn("decisions", state["report"])
        self.assertEqual([r["stance"] for r in state["records"] if r["group"] == "D" and r["round"]], ["BULL","BEAR","BEAR","BULL","BULL","BEAR"])
        study = study_report([job], formal_only=False)
        export = export_job(job, study)
        self.assertEqual(export_job(job, study), export)
        with zipfile.ZipFile(io.BytesIO(export)) as archive:
            self.assertIn("state_trace.json", archive.namelist())
            self.assertIn("summary.csv", archive.namelist())
            self.assertIn("statistics.json", archive.namelist())
            self.assertIn("completeness_diagnostic.json", archive.namelist())
            self.assertIn("manifest.json", archive.namelist())
            self.assertIn("net_return", archive.read("cases.csv").decode())
            manifest = json.loads(archive.read("manifest.json"))
            self.assertEqual(manifest["schema"], "stance-shift-export/v1")
            self.assertEqual(manifest["job"]["id"], job["id"])
            # The numeric/ML stack decides the reported figures, so it belongs
            # in the audit trail next to the protocol and model identity.
            environment = manifest["runtime_environment"]
            self.assertTrue(environment["python"])
            for package in ("numpy", "scipy", "transformers"):
                self.assertIn(package, environment["packages"])
            self.assertTrue(environment["packages"]["numpy"])
            for item in manifest["files"]:
                payload = archive.read(item["path"])
                self.assertEqual(len(payload), item["bytes"])
                self.assertEqual(hashlib.sha256(payload).hexdigest(), item["sha256"])
        report = study
        self.assertEqual(report["status"], "insufficient_cases")
        self.assertEqual(report["comparisons"], [])
        self.assertEqual(report["unique_cases"], 1)
        self.assertTrue(any(row["decision_layer"] == "candidate" for row in report["summary"]))

    def test_future_evidence_and_prices_do_not_reach_report(self):
        future = {"evidence_id":"future", "domain":"sentiment", "claim":"future leak", "source":"test", "available_at":"2025-01-01"}
        self.data["evidence"].append(future)
        first = research_inputs(self.data,"2024-12-31")
        self.assertNotIn("future", [e["evidence_id"] for e in first["evidence"]])
        for row in self.data["prices"]:
            if row["date"] >= "2024-12-31":
                row["close"] *= 100
        self.assertEqual(first, research_inputs(self.data,"2024-12-31"))

    def test_sentiment_prompt_is_bounded_and_selection_is_audited(self):
        self.data["evidence"].extend({"evidence_id":f"news-{i:02d}", "domain":"sentiment",
            "claim":"x" * 2000, "source":"test", "available_at":f"2024-12-{i + 1:02d}"}
            for i in range(20))
        inputs = research_inputs(self.data, "2024-12-31")
        self.assertEqual(len(inputs["domains"]["sentiment"]), 12)
        self.assertEqual(inputs["evidence_selection"]["sentiment"]["available"], 23)  # 3 fixture headlines + 20
        self.assertTrue(all(len(item["claim"]) <= 1200 for item in inputs["domains"]["sentiment"]))

    def test_recovery_releases_only_jobs_of_stopped_services(self):
        live, dead = self.create("2024-12-31"), self.create("2025-03-31")
        self.store.heartbeat("live")
        self.assertEqual(self.store.claim("worker:live")["id"], live["id"])
        self.assertEqual(self.store.claim("worker:dead")["id"], dead["id"])
        from datetime import datetime, timedelta, timezone
        now = datetime.now(timezone.utc)
        released = self.store.recover((now - timedelta(seconds=90)).isoformat(), (now - timedelta(minutes=30)).isoformat())
        self.assertEqual(released, 1)
        self.assertEqual(self.store.get(live["id"])["status"], "running")
        self.assertEqual(self.store.get(dead["id"])["status"], "paused")
        with TestClient(create_app(self.store, fake_model, start_worker=False)):
            self.assertEqual(self.store.get(live["id"])["status"], "running")  # a second service starts

    def test_restart_and_cancel_do_not_duplicate_or_resurrect(self):
        job = self.create()
        claimed = self.store.claim()
        state = Engine(self.store, fake_model).advance(claimed)
        self.store.save_step(job["id"], state)
        self.store.claim()
        self.store.recover("9999", "9999")  # its service has stopped
        recovered = self.store.get(job["id"])
        self.assertEqual(recovered["status"], "paused")
        self.assertEqual(len(recovered["state"]["trace"]), 1)
        self.store.control(job["id"], "cancel")
        self.store.save_step(job["id"], state)
        self.assertEqual(self.store.get(job["id"])["status"], "cancelled")

    def test_missing_data_forces_no_trade(self):
        self.data["evidence"] = []
        self.dataset_id = self.store.add_dataset(self.data)
        self.protocol = StudyProtocol(dataset_kind="synthetic", bootstrap_replicates=199,
                                      missing_data_policy="force_no_trade")
        job = self.complete(self.create())
        self.assertTrue(all(d["action"] == "NoTrade" for d in job["state"]["decisions"].values()))
        self.assertTrue(all(d["gate"]["missing_data_policy"] == "force_no_trade"
                            for d in job["state"]["decisions"].values()))

    def test_missing_data_control_preserves_model_decisions(self):
        self.data["evidence"] = []
        self.dataset_id = self.store.add_dataset(self.data)
        self.protocol = StudyProtocol(dataset_kind="synthetic", bootstrap_replicates=199,
                                      missing_data_policy="allow_decision")
        job = self.complete(self.create())
        self.assertTrue(all(d["action"] == "Buy" for d in job["state"]["decisions"].values()))
        self.assertTrue(all(d["gate"]["missing_data_control"] for d in job["state"]["decisions"].values()))

    def test_missing_sentiment_domain_is_not_blocked_by_news_quality_gate(self):
        historical = json.loads(json.dumps(self.data))
        historical.update(kind="historical", collection_rules={"news_item_limit": "uncapped"}, requested_analysis_date="2024-12-31", evidence=[])
        dataset_id = self.store.add_dataset(historical)
        with TestClient(create_app(self.store, fake_model, start_worker=False)) as client:
            response = client.post('/api/jobs', json={"dataset_id": dataset_id,
                "analysis_date": "2024-12-31", "model": "openrouter/test"})
        self.assertEqual(response.status_code, 200)

    def test_point_only_fundamental_requires_an_explicit_sensitivity_override(self):
        historical = json.loads(json.dumps(self.data))
        historical.update(kind="historical", collection_rules={"news_item_limit": "uncapped"}, requested_analysis_date="2024-12-31")
        historical["evidence"] = [item for item in historical["evidence"] if item["domain"] == "fundamental"]
        dataset_id = self.store.add_dataset(historical)
        with TestClient(create_app(self.store, fake_model, start_worker=False)) as client:
            rejected = client.post('/api/jobs', json={"dataset_id": dataset_id,
                "analysis_date": "2024-12-31", "model": "openrouter/test"})
            allowed = client.post('/api/jobs', json={"dataset_id": dataset_id,
                "analysis_date": "2024-12-31", "model": "openrouter/test",
                "allow_point_fundamental": True})
        self.assertEqual(rejected.status_code, 422)
        self.assertIn("SEC 點時欄位", rejected.json()["detail"])
        self.assertEqual(allowed.status_code, 200)
        self.assertTrue(allowed.json()["config"]["quality_overrides"]["allow_point_fundamental"])

    def test_compute_usage_uses_client_elapsed_time_not_provider_duration(self):
        records = [{"group": "A", "audit": {"usage": {"prompt_tokens": 10,
                    "completion_tokens": 4, "client_elapsed_seconds": 1.25,
                    "total_duration": 15_000_000_000_000}}}]
        usage = compute_usage(records)["A"]
        self.assertEqual(usage["wall_seconds"], 1.25)
        self.assertEqual(usage["duration_source"], "client_monotonic")

    def test_low_historical_accuracy_warns_without_self_locking(self):
        candidate = {"action":"Buy", "expected_return_pct":5., "confidence":.8, "rationale":"test", "evidence_ids":["e1"],
                     "invalid_evidence_ids":[], "risks":[]}
        inputs = {"domains":{domain:[{"evidence_id":"e1"}] for domain in ("technical","fundamental","sentiment","macro")},
                  "volatility":.2}
        result = gate(candidate, inputs, [{"correct":False} for _ in range(5)], StudyProtocol(dataset_kind="synthetic", bootstrap_replicates=199))
        self.assertEqual(result["action"], "Buy")
        self.assertIn("historical_accuracy_below_0.50", result["gate"]["reasons"])
        self.assertEqual(result["gate"]["history_status"], "warning_only_recovery_enabled")

    def test_historical_insufficient_base_rate_history_forces_no_trade(self):
        candidate = {"action":"Buy", "expected_return_pct":5., "confidence":.8, "rationale":"test", "evidence_ids":["e1"],
                     "invalid_evidence_ids":[], "risks":[]}
        inputs = {"domains":{domain:[{"evidence_id":"e1"}] for domain in ("technical","fundamental","sentiment","macro")},
                  "volatility":.2,
                  "base_rates":{"basis":"insufficient_history", "calibration_ready":False,
                                 "windows":4, "windows_required":8}}
        result = gate(candidate, inputs, [], StudyProtocol(dataset_kind="historical", bootstrap_replicates=199))
        self.assertEqual(result["action"], "NoTrade")
        self.assertEqual(result["candidate_action"], "Buy")
        self.assertIn("insufficient_base_rate_history", result["gate"]["reasons"])
        self.assertTrue(result["gate"]["calibration_control"])

    def test_memory_respects_maturity_protocol_and_group(self):
        job = self.complete(self.create())
        config = dict(job["config"], analysis_date="2025-01-01")
        self.assertEqual(self.store.memory(config,"D"), [])
        config["analysis_date"] = "2025-06-30"
        result = self.store.memory(config,"D")
        self.assertEqual(len(result),1)
        self.assertEqual(result[0]["group"],"D")
        config["protocol_hash"] = "other"
        self.assertEqual(self.store.memory(config,"D"), [])

    def test_api_security_validation_and_persistence(self):
        with TestClient(create_app(self.store, fake_model, start_worker=False)) as client:
            self.assertEqual(client.get('/health').status_code,200)
            home = client.get('/').text
            self.assertIn('研究分析日（季末或今天）', home)
            self.assertIn('準備研究資料', home)
            self.assertIn('id="agent-terminal-output"', home)
            self.assertIn('id="refresh-data"', home)
            self.assertIn('實驗對照 · 保留模型決策', home)
            self.assertIn('id="run-button" disabled', home)
            self.assertIn('id="cloud-model"', home)
            frontend = ''.join(client.get(f'/assets/js/{name}').text for name in
                               ('app.js', 'data-panel.js', 'experiment-panel.js', 'runs-panel.js', 'ui.js'))
            self.assertIn('A/B/C/D 實驗執行', frontend)
            self.assertIn('collect --ticker', frontend)
            self.assertIn('舊版結果', frontend)
            self.assertIn('只供 30／60／90 日回測，不能選為分析日', frontend)
            self.assertEqual(client.get('/assets/js/..%2Fapp.py').status_code, 404)
            self.assertEqual(client.get('/assets/js/missing.js').status_code, 404)
            self.assertEqual(client.get('/assets/dataset.css').status_code, 200)
            self.assertEqual(client.get('/',headers={"host":"evil.example"}).status_code,403)
            self.assertEqual(client.post('/api/jobs',headers={"origin":"https://evil.example"},json={}).status_code,403)
            # A forwarding proxy may present an allowed host under another scheme/port.
            self.assertNotEqual(client.post('/api/jobs',headers={"origin":"https://localhost:8000"},json={}).status_code,403)
            response=client.post('/api/jobs',json={"dataset_id":self.dataset_id,"analysis_date":"2024-12-31"})
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.json()["config"]["protocol"]["missing_data_policy"], "allow_decision")
            self.assertEqual(client.get('/api/jobs').json()[0]['id'],response.json()['id'])
            dashboard = client.get('/api/dashboard', params={"selected":response.json()["id"]}).json()
            self.assertEqual(dashboard["jobs"][0]["id"], response.json()["id"])
            self.assertEqual(dashboard["selected"]["id"], response.json()["id"])
            cloud = client.post('/api/jobs',json={"dataset_id":self.dataset_id,"analysis_date":"2024-12-31",
                                                  "model":"openrouter/openai/gpt-4.1-mini"})
            self.assertEqual(cloud.json()["config"]["protocol"]["model"], "openrouter/openai/gpt-4.1-mini")
            self.assertEqual(client.post('/api/jobs',json={"dataset_id":"","analysis_date":"2024-12-31"}).status_code,422)
            self.assertEqual(client.post('/api/jobs',json={"dataset_id":self.dataset_id,"analysis_date":"2024-12-30"}).status_code,422)
        with patch.dict(os.environ,{"RESEARCH_ACCESS_KEY":"a"*32}):
            with TestClient(create_app(self.store,start_worker=False)) as client:
                self.assertEqual(client.get('/api/jobs').status_code,401)
                self.assertEqual(client.get('/assets/dataset.css').status_code,200)
                self.assertEqual(client.get('/assets/js/app.js').status_code,200)
                login = client.post('/api/login',json={"key":"a"*32})
                self.assertEqual(login.status_code,200)
                self.assertNotEqual(login.cookies.get('research_session'), "a"*32)
                self.assertEqual(client.get('/api/jobs').status_code,200)

    def test_api_docs_and_compact_job_detail_contract(self):
        job = self.create()
        with TestClient(create_app(self.store, fake_model, start_worker=False)) as client:
            self.assertEqual(client.get('/docs').status_code, 200)
            self.assertEqual(client.get('/redoc').status_code, 200)
            self.assertEqual(client.get('/openapi.json').status_code, 200)
            compact = client.get(f'/api/jobs/{job["id"]}')
            detailed = client.get(f'/api/jobs/{job["id"]}?detail=true')
        self.assertEqual(compact.status_code, 200)
        self.assertIn("state_summary", compact.json())
        self.assertNotIn("state", compact.json())
        self.assertIn("state", detailed.json())

    def test_resume_clears_stale_provider_error(self):
        job = self.create()
        state = {"records": [], "research": {}, "trace": [], "attempts": []}
        self.store.save_step(job["id"], state, "provider failed")
        self.assertEqual(self.store.get(job["id"])["status"], "paused")
        self.store.control(job["id"], "resume")
        resumed = self.store.get(job["id"])
        self.assertEqual(resumed["error"], "")
        self.assertEqual((resumed["status"], resumed["wants_run"]), ("queued", 1))

    def test_local_model_error_message_does_not_claim_gpu_tw(self):
        with patch.dict(os.environ, {"GPUTW_OLLAMA_BASE_URL": "",
                                     "OLLAMA_BASE_URL": "http://127.0.0.1:11434"}, clear=False), \
             patch("research_service.web.ollama.get_json", side_effect=OSError("offline")):
            with TestClient(create_app(self.store, fake_model, start_worker=False)) as client:
                result = client.get('/api/models').json()
        self.assertIn("本機 Ollama", result["message"])
        self.assertNotIn("GPUtw 執行個體", result["message"])

    def test_legacy_clone_records_required_migration_overrides(self):
        old_protocol = asdict(self.protocol)
        old_protocol.update(version="v3-0908.2", model="ollama/gemma3:4b", allow_small_model=False)
        legacy = self.store.create({"ticker": "NVDA", "analysis_date": "2024-12-31",
                                    "dataset_id": self.dataset_id, "protocol": old_protocol,
                                    "protocol_hash": "legacy-protocol-hash"})
        with TestClient(create_app(self.store, fake_model, start_worker=False)) as client:
            response = client.post(f'/api/jobs/{legacy["id"]}/clone')
        self.assertEqual(response.status_code, 200)
        cloned = response.json()
        self.assertEqual(cloned["config"]["parent_job_id"], legacy["id"])
        self.assertEqual(cloned["config"]["protocol"]["version"], StudyProtocol().version)
        self.assertTrue(cloned["config"]["protocol"]["allow_small_model"])
        self.assertEqual(cloned["config"]["migration"]["from_protocol_version"], "v3-0908.2")

    def test_ollama_metadata_closes_an_unnamed_small_model_loophole(self):
        tags = {"models": [{"name": "gemma4:latest", "digest": "demo", "size": 1,
                             "details": {"parameter_size": "8.0B", "context_length": 4096}}]}
        with patch("research_service.web.ollama.get_json", return_value=tags):
            with TestClient(create_app(self.store, start_worker=False)) as client:
                rejected = client.post('/api/jobs', json={"dataset_id": self.dataset_id,
                    "analysis_date": "2024-12-31", "model": "ollama/gemma4:latest"})
                permitted = client.post('/api/jobs', json={"dataset_id": self.dataset_id,
                    "analysis_date": "2024-12-31", "model": "ollama/gemma4:latest", "allow_small_model": True})
        self.assertEqual(rejected.status_code, 422)
        self.assertIn("正式門檻", rejected.json()["detail"])
        self.assertIn("qwen3:8b", rejected.json()["detail"])
        self.assertEqual(permitted.status_code, 200)
        self.assertEqual(permitted.json()["config"]["model_identity"]["parameter_size"], "8.0B")

    def test_qwen3_8b_is_the_only_formal_small_model_exception(self):
        tags = {"models": [
            {"name": "qwen3:8b", "digest": "qwen8b-digest", "size": 1,
             "details": {"parameter_size": "8.2B", "context_length": 8192}},
            {"name": "gemma3:4b", "digest": "gemma4b-digest", "size": 1,
             "details": {"parameter_size": "4.3B", "context_length": 8192}},
        ]}
        with patch("research_service.web.ollama.get_json", return_value=tags):
            with TestClient(create_app(self.store, start_worker=False)) as client:
                model_listing = client.get('/api/models').json()
                permitted = client.post('/api/jobs', json={"dataset_id": self.dataset_id,
                    "analysis_date": "2024-12-31", "model": "ollama/qwen3:8b"})
                rejected = client.post('/api/jobs', json={"dataset_id": self.dataset_id,
                    "analysis_date": "2024-12-31", "model": "ollama/gemma3:4b"})
        self.assertIn("ollama/qwen3:8b", model_listing["formal_models"])
        self.assertNotIn("ollama/gemma3:4b", model_listing["formal_models"])
        self.assertEqual(permitted.status_code, 200)
        self.assertFalse(permitted.json()["config"]["protocol"]["allow_small_model"])
        self.assertEqual(rejected.status_code, 422)


    def test_backup_endpoint_restores_a_consistent_database_without_settings(self):
        with TestClient(create_app(self.store, fake_model, start_worker=False)) as client:
            response = client.get('/api/backup')
        self.assertEqual(response.status_code, 200)
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            self.assertEqual(set(archive.namelist()), {"manifest.json", "research.sqlite3"})
            manifest = json.loads(archive.read("manifest.json"))
            database = archive.read("research.sqlite3")
        self.assertEqual(manifest["schema"], "stance-shift-backup/v1")
        self.assertEqual(manifest["files"][0]["sha256"], hashlib.sha256(database).hexdigest())
        self.assertIn("API keys", manifest["excludes"])
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "research.sqlite3").write_bytes(database)
            restored = Store(directory)
            self.assertEqual(restored.dataset(self.dataset_id)["ticker"], "NVDA")

    def test_complete_dataset_snapshot_is_reused_unless_refresh_is_requested(self):
        technical = json.loads(json.dumps(self.data))
        technical.update(kind="historical", collection_rules={"news_item_limit": "uncapped"}, evidence=[], limitations=[], requested_analysis_date="2024-12-31")
        by_domain = {domain: [next(item for item in self.data["evidence"] if item["domain"] == domain)]
                     for domain in ("fundamental", "sentiment", "macro")}
        with patch("research_service.collect.download_prices", side_effect=lambda *_: json.loads(json.dumps(technical))) as prices, \
             patch("research_service.collect.fetch_fundamental", return_value=(by_domain["fundamental"], "")), \
             patch("research_service.collect.fetch_sentiment", return_value=(by_domain["sentiment"], "")), \
             patch("research_service.collect.fetch_macro", return_value=(by_domain["macro"], "")):
            with TestClient(create_app(self.store, fake_model, start_worker=False)) as client:
                first = client.post('/api/datasets/download', json={"ticker":"NVDA", "analysis_date":"2024-12-31"})
                second = client.post('/api/datasets/download', json={"ticker":"NVDA", "analysis_date":"2024-12-31"})
                refreshed = client.post('/api/datasets/download', json={"ticker":"NVDA", "analysis_date":"2024-12-31", "refresh":True})
        self.assertFalse(first.json()["reused"])
        self.assertTrue(second.json()["reused"])
        self.assertFalse(refreshed.json()["reused"])
        self.assertEqual(prices.call_count, 2)

    def _wait_for_collection(self, client, task):
        deadline = time.monotonic() + 10
        while task["stage"] not in ("complete", "failed"):
            self.assertLess(time.monotonic(), deadline, "collection task did not finish")
            time.sleep(.05)
            task = client.get(f'/api/collections/{task["id"]}').json()
        return task

    def test_collection_task_matches_sync_download_and_hides_internal_errors(self):
        technical = json.loads(json.dumps(self.data))
        technical.update(kind="historical", collection_rules={"news_item_limit": "uncapped"}, evidence=[], limitations=[], requested_analysis_date="2024-12-31")
        by_domain = {domain: [next(item for item in self.data["evidence"] if item["domain"] == domain)]
                     for domain in ("fundamental", "sentiment", "macro")}
        case = {"ticker": "NVDA", "analysis_date": "2024-12-31", "refresh": True}
        with patch("research_service.collect.download_prices", side_effect=lambda *_: json.loads(json.dumps(technical))),              patch("research_service.collect.fetch_fundamental", return_value=(by_domain["fundamental"], "")),              patch("research_service.collect.fetch_sentiment", return_value=(by_domain["sentiment"], "")),              patch("research_service.collect.fetch_macro", return_value=(by_domain["macro"], "")):
            with TestClient(create_app(self.store, fake_model, start_worker=False)) as client:
                sync = client.post('/api/datasets/download', json=case).json()
                started = client.post('/api/collections', json=case)
                self.assertEqual(started.status_code, 202)
                task = self._wait_for_collection(client, started.json())
        self.assertEqual(task["stage"], "complete")
        # Same inputs must assemble the same content-addressed snapshot even
        # though the background path records agents as they finish.
        self.assertEqual(task["result"]["id"], sync["id"])
        self.assertEqual(list(task["result"]["agents"]), ["technical", "fundamental", "sentiment", "macro"])
        self.assertEqual(set(task["agents"]), {"technical", "fundamental", "sentiment", "macro"})

        with patch("research_service.collect.download_prices", side_effect=RuntimeError("https://provider/?apikey=SECRET")),              patch("research_service.collect.fetch_fundamental", return_value=([], "")),              patch("research_service.collect.fetch_sentiment", return_value=([], "")),              patch("research_service.collect.fetch_macro", return_value=([], "")):
            with TestClient(create_app(self.store, fake_model, start_worker=False)) as client:
                failed = self._wait_for_collection(client, client.post('/api/collections', json=case).json())
                missing = client.get('/api/collections/does-not-exist')
                invalid = client.post('/api/collections', json={"ticker": "NVDA", "analysis_date": "2024-12-30"})
        self.assertEqual(failed["stage"], "failed")
        self.assertNotIn("SECRET", failed["message"])
        self.assertIn("RuntimeError", failed["message"])
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(invalid.status_code, 422)

    def test_error_mapping_distinguishes_not_found_from_bugs(self):
        with TestClient(create_app(self.store, fake_model, start_worker=False), raise_server_exceptions=False) as client:
            missing = client.get('/api/jobs/does-not-exist')
            self.assertEqual(missing.status_code, 404)
            self.assertEqual(missing.json()["detail"], "找不到實驗")
            # A stray KeyError is a bug, not a missing record: 500 without internals.
            with patch.object(self.store, "job_summaries", side_effect=KeyError("internal_field")):
                broken = client.get('/api/jobs')
        self.assertEqual(broken.status_code, 500)
        self.assertNotIn("internal_field", broken.json()["detail"])

    def test_importing_app_module_has_no_side_effects(self):
        import research_service.app as module
        self.assertFalse(hasattr(module, "app"))

    def test_readiness_date_guard_and_finbert_version_endpoint(self):
        historical = json.loads(json.dumps(self.data))
        historical.update(kind="historical", collection_rules={"news_item_limit": "uncapped"}, requested_analysis_date="2024-12-31")
        historical_id = self.store.add_dataset(historical)

        def enrich(data, **kwargs):
            data["evidence"][1]["sentiment_score"] = .6
            data["processing"] = {"sentiment": {"model": "ProsusAI/finbert", "items": 1, "input": "headline"}}
            return data

        with TestClient(create_app(self.store, fake_model, start_worker=False)) as client:
            readiness = client.get('/api/readiness').json()
            self.assertEqual((readiness["complete_cases"], readiness["target_cases"]), (1, 180))
            mismatch = client.post('/api/jobs', json={"dataset_id":historical_id, "analysis_date":"2024-09-30"})
            self.assertEqual(mismatch.status_code, 422)
            self.assertIn("不能用於", mismatch.json()["detail"])
            with patch("research_service.web.datasets.score_sentiment_finbert", side_effect=enrich):
                response = client.post(f'/api/datasets/{historical_id}/finbert')
            self.assertEqual(response.status_code, 200)
            self.assertNotEqual(response.json()["id"], historical_id)
            self.assertEqual(response.json()["items"], 1)

    def test_download_runs_collection_agents_concurrently_and_reports_each_domain(self):
        active = maximum = 0
        lock = threading.Lock()

        def tracked(value):
            nonlocal active, maximum
            with lock:
                active += 1
                maximum = max(maximum, active)
            try:
                time.sleep(.03)
                return value
            finally:
                with lock:
                    active -= 1

        technical = json.loads(json.dumps(self.data))
        technical.update(kind="historical", collection_rules={"news_item_limit": "uncapped"}, evidence=[], limitations=[], requested_analysis_date="2024-12-31")
        with patch("research_service.collect.download_prices", side_effect=lambda *_: tracked(technical)), \
             patch("research_service.collect.fetch_fundamental", side_effect=lambda *_: tracked(([], "SEC not configured"))), \
             patch("research_service.collect.fetch_sentiment", side_effect=lambda *_, **__: tracked(([], "news not configured"))), \
             patch("research_service.collect.fetch_macro", side_effect=lambda *_: tracked(([], "FRED not configured"))):
            with TestClient(create_app(self.store, fake_model, start_worker=False)) as client:
                response = client.post('/api/datasets/download', json={"ticker":"NVDA", "analysis_date":"2024-12-31"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["reused"])
        self.assertGreaterEqual(maximum, 2)
        self.assertEqual(set(response.json()["agents"]), {"technical", "fundamental", "sentiment", "macro"})
        self.assertEqual(response.json()["agents"]["technical"]["status"], "complete")

    def test_download_with_finbert_keeps_zero_news_as_missing_data(self):
        technical = json.loads(json.dumps(self.data))
        technical.update(kind="historical", collection_rules={"news_item_limit": "uncapped"}, evidence=[], limitations=[], requested_analysis_date="2024-12-31")
        with patch("research_service.collect.download_prices", return_value=technical), \
             patch("research_service.collect.fetch_fundamental", return_value=([], "SEC not configured")), \
             patch("research_service.collect.fetch_sentiment", return_value=([], "news not configured")), \
             patch("research_service.collect.fetch_macro", return_value=([], "FRED not configured")), \
             patch("research_service.web.datasets.score_sentiment_finbert", side_effect=AssertionError("must not score an empty set")):
            with TestClient(create_app(self.store, fake_model, start_worker=False)) as client:
                response = client.post('/api/datasets/download', json={
                    "ticker": "NVDA", "analysis_date": "2024-12-31", "use_finbert": True})
        self.assertEqual(response.status_code, 200)
        sentiment = response.json()["agents"]["sentiment"]
        self.assertEqual(sentiment["status"], "needs_input")
        self.assertEqual(sentiment["finbert"]["reason"], "no_headlines")

    def test_dataset_versions_ranges_and_usage_are_exposed(self):
        self.create("2024-12-31")
        second = json.loads(json.dumps(self.data))
        second["source"] = "unit-test-fixture-v2"
        second_id = self.store.add_dataset(second)
        rows = self.store.datasets()
        current = next(row for row in rows if row["id"] == second_id)
        original = next(row for row in rows if row["id"] == self.dataset_id)
        self.assertEqual((current["version"], original["version"]), (2, 1))
        self.assertEqual(original["price_start"], self.data["prices"][0]["date"])
        self.assertEqual(original["price_end"], self.data["prices"][-1]["date"])
        self.assertEqual(original["used_analysis_dates"], ["2024-12-31"])

    def test_research_agents_and_experiment_groups_execute_concurrently(self):
        active = maximum = 0
        lock = threading.Lock()

        def delayed_model(protocol, messages):
            nonlocal active, maximum
            with lock:
                active += 1
                maximum = max(maximum, active)
            try:
                time.sleep(.03)
                return fake_model(protocol, messages)
            finally:
                with lock:
                    active -= 1

        job = self.create()
        engine = Engine(self.store, delayed_model, parallel_workers=4)
        job["state"] = engine.advance(job)  # Coordinator input lock.
        job["state"] = engine.advance(job)  # Four research agents.
        self.assertGreaterEqual(maximum, 2)
        self.assertEqual(set(job["state"]["research"]), {"technical", "fundamental", "sentiment", "macro"})
        job["state"] = engine.advance(job)  # Neutral report lock.
        maximum = 0
        job["state"] = engine.advance(job)  # First A/B/C/D decision wave.
        self.assertGreaterEqual(maximum, 2)
        self.assertEqual({record["group"] for record in job["state"]["records"]}, set("ABCD"))

    def test_local_ollama_research_uses_one_runner_without_changing_cloud_parallelism(self):
        active = maximum = 0
        lock = threading.Lock()

        def tracked(protocol, messages):
            nonlocal active, maximum
            with lock:
                active += 1
                maximum = max(maximum, active)
            try:
                time.sleep(.01)
                return fake_model(protocol, messages)
            finally:
                with lock:
                    active -= 1

        protocol = StudyProtocol(model="ollama/demo", dataset_kind="synthetic", bootstrap_replicates=199)
        job = self.store.create({"ticker": "NVDA", "analysis_date": "2024-12-31", "dataset_id": self.dataset_id,
                                 "protocol": asdict(protocol), "protocol_hash": protocol.fingerprint})
        engine = Engine(self.store, tracked, parallel_workers=4)
        engine.uses_builtin_provider = True
        first = engine.advance(job)
        self.store.save_step(job["id"], first)
        engine.advance(self.store.get(job["id"]))
        self.assertEqual(maximum, 1)

    def test_local_ollama_checkpoints_one_decision_per_step(self):
        engine = Engine(self.store, fake_model, parallel_workers=4)
        engine.uses_builtin_provider = True
        job = self.create()
        for _ in range(3):
            job["state"] = engine.advance(job)
        self.assertIn("report", job["state"])
        self.assertEqual(job["state"]["records"], [])
        job["state"] = engine.advance(job)
        self.assertEqual(len(job["state"]["records"]), 1)
        job["state"] = engine.advance(job)
        self.assertEqual(len(job["state"]["records"]), 2)

    def test_ollama_parallel_is_opt_in_and_bounded(self):
        # v3-1001.x: concurrency is a protocol field (part of the fingerprint), not an environment setting.
        engine = Engine(self.store, fake_model, parallel_workers=4)
        engine.uses_builtin_provider = True
        protocol = StudyProtocol(dataset_kind="synthetic", bootstrap_replicates=199, ollama_parallel=4)
        self.assertNotEqual(protocol.fingerprint, self.protocol.fingerprint)
        job = self.store.create({"ticker": "NVDA", "analysis_date": "2024-12-31", "dataset_id": self.dataset_id,
                                 "protocol": asdict(protocol), "protocol_hash": protocol.fingerprint})
        for _ in range(3):
            job["state"] = engine.advance(job)
        job["state"] = engine.advance(job)
        self.assertEqual(len(job["state"]["records"]), 4)
        self.assertEqual(job["state"]["trace"][-1]["effective_workers"], 4)
        with patch.dict("os.environ", {"RESEARCH_OLLAMA_PARALLEL": "9"}), self.assertRaises(ValueError):
            Engine(self.store, fake_model)

    def test_parallel_agent_failure_uses_audited_source_extract(self):
        job = self.create()
        job["state"] = Engine(self.store, fake_model).advance(job)

        def fail_sentiment(protocol, messages):
            if "Domain: sentiment" in messages[1]["content"]:
                raise TimeoutError("test timeout")
            return fake_model(protocol, messages)

        job["state"] = Engine(self.store, fail_sentiment, parallel_workers=4).advance(job)
        self.assertEqual(set(job["state"]["research"]), {"technical", "fundamental", "sentiment", "macro"})
        self.assertEqual(job["state"]["research"]["sentiment"]["status"], "degraded")
        self.assertEqual(job["state"]["research"]["sentiment"]["audit"]["error_type"], "TimeoutError")

    def test_fundamental_source_locked_extract_preserves_raw_claims_without_a_model_call(self):
        items = [{"evidence_id": "sec-revenue", "domain": "fundamental", "claim": "Revenues = 91166000000 USD"},
                 {"evidence_id": "sec-income", "domain": "fundamental", "claim": "NetIncomeLoss = 50,789,000,000 USD"}]
        result, audit = source_locked_fundamental(items)
        # v3-0930.3: exact values live in claim_map and the cited evidence, not in free summary prose.
        self.assertNotIn("91,166,000,000", result["summary"])
        self.assertEqual(result["claim_map"][0], {"evidence_id": "sec-revenue", "claim": "Revenues = 91166000000 USD"})
        self.assertEqual(result["evidence_ids"], ["sec-revenue", "sec-income"])
        self.assertEqual(result["claim_map"][1], {"evidence_id": "sec-income", "claim": "NetIncomeLoss = 50,789,000,000 USD"})
        self.assertEqual(audit["mode"], "source_locked_extract")

    def test_invalid_research_citations_use_audited_source_extract(self):
        job = self.create()
        job["state"] = Engine(self.store, fake_model).advance(job)

        def invalid_sentiment(protocol, messages):
            if "Domain: sentiment" in messages[1]["content"]:
                result = {"summary":"unsupported", "evidence_ids":["invented-id"], "risks":[]}
                return result, {"prompt_hash":digest(messages), "usage":{}, "raw_response":json.dumps(result)}
            return fake_model(protocol, messages)

        job["state"] = Engine(self.store, invalid_sentiment).advance(job)
        sentiment = job["state"]["research"]["sentiment"]
        self.assertEqual(sentiment["status"], "degraded")
        self.assertEqual(sentiment["audit"]["fallback"], "deterministic_source_extract")
        # Sentiment reaches the models as FinBERT indicators (v3-0930.1), so the audited fallback cites those.
        self.assertEqual(len(sentiment["evidence_ids"]), 3)
        self.assertTrue(all(item.startswith("sentiment-target-") for item in sentiment["evidence_ids"]))

    def test_invalid_decision_citation_retries_with_new_seed_and_audit(self):
        job = self.create()
        bootstrap = Engine(self.store, fake_model)
        job["state"] = bootstrap.advance(job)  # Coordinator input lock.
        job["state"] = bootstrap.advance(job)  # Four research agents.
        job["state"] = bootstrap.advance(job)  # Neutral report lock.
        target_key = "d-r1-agent-b"
        target_seed = (self.protocol.inference_seed + int(digest(target_key)[:8], 16)) % 2_147_483_647
        retry_key = f"{target_key}:validation-retry-2"
        retry_seed = (self.protocol.inference_seed + int(digest(retry_key)[:8], 16)) % 2_147_483_647
        observed_seeds = []

        def invalid_once(protocol, messages, seed=None):
            observed_seeds.append(seed)
            items = json.loads(messages[1]["content"])["report"]["evidence"]
            action = "Sell" if "action MUST be Sell" in messages[0]["content"] else "Buy"
            result = {"action": action, "expected_return_pct": -5.0 if action == "Sell" else 5.0,
                      "confidence": .8, "rationale": "Synthetic test decision",
                      "evidence_ids": ["invented-id"] if seed == target_seed else [items[0]["evidence_id"]],
                      "risks": ["test"]}
            if "assigned debate stance" in messages[0]["content"]:
                result["strongest_counterpoint"] = "Synthetic counterpoint."
            return result, {"prompt_hash": digest(messages), "usage": {}, "raw_response": json.dumps(result), "seed": seed}

        job["state"] = Engine(self.store, invalid_once, parallel_workers=4).advance(job)
        record = next(item for item in job["state"]["records"] if item["key"] == target_key)
        self.assertEqual(len(job["state"]["records"]), 12)
        self.assertIn(target_seed, observed_seeds)
        self.assertIn(retry_seed, observed_seeds)
        self.assertEqual(record["output"]["invalid_evidence_ids"], [])
        self.assertEqual(record["audit"]["validation_retries"][0]["error_type"], "ValueError")

    def test_json_schema_validation_errors_are_retried(self):
        engine = Engine(self.store, fake_model)
        call = next(item for item in decision_plan(self.protocol) if item.key == "a-decision")
        messages = messages_for(call, {"evidence": []}, [], [], self.protocol)
        valid = {"action": "Hold", "expected_return_pct": 0.0, "confidence": .5,
                 "rationale": "Synthetic retry result", "evidence_ids": ["technical-1"], "risks": []}
        seen = []

        def patched(_protocol, _messages, _key, _temperature, _aliases=None):
            seen.append(_key)
            if len(seen) == 1:
                raise JsonSchemaValidationError("synthetic schema rejection")
            return valid, {"prompt_hash": "synthetic", "usage": {}, "raw_response": json.dumps(valid)}

        engine.call_model = patched
        result, audit = engine.validated_decision(self.protocol, call, messages,
                                                  [{"evidence_id": "technical-1", "domain": "technical", "claim": "x"}])
        self.assertEqual(result["action"], "Hold")
        self.assertEqual(seen, ["a-decision", "a-decision:validation-retry-2"])
        self.assertEqual(audit["validation_retries"][0]["error_type"], "ValidationError")

    def test_unsupported_positive_magnitude_retry_explains_negative_source_sign(self):
        # Retry-then-redact is the registered v3-0930.3 behaviour; v3-1001.x redacts at once.
        self.protocol = StudyProtocol(version="v3-0930.3", dataset_kind="synthetic", bootstrap_replicates=199)
        engine = Engine(self.store, fake_model)
        call = next(item for item in decision_plan(self.protocol) if item.key == "a-decision")
        evidence = [{"evidence_id": "sec-yoy", "domain": "fundamental", "comparative": True,
                     "claim": "Revenue: year_over_year_change_pct=-1.400692"}]
        messages = messages_for(call, {"evidence": evidence}, [], [], self.protocol)
        invalid = {"action": "Sell", "expected_return_pct": -2.0, "confidence": .6,
                   "rationale": "Revenue declined by 1.400692%.",
                   "evidence_ids": ["sec-yoy"], "risks": []}
        valid = {"action": "Sell", "expected_return_pct": -2.0, "confidence": .6,
                 "rationale": "The supplied comparison indicates a decline.",
                 "evidence_ids": ["sec-yoy"], "risks": []}
        seen = []

        def patched(_protocol, retry_messages, _key, _temperature, _aliases=None):
            seen.append(retry_messages)
            chosen = invalid if len(seen) == 1 else valid
            return chosen, {"prompt_hash": "synthetic", "usage": {}, "raw_response": json.dumps(chosen)}

        engine.call_model = patched
        result, audit = engine.validated_decision(self.protocol, call, messages, evidence)
        retry_text = seen[1][-1]["content"]
        self.assertIn("-1.400692 (negative values)", retry_text)
        self.assertIn("or omit the numbers", retry_text)
        self.assertEqual(result["action"], "Sell")
        self.assertEqual(audit["validation_retries"][0]["error_type"], "ValueError")

    def test_schema_retry_names_the_field_and_limit(self):
        from research_service.engine import validation_hint

        error = None
        try:
            import jsonschema
            jsonschema.validate({"rebutted_claim": "x" * 300},
                                {"type": "object", "properties": {"rebutted_claim": {"type": "string", "maxLength": 240}}})
        except JsonSchemaValidationError as caught:
            error = caught
        hint = validation_hint(error)
        self.assertIn("rebutted_claim", hint)
        self.assertIn("maxLength=240", hint)
        self.assertNotIn("xxxx", hint)

    def test_persistent_unsupported_numbers_are_redacted_instead_of_aborting(self):
        # Retry-then-redact is the registered v3-0930.3 behaviour; v3-1001.x redacts at once.
        self.protocol = StudyProtocol(version="v3-0930.3", dataset_kind="synthetic", bootstrap_replicates=199)
        engine = Engine(self.store, fake_model)
        call = next(item for item in decision_plan(self.protocol) if item.key == "a-decision")
        evidence = [{"evidence_id": "sec-yoy", "domain": "fundamental", "comparative": True, "metric": "Revenue",
                     "current_period": "2024-12-31", "prior_period": "2023-12-31",
                     "current_value": 98.5993, "prior_value": 100.0, "change_pct": -1.400692,
                     "claim": "Revenue: year_over_year_change_pct=-1.400692"}]
        messages = messages_for(call, {"evidence": evidence}, [], [], self.protocol)
        bound = {"evidence_id": "sec-yoy", "metric": "Revenue year-over-year change",
                 "period": "2023-12-31..2024-12-31", "unit": "percent", "value": -1.400692,
                 "quote": "Revenue fell -1.400692%"}
        invalid = {"action": "Sell", "expected_return_pct": -2.0, "confidence": .6,
                   "rationale": "Revenue fell -1.400692%, roughly 1.4% (about 987654 units).",
                   "evidence_ids": ["sec-yoy"], "risks": ["Margins near 12345.6789"],
                   "numeric_claims": [bound]}
        engine.call_model = lambda *_args, **_kwargs: (
            json.loads(json.dumps(invalid)), {"prompt_hash": "synthetic", "usage": {}, "raw_response": "x"})
        result, audit = engine.validated_decision(self.protocol, call, messages, evidence)
        self.assertEqual(result["action"], "Sell")
        self.assertIn("-1.400692", result["rationale"])
        self.assertNotIn("987654", result["rationale"])
        self.assertNotIn("12345.6789", result["risks"][0])
        self.assertIn("987654", audit["numeric_redaction"])
        self.assertEqual(len(audit["validation_retries"]), self.protocol.provider_retry_attempts)

    def test_comparable_fundamental_citation_is_valid_decision_evidence(self):
        engine = Engine(self.store, fake_model)
        call = next(item for item in decision_plan(self.protocol) if item.key == "a-decision")
        messages = messages_for(call, {"evidence": []}, [], [], self.protocol)
        evidence = [
            {"evidence_id": "sec-point", "domain": "fundamental", "claim": "Assets=10 USD"},
            {"evidence_id": "sec-yoy", "domain": "fundamental", "comparative": True,
             "claim": "Revenue: current=12 USD; prior=10 USD; year_over_year_change_pct=20"},
            {"evidence_id": "technical-1", "domain": "technical", "claim": "return20=0.01"},
        ]
        result = {"action": "Buy", "expected_return_pct": 2.0, "confidence": .6,
                  "rationale": "The supplied comparison supports the forecast.",
                  "evidence_ids": ["sec-yoy"], "risks": []}
        engine.call_model = lambda *_args, **_kwargs: (
            result, {"prompt_hash": "synthetic", "usage": {}, "raw_response": json.dumps(result)})
        validated, _ = engine.validated_decision(self.protocol, call, messages, evidence)
        self.assertEqual(validated["invalid_evidence_ids"], [])

    def test_degraded_research_runs_are_excluded_from_study_statistics(self):
        job = self.complete(self.create())
        job["state"]["report"]["degraded_research_domains"] = ["sentiment"]
        report = study_report([job])
        self.assertEqual(report["status"], "no_formal_cases")
        self.assertEqual(report["excluded_degraded_research_runs"], 1)

    def test_switch_round_visibility_is_agent_isolated(self):
        # Round 2 is the role-switch round: each side sees only its OWN
        # round-1 turn, never its counterpart's, so the two histories now
        # differ instead of matching (unlike rounds 1 and 3).
        job = self.complete(self.create())
        calls = [c for c in decision_plan(self.protocol) if c.group == 'D' and c.round == 2]
        a = messages_for(calls[0], job['state']['report'], job['state']['records'], [], self.protocol)
        b = messages_for(calls[1], job['state']['report'], job['state']['records'], [], self.protocol)
        a_history, b_history = json.loads(a[1]['content'])['history'], json.loads(b[1]['content'])['history']
        self.assertEqual((len(a_history), len(b_history)), (1, 1))
        self.assertNotEqual(a_history, b_history)
        self.assertEqual(a_history[0]['key'], f"d-r1-{calls[0].agent}")
        self.assertEqual(b_history[0]['key'], f"d-r1-{calls[1].agent}")

    def test_decision_policy_distinguishes_hold_no_trade_and_enforces_debate_stance(self):
        plan = decision_plan(self.protocol)
        neutral = messages_for(plan[0], {"evidence": []}, [], [], self.protocol)
        bull_call = next(call for call in plan if call.kind == "debate" and call.stance == "BULL")
        bear_call = next(call for call in plan if call.kind == "debate" and call.stance == "BEAR")
        bull = messages_for(bull_call, {"evidence": []}, [], [], self.protocol)
        bear = messages_for(bear_call, {"evidence": []}, [], [], self.protocol)
        self.assertNotIn("risk preference", neutral[0]["content"])
        self.assertIn("Hold is not a way to avoid committing", neutral[0]["content"])
        self.assertIn("next 60 trading sessions", neutral[0]["content"])
        self.assertEqual(output_schema_for(neutral)["properties"]["action"]["enum"], ["Buy", "Hold", "Sell"])
        self.assertEqual(output_schema_for(bull)["properties"]["action"]["enum"], ["Buy"])
        self.assertEqual(output_schema_for(bear)["properties"]["action"]["enum"], ["Sell"])
        self.assertIn("strongest_counterpoint", bull[0]["content"])

    def test_temperature_action_and_pilot_diagnostics_are_auditable(self):
        observed = []
        def temperature_model(protocol, messages, temperature=None, **_kwargs):
            observed.append(temperature)
            return fake_model(protocol, messages)
        job = self.create()
        engine = Engine(self.store, temperature_model)
        for _ in range(10):
            state = engine.advance(job)
            self.store.save_step(job["id"], state)
            job = self.store.get(job["id"])
            if job["status"] == "complete":
                break
        self.assertIn(self.protocol.voting_temperature, observed)
        self.assertIn(self.protocol.temperature, observed)
        self.assertEqual(derive_action(2.0, 2.0), "Hold")
        self.assertEqual(derive_action(2.01, 2.0), "Buy")
        self.assertEqual(derive_action(-2.01, 2.0), "Sell")
        diagnostic = pilot_diagnostics([job])
        self.assertEqual(diagnostic["verdict"], "blocked")
        self.assertIn("arms_not_identifiable", diagnostic["blocking_reasons"])
        sensitivity = hold_band_sensitivity([job], sigmas=(0.0,))
        candidate_rows = [row for row in sensitivity["sigmas"][0]["summary"] if row["group"] in "ABCD"]
        self.assertTrue(all(row["hold_rate"] == 0 for row in candidate_rows))

    def test_switch_completeness_diagnostic_is_saved(self):
        job = self.complete(self.create())
        diagnostic = job["state"]["completeness_diagnostic"]
        self.assertTrue(diagnostic["isolation_enabled"])
        self.assertEqual(len(diagnostic["pairs"]), 2)
        self.assertEqual(len(diagnostic["control"]["pairs"]), 2)

    def test_preregistration_freeze_locks_dataset_ids_and_flags_later_additions(self):
        with TestClient(create_app(self.store, fake_model, start_worker=False)) as client:
            first = self.complete(self.create("2024-12-31"))
            protocol_hash = first["config"]["protocol_hash"]
            self.assertIsNone(client.get(f'/api/studies/{protocol_hash}').json()["preregistration"])
            # Locking after results exist is retrospective, not a preregistration.
            self.assertEqual(client.post(f'/api/studies/{protocol_hash}/freeze').status_code, 422)
            frozen = self.store.freeze(protocol_hash, [self.dataset_id])
            self.assertTrue(frozen["frozen_at"])
            again = self.store.freeze(protocol_hash, [self.dataset_id])
            self.assertEqual(again["frozen_at"], frozen["frozen_at"])
            report = client.get(f'/api/studies/{protocol_hash}').json()
            self.assertEqual(report["preregistration"]["dataset_ids"], [self.dataset_id])
            self.assertEqual(report["preregistration"]["post_freeze_dataset_ids"], [])
            other_dataset_id = self.store.add_dataset({**self.data, "source": "unit-test-fixture-v2"})
            self.complete(self.store.create({"ticker": "NVDA", "analysis_date": "2025-03-31",
                "dataset_id": other_dataset_id, "protocol": asdict(self.protocol), "protocol_hash": protocol_hash}))
            report = client.get(f'/api/studies/{protocol_hash}').json()
            self.assertEqual(report["preregistration"]["post_freeze_dataset_ids"], [other_dataset_id])
            self.assertEqual(report["excluded_nonformal_reasons"], {"non_historical_dataset": 2})

    def test_preregister_locks_a_planned_batch_without_creating_jobs(self):
        with TestClient(create_app(self.store, fake_model, start_worker=False)) as client:
            case = {"dataset_id": self.dataset_id, "analysis_date": "2024-12-31"}
            locked = client.post('/api/studies/preregister', json={"cases": [case]})
            self.assertEqual(locked.status_code, 200, locked.text)
            body = locked.json()
            self.assertEqual((body["dataset_ids"], body["cases"]), ([self.dataset_id], 1))
            self.assertEqual(self.store.job_summaries(), [])
            self.assertEqual(self.store.preregistration(body["protocol_hash"])["frozen_at"], body["frozen_at"])
            mixed = client.post('/api/studies/preregister', json={"cases": [case, {**case, "voting_samples": 5}]})
            self.assertEqual(mixed.status_code, 422)

    def test_enqueue_is_idempotent_and_limited_to_the_preregistered_sample(self):
        with TestClient(create_app(self.store, fake_model, start_worker=False)) as client:
            case = {"dataset_id": self.dataset_id, "analysis_date": "2024-12-31"}
            protocol_hash = client.post('/api/studies/preregister', json={"cases": [case]}).json()["protocol_hash"]
            listed = client.get('/api/studies').json()
            self.assertEqual([(s["protocol_hash"], s["cases"]) for s in listed], [(protocol_hash, 1)])
            self.assertEqual(listed[0]["progress"]["not_created"], 1)

            first = client.post(f'/api/studies/{protocol_hash}/enqueue', json={"cases": [case, case]})
            self.assertEqual(first.status_code, 200, first.text)
            # The same case listed twice in one request is created once.
            self.assertEqual((first.json()["created"], first.json()["skipped_existing"]), (1, 1))
            # Pressing the button twice (or a helper re-sending the batch) must not duplicate GPU work.
            again = client.post(f'/api/studies/{protocol_hash}/enqueue', json={"cases": [case]}).json()
            self.assertEqual((again["created"], again["skipped_existing"]), (1 - 1, 1))
            self.assertEqual(len(self.store.job_summaries()), 1)

            # The single-job and batch routes refuse a second job for a registered case.
            self.assertEqual(client.post('/api/jobs', json=case).status_code, 422)
            self.assertEqual(client.post('/api/batches', json={"cases": [case]}).status_code, 422)
            outsider = self.store.add_dataset({**self.data, "source": "unit-test-fixture-v2"})
            refused = client.post(f'/api/studies/{protocol_hash}/enqueue',
                                  json={"cases": [{"dataset_id": outsider, "analysis_date": "2024-12-31"}]})
            self.assertEqual(refused.status_code, 422)
            other_protocol = client.post(f'/api/studies/{protocol_hash}/enqueue',
                                         json={"cases": [{**case, "voting_samples": 5}]})
            self.assertEqual(other_protocol.status_code, 422)
            self.assertEqual(len(self.store.job_summaries()), 1)

            paused = client.post(f'/api/studies/{protocol_hash}/pause-all').json()
            self.assertEqual((paused["changed"], paused["progress"]["counts"]["paused"]), (1, 1))
            resumed = client.post(f'/api/studies/{protocol_hash}/resume-all').json()
            self.assertEqual((resumed["changed"], resumed["progress"]["counts"]["queued"]), (1, 1))
            self.assertEqual(client.post(f'/api/studies/{protocol_hash}/delete-all').status_code, 404)

    def test_enqueue_requires_a_preregistration(self):
        with TestClient(create_app(self.store, fake_model, start_worker=False)) as client:
            response = client.post('/api/studies/not-registered/enqueue',
                                   json={"cases": [{"dataset_id": self.dataset_id, "analysis_date": "2024-12-31"}]})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.store.job_summaries(), [])

    def test_freeze_rejects_changing_the_dataset_set_after_the_fact(self):
        job = self.complete(self.create("2024-12-31"))
        protocol_hash = job["config"]["protocol_hash"]
        self.store.freeze(protocol_hash, [self.dataset_id])
        other_dataset_id = self.store.add_dataset({**self.data, "source": "unit-test-fixture-v2"})
        with self.assertRaises(ValueError):
            self.store.freeze(protocol_hash, [self.dataset_id, other_dataset_id])

    def test_provider_error_pauses_and_requires_explicit_resume(self):
        job = self.create()
        self.store.save_step(job['id'], job['state'], 'provider failed')
        failed = self.store.get(job['id'])
        self.assertEqual(failed['status'], 'paused')
        self.assertEqual(failed['wants_run'], 0)
        self.store.control(job['id'], 'resume')
        self.assertEqual(self.store.get(job['id'])['status'], 'queued')

    def test_finbert_is_explicit_and_audited(self):
        calls = []
        def classify(text):
            calls.append(text)
            return [{'label':'positive','score':.7},{'label':'neutral','score':.2},{'label':'negative','score':.1}]
        with patch.dict(os.environ, {'HF_TOKEN':'test-token'}):
            enriched = score_sentiment_finbert(self.data, classify)
        item = next(e for e in enriched['evidence'] if e['domain'] == 'sentiment')
        self.assertEqual(calls, [item['claim']])
        self.assertEqual(item['direction'], 'bullish')
        self.assertIn('ProsusAI/finbert', item['sentiment_method'])


if __name__ == '__main__':
    unittest.main()
