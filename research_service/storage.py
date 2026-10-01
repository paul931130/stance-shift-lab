import json
from pathlib import Path
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from tempfile import TemporaryDirectory
from uuid import uuid4

from .errors import NotFoundError


def now():
    return datetime.now(timezone.utc).isoformat()


class JobLeaseLost(RuntimeError):
    """Another process took over the job; this process must not write its state."""


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
                CREATE INDEX IF NOT EXISTS idx_jobs_protocol
                    ON jobs(json_extract(config, '$.protocol_hash'));
                CREATE TABLE IF NOT EXISTS services(id TEXT PRIMARY KEY, heartbeat_at TEXT);
                CREATE TABLE IF NOT EXISTS preregistrations(
                    protocol_hash TEXT PRIMARY KEY, dataset_ids TEXT, frozen_at TEXT);
                -- The exact case requests a study was registered with, so it can be
                -- queued later in one step (older registrations may lack this).
                CREATE TABLE IF NOT EXISTS preregistration_cases(
                    protocol_hash TEXT PRIMARY KEY, cases TEXT, saved_at TEXT);
                -- Which protocol version/model/design a registration is for, so a study can be
                -- labelled (current or old) before any of its jobs exist.
                CREATE TABLE IF NOT EXISTS preregistration_meta(
                    protocol_hash TEXT PRIMARY KEY, version TEXT, model TEXT, design TEXT);
            """)
            self._ensure_steps_column(db)
            self._ensure_owner_column(db)
        self.backfill_case_results()

    @staticmethod
    def _ensure_owner_column(db):
        """Who is running a job: 'worker' (web service) or 'cli:<token>' (CLI / Python API)."""
        columns = {row["name"] for row in db.execute("PRAGMA table_info(jobs)")}
        if "owner" not in columns:
            db.execute("ALTER TABLE jobs ADD COLUMN owner TEXT NOT NULL DEFAULT ''")

    @staticmethod
    def _ensure_steps_column(db):
        """Keep a model-output count beside the state JSON.

        The dashboard polls the job list every few seconds; reading this column
        avoids parsing every job's full state just to count its records.
        """
        columns = {row["name"] for row in db.execute("PRAGMA table_info(jobs)")}
        if "steps" in columns:
            return
        db.execute("ALTER TABLE jobs ADD COLUMN steps INTEGER NOT NULL DEFAULT 0")
        for row in db.execute("SELECT id, state FROM jobs").fetchall():
            db.execute("UPDATE jobs SET steps=? WHERE id=?",
                       (len(json.loads(row["state"]).get("records", [])), row["id"]))

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def heartbeat(self, service_id):
        """Record that a web service instance (and its worker) is alive."""
        with self.connect() as db:
            db.execute("INSERT INTO services(id, heartbeat_at) VALUES(?, ?) "
                       "ON CONFLICT(id) DO UPDATE SET heartbeat_at=excluded.heartbeat_at", (service_id, now()))

    def active_job_count(self):
        """Jobs that still need the model: queued or currently running."""
        with self.connect() as db:
            return db.execute("SELECT COUNT(*) FROM jobs WHERE status IN ('queued','running')").fetchone()[0]

    def recover(self, dead_before, idle_before):
        """Pause worker jobs whose service stopped; never touch a live service's or a CLI's job.

        A job claimed by ``worker:<id>`` is orphaned once that service's
        heartbeat is older than ``dead_before``. Jobs claimed before owners were
        recorded (owner '' or 'worker') are orphaned once not updated since
        ``idle_before``. CLI leases expire on their own (see acquire).
        """
        with self.connect() as db:
            return db.execute("""UPDATE jobs SET status='paused', wants_run=0, owner='',
                error='研究服務曾重新啟動；已完成的步驟都保留，請按「繼續執行」'
                WHERE status='running' AND owner NOT LIKE 'cli:%' AND (
                    (owner LIKE 'worker:%' AND substr(owner, 8) NOT IN
                        (SELECT id FROM services WHERE heartbeat_at >= ?))
                    OR (owner IN ('', 'worker') AND updated_at < ?))""",
                (dead_before, idle_before)).rowcount

    def backup_bytes(self):
        """Return a WAL-safe SQLite snapshot without stopping the research worker."""
        with TemporaryDirectory(prefix="stance-shift-backup-") as directory:
            target_path = Path(directory) / "research.sqlite3"
            # sqlite3.Connection is a transaction context manager, not a
            # resource context manager: ``with connect(...)`` commits but does
            # not close the handle.  Close both handles explicitly so Windows
            # can remove the temporary WAL/snapshot files on context exit.
            source = sqlite3.connect(self.path, timeout=30)
            target = sqlite3.connect(target_path)
            try:
                source.backup(target)
            finally:
                target.close()
                source.close()
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
            raise NotFoundError("找不到資料集")
        return json.loads(row[0])

    def datasets(self):
        with self.connect() as db:
            rows = db.execute("SELECT id, ticker, created_at FROM datasets ORDER BY created_at ASC, rowid ASC").fetchall()
            uncached = [row["id"] for row in rows if row["id"] not in self._dataset_summary_cache]
            contents = {}
            # One query per chunk instead of one per dataset on a cold cache.
            for start in range(0, len(uncached), 500):
                chunk = uncached[start:start + 500]
                marks = ",".join("?" * len(chunk))
                contents.update(db.execute(f"SELECT id, content FROM datasets WHERE id IN ({marks})", chunk).fetchall())
            jobs = db.execute("SELECT config FROM jobs").fetchall()
        uses = {}
        for job in jobs:
            config = json.loads(job["config"])
            uses.setdefault(config.get("dataset_id"), set()).add(config.get("analysis_date"))
        versions, summaries = {}, []
        for row in rows:
            cached = self._dataset_summary_cache.get(row["id"])
            if cached is None:
                content = json.loads(contents[row["id"]])
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

    def create(self, config, queued=True):
        """Store a new job; ``queued=False`` creates it paused so no worker claims it."""
        key, stamp = str(uuid4()), now()
        with self.connect() as db:
            db.execute("""INSERT INTO jobs(id,status,wants_run,config,state,error,created_at,updated_at,steps)
                VALUES(?,?,?,?,?,?,?,?,0)""", (key, "queued" if queued else "paused", int(queued), json.dumps(config),
                json.dumps({"records": [], "research": {}, "trace": [], "attempts": []}), "", stamp, stamp))
        return self.get(key)

    @staticmethod
    def unpack(row):
        if not row:
            raise NotFoundError("找不到實驗")
        result = dict(row)
        result["config"] = json.loads(result["config"])
        result["state"] = json.loads(result["state"])
        return result

    def get(self, key):
        with self.connect() as db:
            return self.unpack(db.execute("SELECT * FROM jobs WHERE id=?", (key,)).fetchone())

    def jobs(self, protocol_hash=None):
        """Full jobs, optionally only one protocol's; study pages never need other protocols' state JSON."""
        with self.connect() as db:
            if protocol_hash is None:
                rows = db.execute("SELECT * FROM jobs ORDER BY created_at DESC")
            else:
                rows = db.execute("""SELECT * FROM jobs WHERE json_extract(config, '$.protocol_hash')=?
                    ORDER BY created_at DESC""", (protocol_hash,))
            return [self.unpack(row) for row in rows]

    def study_rows(self, protocol_hash):
        """One protocol's jobs without state JSON: enough to show batch progress cheaply."""
        with self.connect() as db:
            rows = db.execute("""SELECT id, status, error, created_at, updated_at, steps,
                    json_extract(config, '$.ticker') AS ticker,
                    json_extract(config, '$.analysis_date') AS analysis_date,
                    json_extract(config, '$.dataset_id') AS dataset_id,
                    json_extract(config, '$.protocol.version') AS version,
                    json_extract(config, '$.protocol.model') AS model,
                    json_extract(config, '$.protocol.design') AS design
                FROM jobs WHERE json_extract(config, '$.protocol_hash')=?""", (protocol_hash,)).fetchall()
        return [dict(row) for row in rows]

    def preregistrations(self):
        with self.connect() as db:
            rows = db.execute("SELECT protocol_hash, dataset_ids, frozen_at FROM preregistrations "
                              "ORDER BY frozen_at DESC").fetchall()
        return [{"protocol_hash": row["protocol_hash"], "cases": len(json.loads(row["dataset_ids"])),
                 "frozen_at": row["frozen_at"]} for row in rows]

    def job_summaries(self):
        """Job list without the state JSON, for the frequently polled dashboard."""
        with self.connect() as db:
            rows = db.execute("""SELECT id,status,config,error,updated_at,steps,wants_run
                FROM jobs ORDER BY created_at DESC""").fetchall()
        return [{**dict(row), "config": json.loads(row["config"])} for row in rows]

    def control(self, key, command):
        with self.connect() as db:
            job = self.unpack(db.execute("SELECT * FROM jobs WHERE id=?", (key,)).fetchone())
            if job["status"] in ("complete", "cancelled"):
                raise ValueError("已完成或取消的實驗不能變更；可建立新實驗")
            from .protocol import protocol_is_current
            if command == "resume" and not protocol_is_current(job["config"]["protocol"]):
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
            # A previous provider failure should not remain attached to a
            # deliberately resumed job; otherwise the UI shows a stale error
            # while the worker is already progressing again.
            db.execute("UPDATE jobs SET wants_run=?,status=?,error=?,updated_at=? WHERE id=?",
                       (wanted, status, "" if command == "resume" else job.get("error", ""), now(), key))

    def acquire(self, key, owner, stale_before):
        """Atomically give ``owner`` the right to run a paused or queued job; True when granted.

        A CLI lease not refreshed since ``stale_before`` (its process was killed)
        can be taken over; a job the web worker is running never can.
        """
        with self.connect() as db:
            changed = db.execute("""UPDATE jobs SET status='running', wants_run=0, owner=?, error='', updated_at=?
                WHERE id=? AND (status IN ('paused', 'queued')
                                OR (status='running' AND owner LIKE 'cli:%' AND updated_at < ?))""",
                (owner, now(), key, stale_before)).rowcount
        return changed == 1

    def release(self, key, owner):
        """Give up a lease that is still held (e.g. the CLI was interrupted)."""
        with self.connect() as db:
            db.execute("UPDATE jobs SET status='paused', owner='', updated_at=? WHERE id=? AND owner=? AND status='running'",
                       (now(), key, owner))

    def claim(self, owner="worker"):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            # Run cases in analysis-date order, not submission order. A case's
            # memory only contains earlier matured cases of the same protocol,
            # so processing earlier dates first makes that memory independent
            # of the order in which a batch happened to be queued.
            row = db.execute("""SELECT * FROM jobs WHERE status='queued' AND wants_run=1
                ORDER BY json_extract(config, '$.analysis_date'), created_at LIMIT 1""").fetchone()
            if not row:
                return None
            db.execute("UPDATE jobs SET status='running',owner=?,updated_at=? WHERE id=?", (owner, now(), row["id"]))
            job = self.unpack(row)
            from .protocol import protocol_is_current
            if not protocol_is_current(job["config"]["protocol"]):
                db.execute("UPDATE jobs SET status='paused',wants_run=0,error=? WHERE id=?",
                           ("舊版實驗已隔離；請複製至新版重新執行", row["id"]))
                return None
            return job

    def save_step(self, key, state, error="", owner=None):
        """Persist one step. With ``owner`` (a CLI lease) the write happens only while that lease is held."""
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT wants_run,status,config,created_at,owner FROM jobs WHERE id=?", (key,)).fetchone()
            if owner is None:
                status = "cancelled" if row["status"] == "cancelled" else "paused" if error else "complete" if state.get("finished") else "queued" if row["wants_run"] else "paused"
                wants_run = 0 if error else row["wants_run"]
            else:
                if row["owner"] != owner:
                    raise JobLeaseLost("此實驗的執行權已被其他程序取走；本次結果未寫入")
                # Keep the lease while the job runs; a pause or cancel pressed
                # in the web UI ends it after this step.
                status = ("cancelled" if row["status"] == "cancelled" else "paused" if error
                          else "complete" if state.get("finished") else "running" if row["status"] == "running"
                          else "paused")
                wants_run = 0
            db.execute("UPDATE jobs SET state=?,status=?,wants_run=?,error=?,updated_at=?,steps=?,owner=? WHERE id=?",
                (json.dumps(state, ensure_ascii=False, allow_nan=False), status, wants_run, error, now(),
                 len(state.get("records", [])), owner if owner is not None and status == "running" else "", key))
            # A job cancelled during its final step must not feed memory or statistics.
            if state.get("finished") and status == "complete":
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

    def memory_audit(self, config):
        """Earlier same-ticker cases of this protocol that were unfinished when memory was frozen.

        Date-ordered scheduling prevents this for batches, but a case can still
        start before an earlier one is added or resumed. Recording it keeps any
        order-dependent memory visible in the job state and its export.
        """
        with self.connect() as db:
            rows = db.execute("""SELECT id, status, json_extract(config, '$.analysis_date') AS analysis_date
                FROM jobs WHERE json_extract(config, '$.protocol_hash')=? AND json_extract(config, '$.ticker')=?
                  AND json_extract(config, '$.analysis_date') < ? AND status NOT IN ('complete', 'cancelled')
                ORDER BY analysis_date, created_at""",
                (config["protocol_hash"], config["ticker"], config["analysis_date"])).fetchall()
        return {"rule": "memory uses earlier matured cases of the same protocol and ticker; "
                        "cases are scheduled by analysis date",
                "pending_earlier_cases": [dict(row) for row in rows]}

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
                    raise ValueError("研究樣本已於 " + existing["frozen_at"] + " 鎖定，不能再變更")
                return {"protocol_hash": protocol_hash, "dataset_ids": dataset_ids, "frozen_at": existing["frozen_at"]}
            stamp = now()
            db.execute("INSERT INTO preregistrations VALUES(?,?,?)",
                       (protocol_hash, json.dumps(dataset_ids), stamp))
            return {"protocol_hash": protocol_hash, "dataset_ids": dataset_ids, "frozen_at": stamp}

    def save_registered_cases(self, protocol_hash, cases):
        """Keep the first case list a study was registered or queued with; later calls never replace it."""
        with self.connect() as db:
            db.execute("INSERT OR IGNORE INTO preregistration_cases VALUES(?,?,?)",
                       (protocol_hash, json.dumps(cases, ensure_ascii=False), now()))

    def save_registration_meta(self, protocol_hash, version, model, design):
        with self.connect() as db:
            db.execute("INSERT OR IGNORE INTO preregistration_meta VALUES(?,?,?,?)",
                       (protocol_hash, version, model, design))

    def registration_meta(self, protocol_hash):
        with self.connect() as db:
            row = db.execute("SELECT version, model, design FROM preregistration_meta WHERE protocol_hash=?",
                             (protocol_hash,)).fetchone()
        return dict(row) if row else None

    def registered_cases(self, protocol_hash):
        with self.connect() as db:
            row = db.execute("SELECT cases FROM preregistration_cases WHERE protocol_hash=?",
                             (protocol_hash,)).fetchone()
        return json.loads(row["cases"]) if row else None

    def preregistration(self, protocol_hash):
        with self.connect() as db:
            row = db.execute("SELECT dataset_ids, frozen_at FROM preregistrations WHERE protocol_hash=?",
                              (protocol_hash,)).fetchone()
        if not row:
            return None
        return {"protocol_hash": protocol_hash, "dataset_ids": json.loads(row["dataset_ids"]), "frozen_at": row["frozen_at"]}
