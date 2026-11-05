"""Experimental debate clash (StudyProtocol.debate_clash): prompts, schema, checks, hash safety."""
import unittest

from research_service.engine import clash_context
from research_service.models import messages_for, output_schema_for, validate_clash
from research_service.protocol import StudyProtocol, decision_plan

REPORT = {"ticker": "NVDA", "base_rates": {"hold_band_pct": 2.0}, "research": {}, "evidence": []}
OPPONENT = {"rationale": "Revenue declined year over year, which signals weakening demand for the core product."}
OWN = {"rationale": "Net income rose sharply and sentiment is positive, so the stock should outperform."}


def protocol(**overrides):
    return StudyProtocol(model="ollama/demo", dataset_kind="synthetic", bootstrap_replicates=199, **overrides)


def call(p, key):
    return next(item for item in decision_plan(p) if item.key == key)


def record(key, group, agent, round_number, output):
    return {"key": key, "group": group, "kind": "debate", "agent": agent, "round": round_number,
            "stance": "BULL" if agent == "agent-a" else "BEAR", "output": output}


class DebateClashTests(unittest.TestCase):
    def test_off_by_default_and_hash_unchanged(self):
        self.assertEqual(protocol().fingerprint, protocol(debate_clash=False).fingerprint)
        self.assertNotEqual(protocol().fingerprint, protocol(debate_clash=True).fingerprint)
        prompt = messages_for(call(protocol(), "c-r2-agent-a"), REPORT, [], [], protocol())[0]["content"]
        self.assertNotIn("Round role", prompt)
        self.assertNotIn("Clash turn", prompt)

    def test_requires_evidence_reference_version(self):
        with self.assertRaises(ValueError):
            protocol(version="v3-1002.2", debate_clash=True)

    def test_round_roles_and_clash_schema(self):
        p = protocol(debate_clash=True)
        first = messages_for(call(p, "c-r1-agent-a"), REPORT, [], [], p)
        self.assertIn("OPENING", first[0]["content"])
        self.assertNotIn("Clash turn", first[0]["content"])
        self.assertNotIn("rebutted_opponent_claim", output_schema_for(first)["required"])
        for key, role in (("c-r2-agent-a", "REBUTTAL"), ("c-r3-agent-b", "CLOSING"), ("d-r3-agent-a", "CLOSING")):
            messages = messages_for(call(p, key), REPORT, [], [], p)
            self.assertIn(role, messages[0]["content"])
            self.assertIn("rebutted_opponent_claim", output_schema_for(messages)["required"])
        switched = messages_for(call(p, "d-r2-agent-a"), REPORT, [], [], p)
        self.assertNotIn("Clash turn", switched[0]["content"])
        self.assertNotIn("rebutted_opponent_claim", output_schema_for(switched)["required"])

    def test_quote_must_come_from_counterpart_and_rationale_must_be_new(self):
        good = {"rebutted_opponent_claim": "Revenue declined year over year, which signals weakening demand",
                "rationale": "The revenue dip is a one-off; operating cash flow and margins point the other way."}
        validate_clash(dict(good), OPPONENT, OWN)
        for bad in ({**good, "rebutted_opponent_claim": "Margins are collapsing across every segment"},
                    {**good, "rebutted_opponent_claim": "demand"},
                    {**good, "rationale": OWN["rationale"]}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                validate_clash(dict(bad), OPPONENT, OWN)

    def test_clash_context_skips_opening_and_isolated_switch_round(self):
        p = protocol(debate_clash=True)
        records = [record("c-r1-agent-a", "C", "agent-a", 1, OWN), record("c-r1-agent-b", "C", "agent-b", 1, OPPONENT),
                   record("d-r1-agent-a", "D", "agent-a", 1, OWN), record("d-r1-agent-b", "D", "agent-b", 1, OPPONENT)]
        self.assertIsNone(clash_context(p, call(p, "c-r1-agent-a"), records))
        self.assertIsNone(clash_context(p, call(p, "d-r2-agent-a"), records))
        self.assertIsNone(clash_context(protocol(), call(protocol(), "c-r2-agent-a"), records))
        self.assertEqual(clash_context(p, call(p, "c-r2-agent-a"), records), (OPPONENT, OWN))
        with self.assertRaises(ValueError):
            clash_context(p, call(p, "c-r3-agent-a"), records)

    def test_d_round_three_rebuts_the_switched_turn_on_the_other_side(self):
        p = protocol(debate_clash=True)
        switched_a = {"rationale": "Revenue fell, so the bull case no longer holds and the stock should drop."}
        switched_b = {"rationale": "Cash flow is strong, so the bear case no longer holds and the stock should rise."}
        records = [dict(record("d-r2-agent-a", "D", "agent-a", 2, switched_a), stance="BEAR"),
                   dict(record("d-r2-agent-b", "D", "agent-b", 2, switched_b), stance="BULL")]
        # agent-a argues BULL again in round 3; the round-2 BEAR turn was its own switched turn.
        self.assertEqual(clash_context(p, call(p, "d-r3-agent-a"), records), (switched_a, switched_a))
        self.assertEqual(clash_context(p, call(p, "d-r3-agent-b"), records), (switched_b, switched_b))
        prompt = messages_for(call(p, "d-r3-agent-a"), REPORT, [], [], p)[0]["content"]
        self.assertIn("argued BEAR", prompt)


if __name__ == "__main__":
    unittest.main()
