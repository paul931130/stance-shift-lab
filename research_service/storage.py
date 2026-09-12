import json
from pathlib import Path
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from tempfile import TemporaryDirectory
from uuid import uuid4


def now():
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "research.sqlite3"
        # Dataset content is immutable and content-addressed (id = digest(data)),
        # so the derived summary below never needs to be recomputed once cached.
        self._dataset_summary_cache = {}
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS datasets(id TEXT PRIMARY KEY, ticker TEXT, content TEXT, created_at TEXT);
                CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, status TEXT, wants_run INTEGER,
                    config TEXT, state TEXT, error TEXT, created_at TEXT, updated_at TEXT);
                CREATE TABLE IF NOT EXISTS case_results(
                    job_id TEXT, protocol_hash TEXT, ticker TEXT, analysis_date TEXT,
                    "group" TEXT, horizon INTEGER, cost_model TEXT, decision_layer TEXT,
                    maturity_date TEXT, action TEXT, correct INTEGER, net_return REAL,
                    degraded INTEGER, created_at TEXT,
                    PRIMARY KEY(job_id, "group", horizon, cost_model, decision_layer));
                CREATE INDEX IF NOT EXISTS idx_case_results_lookup
                    ON case_results(protocol_hash, ticker, "group", maturity_date);
                CREATE TABLE IF NOT EXISTS preregistrations(
                    protocol_hash TEXT PRIMARY KEY, dataset_ids TEXT, frozen_at TEXT);
            """)
        self.backfill_case_results()

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def recover(self):
        with self.connect() as db:
            db.execute("UPDATE jobs SET status='paused', wants_run=0, error='服務重啟；已完成步驟保留，請按繼續' WHERE status='running'")

    def backup_bytes(self):
        """Return a WAL-safe SQLite snapshot without stopping the research worker."""
        with TemporaryDirectory(prefix="stance-shift-backup-") as directory:
            target_path = Path(directory) / "research.sqlite3"
            with sqlite3.connect(self.path, timeout=30) as source:
                with sqlite3.connect(target_path) as target:
                    source.backup(target)
            return target_path.read_bytes()

    def add_dataset(self, data):
        from .data import digest
        key = digest(data)
        with self.connect() as db:
            db.execute("INSERT OR IGNORE INTO datasets VALUES(?,?,?,?)", (key, data["ticker"], json.dumps(data, ensure_ascii=False, allow_nan=False), now()))
        return key

    def dataset(self, key):
        with self.connect() as db:
            row = db.execute("SELECT content FROM datasets WHERE id=?", (key,)).fetchone()
        if not row:
            raise KeyError("找不到資料集")
        return json.loads(row[0])

    def datasets(self):
        with self.connect() as db:
            rows = db.execute("SELECT * FROM datasets ORDER BY created_at ASC, rowid ASC").fetchall()
            jobs = db.execute("SELECT config FROM jobs").fetchall()
        uses = {}
        for job in jobs:
            config = json.loads(job["config"])
            uses.setdefault(config.get("dataset_id"), set()).add(config.get("analysis_date"))
        versions, summaries = {}, []
        for row in rows:
            cached = self._dataset_summary_cache.get(row["id"])
            if cached is None:
                content = json.loads(row["content"])
                prices, evidence = content["prices"], content["evidence"]
                evidence_by_domain = {domain: sum(item.get("domain") == domain for item in evidence)
                                      for domain in ("technical", "fundamental", "sentiment", "macro")}
                from .readiness import coverage
                cached = {
                    "coverage": coverage(content),
                    "kind": content.get("kind", "historical"),
                    "static": {key: value for key, value in content.items() if key not in ("prices", "evidence")},
                    "price_count": len(prices), "evidence_count": len(evidence),
                    "evidence_by_domain": evidence_by_domain,
                    "price_start": prices[0]["date"], "price_end": prices[-1]["date"],
                }
                self._dataset_summary_cache[row["id"]] = cached
            version_key = (row["ticker"], cached["kind"])
            versions[version_key] = versions.get(version_key, 0) + 1
            summaries.append({
                "coverage": cached["coverage"],
                "id": row["id"], "ticker": row["ticker"], "created_at": row["created_at"],
                **cached["static"],
                "version": versions[version_key], "price_count": cached["price_count"],
                "evidence_count": cached["evidence_count"],
                "evidence_by_domain": cached["evidence_by_domain"],
                "price_start": cached["price_start"], "price_end": cached["price_end"],
                "used_analysis_dates": sorted(day for day in uses.get(row["id"], set()) if day),
            })
        return list(reversed(summaries))

    def create(self, config):
        key, stamp = str(uuid4()), now()
        with self.connect() as db:
            db.execute("INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?)", (key, "queued", 1, json.dumps(config),
                json.dumps({"records": [], "research": {}, "trace": [], "attempts": []}), "", stamp, stamp))
        return self.get(key)

    @staticmethod
    def unpack(row):
        if not row:
            raise KeyError("找不到實驗")
        result = dict(row)
        result["config"] = json.loads(result["config"])
        result["state"] = json.loads(result["state"])
        return result

    def get(self, key):
        with self.connect() as db:
            return self.unpack(db.execute("SELECT * FROM jobs WHERE id=?", (key,)).fetchone())

    def jobs(self):
        with self.connect() as db:
            return [self.unpack(row) for row in db.execute("SELECT * FROM jobs ORDER BY created_at DESC")]

    def control(self, key, command):
        with self.connect() as db:
            job = self.unpack(db.execute("SELECT * FROM jobs WHERE id=?", (key,)).fetchone())
            if job["status"] in ("complete", "cancelled"):
                raise ValueError("已完成或取消的實驗不能變更；可建立新實驗")
            from .protocol import StudyProtocol
            if command == "resume" and job["config"]["protocol"].get("version") != StudyProtocol().version:
                raise ValueError("舊版實驗不能混用新版引擎；請使用複製至新版，原始紀錄會保留")
            wanted = int(command == "resume")
            # A pause request must be visible to the worker even when the job
            # is currently inside a model call.  Keeping status="running" for
            # pause made the UI report a running job forever and prevented a
            # clean resume after the call returned.
            if command == "cancel":
                status = "cancelled"
            elif command == "pause":
                status = "paused"
            else:
                status = "running" if job["status"] == "running" else "queued"
            db.execute("UPDATE jobs SET wants_run=?,status=?,updated_at=? WHERE id=?", (wanted, status, now(), key))

    def claim(self):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM jobs WHERE status='queued' AND wants_run=1 ORDER BY created_at LIMIT 1").fetchone()
            if not row:
                return None
            db.execute("UPDATE jobs SET status='running',updated_at=? WHERE id=?", (now(), row["id"]))
            job = self.unpack(row)
            from .protocol import StudyProtocol
            if job["config"]["protocol"].get("version") != StudyProtocol().version:
                db.execute("UPDATE jobs SET status='paused',wants_run=0,error=? WHERE id=?",
                           ("舊版實驗已隔離；請複製至新版重新執行", row["id"]))
                return None
            return job

    def save_step(self, key, state, error=""):
        with self.connect() as db:
            row = db.execute("SELECT wants_run,status,config,created_at FROM jobs WHERE id=?", (key,)).fetchone()
            status = "cancelled" if row["status"] == "cancelled" else "paused" if error else "complete" if state.get("finished") else "queued" if row["wants_run"] else "paused"
            db.execute("UPDATE jobs SET state=?,status=?,wants_run=?,error=?,updated_at=? WHERE id=?",
                (json.dumps(state, ensure_ascii=False, allow_nan=False), status, 0 if error else row["wants_run"], error, now(), key))
            if state.get("finished"):
                self._upsert_case_results(db, key, json.loads(row["config"]), state, row["created_at"])

    @staticmethod
    def _upsert_case_results(db, job_id, config, state, created_at):
        db.execute("DELETE FROM case_results WHERE job_id=?", (job_id,))
        degraded = int(bool(state.get("report", {}).get("degraded_research_domains")))
        for row in state.get("cases", []):
            db.execute("""INSERT OR REPLACE INTO case_results
                (job_id,protocol_hash,ticker,analysis_date,"group",horizon,cost_model,decision_layer,
                 maturity_date,action,correct,net_return,degraded,created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
                job_id, config.get("protocol_hash"), config.get("ticker"), config.get("analysis_date"), row.get("group"),
                row.get("horizon"), row.get("cost_model"), row.get("decision_layer", "gated"), row.get("maturity_date"),
                row.get("action"), None if row.get("correct") is None else int(bool(row.get("correct"))),
                row.get("net_return"), degraded, created_at))

    def backfill_case_results(self):
        """Idempotently index completed legacy jobs without rewriting their state JSON."""
        with self.connect() as db:
            rows = db.execute("SELECT id,config,state,created_at FROM jobs WHERE status='complete'").fetchall()
            for row in rows:
                exists = db.execute("SELECT 1 FROM case_results WHERE job_id=? LIMIT 1", (row["id"],)).fetchone()
                if exists:
                    continue
                state = json.loads(row["state"])
                if state.get("finished"):
                    self._upsert_case_results(db, row["id"], json.loads(row["config"]), state, row["created_at"])

    def memory(self, config, group):
        protocol = config.get("protocol", {})
        with self.connect() as db:
            rows = db.execute("""SELECT * FROM case_results
                WHERE protocol_hash=? AND ticker=? AND "group"=? AND horizon=? AND cost_model=?
                  AND decision_layer='gated' AND maturity_date < ? AND analysis_date < ? AND degraded=0
                ORDER BY analysis_date DESC, created_at ASC""", (
                config["protocol_hash"], config["ticker"], group, protocol.get("primary_horizon", 60),
                "corwin_schultz", config["analysis_date"], config["analysis_date"])).fetchall()
        unique = {}
        for row in rows:
            value = dict(row)
            value["correct"] = None if value["correct"] is None else bool(value["correct"])
            unique.setdefault(value["analysis_date"], value)
        return list(unique.values())[:20]

    def freeze(self, protocol_hash, dataset_ids):
        """Record the dataset IDs a study analyzed at the moment it was frozen.

        Freezing is a one-time, append-only action: once a protocol_hash is
        frozen, calling this again with a different dataset_id set raises,
        so a researcher cannot quietly widen the sample after seeing results.
        """
        dataset_ids = sorted(set(dataset_ids))
        with self.connect() as db:
            existing = db.execute("SELECT dataset_ids, frozen_at FROM preregistrations WHERE protocol_hash=?",
                                   (protocol_hash,)).fetchone()
            if existing:
                if json.loads(existing["dataset_ids"]) != dataset_ids:
                    raise ValueError("此協議已於 " + existing["frozen_at"] + " 凍結；不能改變已分析的資料集清單")
                return {"protocol_hash": protocol_hash, "dataset_ids": dataset_ids, "frozen_at": existing["frozen_at"]}
            stamp = now()
            db.execute("INSERT INTO preregistrations VALUES(?,?,?)",
                       (protocol_hash, json.dumps(dataset_ids), stamp))
            return {"protocol_hash": protocol_hash, "dataset_ids": dataset_ids, "frozen_at": stamp}

    def preregistration(self, protocol_hash):
        with self.connect() as db:
            row = db.execute("SELECT dataset_ids, frozen_at FROM preregistrations WHERE protocol_hash=?",
                              (protocol_hash,)).fetchone()
        if not row:
            return None
        return {"protocol_hash": protocol_hash, "dataset_ids": json.loads(row["dataset_ids"]), "frozen_at": row["frozen_at"]}
