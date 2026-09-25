import csv
import tempfile
import unittest
import zipfile
from pathlib import Path

from scripts.append_fnspid_ticker import append_tickers

RAW_HEADER = ["Unnamed: 0", "Date", "Article_title", "Stock_symbol", "Url", "Publisher", "Author", "Article"]
TARGET_HEADER = ["date", "symbol", "headline", "article", "publisher", "url"]


def write_csv(path, header, rows):
    with Path(path).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


class AppendFnspidTickerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.raw = self.dir / "raw.csv"
        write_csv(self.raw, RAW_HEADER, [
            [0, "2022-03-01 00:00:00 UTC", "Intel headline, with comma", "INTC", "https://x/1", "Pub", "", "Body"],
            [1, "2021-01-05 00:00:00 UTC", "Apple headline", "AAPL", "https://x/2", "Pub", "", "Body"],
            [2, "2021-02-01 00:00:00 UTC", "Earlier Intel headline", "INTC", "https://x/3", "", "", ""],
        ])
        self.target = self.dir / "Stock_news.csv"
        write_csv(self.target, TARGET_HEADER, [
            ["2021-01-05 00:00:00 UTC", "AAPL", "Apple headline", "Body", "Pub", "https://x/2"]])

    def tearDown(self):
        self.tmp.cleanup()

    def test_appends_only_the_requested_ticker_in_the_target_columns(self):
        before = self.target.read_bytes()
        result = append_tickers(self.raw, self.target, ["INTC"], progress_every=0)
        self.assertEqual(result["appended"], 2)
        self.assertEqual(Path(result["backup"]).read_bytes(), before)
        self.assertTrue(self.target.read_bytes().startswith(before))
        with self.target.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual([row["symbol"] for row in rows], ["AAPL", "INTC", "INTC"])
        self.assertEqual(rows[1]["headline"], "Earlier Intel headline")
        self.assertEqual(rows[2]["headline"], "Intel headline, with comma")

    def test_reads_a_single_csv_from_inside_a_zip(self):
        archive = self.dir / "raw.zip"
        with zipfile.ZipFile(archive, "w") as handle:
            handle.write(self.raw, "nested/raw_stock_news.csv")
        result = append_tickers(archive, self.target, ["INTC"], progress_every=0)
        self.assertEqual(result["appended"], 2)

    def test_refuses_to_duplicate_rows_and_unapproved_tickers(self):
        append_tickers(self.raw, self.target, ["INTC"], progress_every=0)
        with self.assertRaisesRegex(ValueError, "already contains"):
            append_tickers(self.raw, self.target, ["INTC"], progress_every=0)
        with self.assertRaisesRegex(ValueError, "approved study universe"):
            append_tickers(self.raw, self.target, ["TSLA"], progress_every=0)


if __name__ == "__main__":
    unittest.main()
