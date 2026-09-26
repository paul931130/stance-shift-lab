import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

from research_service.settings import Settings


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        # Settings writes through to os.environ; isolate every test from it.
        self.env = patch.dict(os.environ, {}, clear=False)
        self.env.start()
        for key in ("FRED_API_KEY", "SEC_USER_AGENT"):
            os.environ.pop(key, None)

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_saved_values_apply_now_and_after_restart(self):
        Settings(self.tmp.name).save({"FRED_API_KEY": "  fred-secret  ", "SEC_USER_AGENT": "Lab lab@example.com"})
        self.assertEqual(os.environ["FRED_API_KEY"], "fred-secret")
        os.environ.pop("FRED_API_KEY")
        Settings(self.tmp.name)  # a fresh process loads the private file
        self.assertEqual(os.environ["FRED_API_KEY"], "fred-secret")

    def test_blank_keeps_and_clear_removes(self):
        settings = Settings(self.tmp.name)
        settings.save({"FRED_API_KEY": "fred-secret"})
        settings.save({"FRED_API_KEY": "   "})
        self.assertEqual(os.environ["FRED_API_KEY"], "fred-secret")
        settings.save({}, clear=["FRED_API_KEY"])
        self.assertEqual(os.environ["FRED_API_KEY"], "")

    def test_secrets_are_never_echoed(self):
        settings = Settings(self.tmp.name)
        settings.save({"FRED_API_KEY": "fred-secret", "SEC_USER_AGENT": "Lab lab@example.com"})
        fields = {field["name"]: field for field in settings.public()["fields"]}
        self.assertTrue(fields["FRED_API_KEY"]["configured"])
        self.assertNotIn("display_value", fields["FRED_API_KEY"])
        self.assertNotIn("fred-secret", json.dumps(settings.public()))
        self.assertEqual(fields["SEC_USER_AGENT"]["display_value"], "Lab lab@example.com")

    def test_invalid_input_is_rejected_without_writing(self):
        settings = Settings(self.tmp.name)
        for values, clear in (({"UNKNOWN": "x"}, []), ({"FRED_API_KEY": "a\nb"}, []),
                              ({"FRED_API_KEY": "x" * 2001}, []), ({}, ["UNKNOWN"]), ({"FRED_API_KEY": 1}, [])):
            with self.assertRaises(ValueError):
                settings.save(values, clear)
        self.assertFalse(settings.path.exists())

    @unittest.skipIf(os.name == "nt", "POSIX file modes only")
    def test_private_file_is_owner_only(self):
        settings = Settings(self.tmp.name)
        settings.save({"FRED_API_KEY": "fred-secret"})
        self.assertEqual(stat.S_IMODE(Path(settings.path).stat().st_mode), 0o600)


if __name__ == "__main__":
    unittest.main()
