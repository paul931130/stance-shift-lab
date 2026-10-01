import unittest

from research_service.labels import gate_reasons, ljust, pct, ratio_pct, rjust, width


class LabelTests(unittest.TestCase):
    def test_gate_reasons_are_translated_and_unknown_codes_kept(self):
        self.assertEqual(gate_reasons(["missing_research_domains", "confidence_below_0.55", "new_code"]),
                         "資料面向不齊、信心低於 0.55、new_code")
        self.assertEqual(gate_reasons([]), "—")

    def test_percent_formats(self):
        self.assertEqual((pct(4), pct(-4, sign=True), pct(None)), ("4.0%", "-4.0%", "—"))
        self.assertEqual(ratio_pct(0.034183822345738246), "+3.42%")

    def test_padding_counts_wide_characters_as_two_columns(self):
        self.assertEqual(width("C 固定立場辯論"), 14)
        self.assertEqual(width(ljust("組別", 6)), 6)
        self.assertEqual(rjust("+4.0%", 8), "   +4.0%")


if __name__ == "__main__":
    unittest.main()
