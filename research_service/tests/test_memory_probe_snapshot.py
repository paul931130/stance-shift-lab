import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from contextlib import closing

from scripts.memory_probe import SnapshotReader


class ProbeSnapshotTests(unittest.TestCase):
    def test_legacy_schema_is_read_without_migration_or_modification(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "research.sqlite3"
            with sqlite3.connect(path) as db:
                db.execute("CREATE TABLE jobs (config TEXT, created_at TEXT)")
                db.execute("CREATE TABLE datasets (id TEXT, content TEXT)")
                db.execute("INSERT INTO jobs VALUES (?,?)", (json.dumps({"ticker": "NVDA"}), "2024"))
                db.execute("INSERT INTO datasets VALUES (?,?)", ("one", json.dumps({"prices": []})))
            db.close()
            before = hashlib.sha256(path.read_bytes()).hexdigest()
            reader = SnapshotReader(root)
            self.assertEqual(reader.job_summaries(), [{"config": {"ticker": "NVDA"}}])
            self.assertEqual(reader.dataset("one"), {"prices": []})
            with self.assertRaises(sqlite3.OperationalError):
                with closing(reader.connect()) as db:
                    db.execute("CREATE TABLE forbidden (x)")
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), before)
            self.assertEqual({p.name for p in Path(root).iterdir()}, {"research.sqlite3"})

    def test_active_wal_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "research.sqlite3"
            path.touch()
            Path(str(path) + "-wal").touch()
            with self.assertRaisesRegex(ValueError, "WAL"):
                SnapshotReader(root)
