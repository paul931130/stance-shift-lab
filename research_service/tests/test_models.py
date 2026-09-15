import io
import json
import unittest
from unittest.mock import patch

from research_service.models import _compact_report, compact_research_evidence, generate, messages_for
from research_service.protocol import StudyProtocol, decision_plan


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


class ModelReliabilityTests(unittest.TestCase):
    def test_prompt_compaction_keeps_titles_scores_and_financial_numbers(self):
        sentiment = [{"evidence_id": f"news-{index}", "domain": "sentiment", "available_at": "2024-12-20",
                      "headline": "NVIDIA headline " + "h" * 800, "claim": "c" * 5000,
                      "source": "https://example.test/" + "path" * 400,
                      "evidence_scope": "target", "relevance_score": .9,
                      "sentiment_score": .3, "sentiment_label": "positive", "direction": "bullish"}
                     for index in range(12)]
        compact = compact_research_evidence("sentiment", sentiment)
        self.assertEqual([item["evidence_id"] for item in compact], [item["evidence_id"] for item in sentiment])
        self.assertTrue(all(item["evidence_scope"] == "target" and item["sentiment_score"] == .3 for item in compact))
        self.assertTrue(all("source" not in item and "claim" not in item for item in compact))
        self.assertLess(len(json.dumps(compact)), 8000)

        financial = {"evidence_id": "revenue", "domain": "fundamental", "available_at": "2024-11-20",
                     "claim": "Revenues = 91166000000 USD; period 2024-01-29–2024-10-27; form 10-Q"}
        self.assertEqual(compact_research_evidence("fundamental", [financial])[0]["claim"], financial["claim"])
        report = {"research": {"sentiment": {"status": "complete", "summary": "s" * 1000,
                                                 "evidence_ids": ["news-0"], "risks": []}},
                  "evidence": [*sentiment, financial]}
        decision_view = _compact_report(report)
        prompt_news = next(item for item in decision_view["evidence"] if item["domain"] == "sentiment")
        self.assertEqual(prompt_news["evidence_scope"], "target")
        self.assertNotIn("source", prompt_news)

    def test_source_locked_fundamental_fields_remain_auditable_but_are_not_decision_features(self):
        financial = {"evidence_id": "revenue", "domain": "fundamental", "available_at": "2024-11-20",
                     "claim": "Revenues = 91166000000 USD; period 2024-01-29–2024-10-27; form 10-Q"}
        technical = {"evidence_id": "return", "domain": "technical", "claim": "return20 = -0.01"}
        report = {"research": {"fundamental": {"status": "complete", "mode": "source_locked",
                                                  "summary": financial["claim"], "evidence_ids": ["revenue"]}},
                  "evidence": [financial, technical]}
        decision_view = _compact_report(report)
        payload = json.dumps(decision_view)
        self.assertNotIn("91166000000", payload)
        self.assertNotIn('"revenue"', payload)
        self.assertIn("SEC point facts are preserved", payload)
        self.assertEqual([item["evidence_id"] for item in decision_view["evidence"]], ["return"])

    def test_comparable_sec_metrics_are_included_as_decision_features(self):
        financial = {"evidence_id": "revenue-yoy", "domain": "fundamental",
                     "available_at": "2024-11-20", "comparative": True,
                     "claim": "Revenue: current=30000000000 USD; prior=18000000000 USD; year_over_year_change_pct=66.666667"}
        technical = {"evidence_id": "return", "domain": "technical", "claim": "return20 = -0.01"}
        report = {"research": {"fundamental": {"status": "complete", "mode": "source_locked_comparative",
                                                  "summary": financial["claim"], "evidence_ids": ["revenue-yoy"]}},
                  "evidence": [financial, technical]}
        decision_view = _compact_report(report)
        self.assertEqual([item["evidence_id"] for item in decision_view["evidence"]],
                         ["revenue-yoy", "return"])
        self.assertIn("30000000000", json.dumps(decision_view))

    def test_debate_history_omits_provider_audit_and_is_bounded(self):
        protocol = StudyProtocol(model="ollama/demo", dataset_kind="synthetic", bootstrap_replicates=199)
        call = next(item for item in decision_plan(protocol) if item.key == "d-r3-agent-a")
        history = [{"key": f"d-r{round_number}-agent-a", "group": "D", "kind": "debate", "stance": "BULL",
                    "round": round_number, "output": {"action": "Buy", "expected_return_pct": 3.0,
                    "confidence": .7, "rationale": "r" * 3000, "evidence_ids": ["e1"] * 8,
                    "strongest_counterpoint": "c" * 1000},
                    "audit": {"raw_response": "secret audit payload " * 2000}}
                   for round_number in (1, 2)]
        report = {"ticker": "NVDA", "base_rates": {"hold_band_pct": 2.0}, "research": {}, "evidence": []}
        messages = messages_for(call, report, history, [], protocol)
        payload = json.loads(messages[1]["content"])
        self.assertNotIn("audit", json.dumps(payload))
        self.assertTrue(all(len(item["output"]["rationale"]) <= 60 for item in payload["history"]))
        self.assertTrue(all(len(item["output"]["strongest_counterpoint"]) <= 50 for item in payload["history"]))

    def test_4k_decision_view_limits_news_and_summarizes_maturity_memory(self):
        protocol = StudyProtocol(model="ollama/demo", dataset_kind="synthetic", bootstrap_replicates=199)
        call = next(item for item in decision_plan(protocol) if item.key == "d-adjudication")
        sentiment = [{"evidence_id": f"news-{index}", "domain": "sentiment", "available_at": "2024-12-20",
                      "headline": "NVIDIA headline " + "h" * 400, "evidence_scope": "target",
                      "sentiment_score": .2} for index in range(12)]
        report = {"ticker": "NVDA", "analysis_date": "2024-12-31",
                  "base_rates": {"hold_band_pct": 2.0, "horizon_sessions": 60},
                  "research": {"sentiment": {"status": "complete", "summary": "s" * 1000,
                                                "evidence_ids": ["news-0", "news-1"]}},
                  "decision_calibration": {"technical": {"return20": .1, "mean20_vs_mean60": .1,
                                                            "annual_volatility": .2, "direction": "upward", "strength": "weak"},
                                           "sentiment": {"target": {"count": 12, "scored_count": 12,
                                                                      "mean_score": .2, "direction": "positive"}}},
                  "evidence": sentiment}
        records = [{"key": f"d-r{round_number}-agent-a", "group": "D", "kind": "debate", "stance": "BULL",
                    "round": round_number, "output": {"action": "Buy", "expected_return_pct": 3.0,
                    "rationale": "r" * 1000, "evidence_ids": ["news-0"], "strongest_counterpoint": "c" * 1000}}
                   for round_number in (1, 2, 3)]
        memory = [{"analysis_date": f"2024-0{index + 1}-01", "action": "Buy", "correct": True,
                   "net_return": .0123, "raw_response": "must never reach a prompt" * 1000}
                  for index in range(12)]
        messages = messages_for(call, report, records, memory, protocol)
        payload = json.loads(messages[1]["content"])
        prompt = messages[0]["content"] + messages[1]["content"]
        self.assertEqual(len([item for item in payload["report"]["evidence"]
                              if item["domain"] == "sentiment"]), 4)
        self.assertEqual(payload["matured_same_group_memory"]["count"], 12)
        self.assertNotIn("raw_response", json.dumps(payload))
        self.assertLess(len(prompt), 7000)

    def test_invalid_json_retries_with_same_audited_seed(self):
        calls = []
        payloads = [
            {"message": {"content": '{"action":"Buy"'}, "model": "demo"},
            {"message": {"content": json.dumps({"action":"Buy", "expected_return_pct":3.0, "confidence":.8,
                "rationale":"brief", "evidence_ids":["e1"], "risks":[]})}, "model": "demo"},
        ]

        def request(req, timeout):
            calls.append(json.loads(req.data))
            return Response(json.dumps(payloads.pop(0)).encode())

        protocol = StudyProtocol(model="ollama/demo", dataset_kind="synthetic", bootstrap_replicates=199)
        messages = [{"role":"system", "content":"decision"}, {"role":"user", "content":"{}"}]
        with patch("research_service.models.urlopen", side_effect=request), patch("research_service.models.time.sleep"):
            result, audit = generate(protocol, messages, seed=1234)
        self.assertEqual(result["action"], "Buy")
        self.assertEqual((audit["provider_attempts"], audit["seed"]), (2, 1234))
        self.assertEqual(audit["prior_failures"], ["JSONDecodeError"])
        self.assertEqual([call["options"]["seed"] for call in calls], [1234, 1234])

    def test_gpu_tw_ollama_endpoint_is_used_only_when_explicitly_configured(self):
        request = None

        def requester(req, timeout):
            nonlocal request
            request = req
            return Response(json.dumps({"message": {"content": json.dumps({
                "action": "Buy", "expected_return_pct": 3.0, "confidence": .8,
                "rationale": "brief", "evidence_ids": ["e1"], "risks": []
            })}, "model": "demo"}).encode())

        protocol = StudyProtocol(model="ollama/demo", dataset_kind="synthetic", bootstrap_replicates=199)
        with patch.dict("os.environ", {"GPUTW_OLLAMA_BASE_URL": "https://gpu.example/ollama",
                                        "GPUTW_OLLAMA_API_KEY": "gpu-model-key"}, clear=False), \
             patch("research_service.models.urlopen", side_effect=requester):
            generate(protocol, [{"role": "system", "content": "decision"}, {"role": "user", "content": "{}"}])
        self.assertEqual(request.full_url, "https://gpu.example/ollama/api/chat")
        self.assertEqual(request.get_header("Authorization"), "Bearer gpu-model-key")


if __name__ == "__main__":
    unittest.main()
