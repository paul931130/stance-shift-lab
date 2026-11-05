"""Experimental debate clash (StudyProtocol.debate_clash): prompts, schema, checks, hash safety."""
import unittest

from research_service.engine import clash_context, clash_verdict_turns
from research_service.models import (counterpoint_required, messages_for, output_schema_for, validate_clash,
                                     validate_clash_verdicts)
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

    def test_closing_may_answer_an_earlier_opposing_turn(self):
        later = {"rationale": "Leverage stays high, so the cash flow gains will not protect the equity holders."}
        good = {"rebutted_opponent_claim": "Revenue declined year over year, which signals weakening demand",
                "rationale": "The revenue dip is a one-off; operating cash flow and margins point the other way."}
        validate_clash(dict(good), [OPPONENT, later], OWN)
        with self.assertRaises(ValueError):
            validate_clash(dict(good), [later], OWN)

    def test_clash_context_skips_opening_and_isolated_switch_round(self):
        p = protocol(debate_clash=True)
        records = [record("c-r1-agent-a", "C", "agent-a", 1, OWN), record("c-r1-agent-b", "C", "agent-b", 1, OPPONENT),
                   record("d-r1-agent-a", "D", "agent-a", 1, OWN), record("d-r1-agent-b", "D", "agent-b", 1, OPPONENT)]
        self.assertIsNone(clash_context(p, call(p, "c-r1-agent-a"), records))
        self.assertIsNone(clash_context(p, call(p, "d-r2-agent-a"), records))
        self.assertIsNone(clash_context(protocol(), call(protocol(), "c-r2-agent-a"), records))
        self.assertEqual(clash_context(p, call(p, "c-r2-agent-a"), records), ([OPPONENT], OWN))
        with self.assertRaises(ValueError):
            clash_context(p, call(p, "c-r3-agent-a"), records)

    def test_d_round_three_rebuts_the_switched_turn_on_the_other_side(self):
        p = protocol(debate_clash=True)
        switched_a = {"rationale": "Revenue fell, so the bull case no longer holds and the stock should drop."}
        switched_b = {"rationale": "Cash flow is strong, so the bear case no longer holds and the stock should rise."}
        records = [dict(record("d-r2-agent-a", "D", "agent-a", 2, switched_a), stance="BEAR"),
                   dict(record("d-r2-agent-b", "D", "agent-b", 2, switched_b), stance="BULL")]
        # agent-a argues BULL again in round 3; the round-2 BEAR turn was its own switched turn.
        self.assertEqual(clash_context(p, call(p, "d-r3-agent-a"), records), ([switched_a], switched_a))
        self.assertEqual(clash_context(p, call(p, "d-r3-agent-b"), records), ([switched_b], switched_b))
        with_round1 = records + [record("d-r1-agent-b", "D", "agent-b", 1, OPPONENT)]
        self.assertEqual(clash_context(p, call(p, "d-r3-agent-a"), with_round1)[0], [OPPONENT, switched_a])
        prompt = messages_for(call(p, "d-r3-agent-a"), REPORT, [], [], p)[0]["content"]
        self.assertIn("argued BEAR", prompt)


    def test_no_counterpoint_after_opening_under_clash(self):
        on, off = protocol(debate_clash=True), protocol()
        for p, key, required in ((on, "c-r1-agent-a", True), (on, "c-r2-agent-a", False), (on, "d-r2-agent-b", False),
                                 (on, "d-r3-agent-a", False), (off, "c-r2-agent-a", True), (off, "d-r3-agent-a", True)):
            with self.subTest(clash=bool(p.debate_clash), key=key):
                messages = messages_for(call(p, key), REPORT, [], [], p)
                self.assertEqual(counterpoint_required(p, call(p, key)), required)
                self.assertEqual("strongest_counterpoint" in output_schema_for(messages)["required"], required)
                if p.debate_clash and not required:
                    self.assertNotIn("strongest_counterpoint", output_schema_for(messages)["properties"])

    def test_switch_quote_limit_is_longer_only_under_clash(self):
        for p, limit in ((protocol(debate_clash=True), 400), (protocol(), 240)):
            messages = messages_for(call(p, "d-r2-agent-a"), REPORT, [], [], p)
            self.assertEqual(output_schema_for(messages)["properties"]["rebutted_claim"]["maxLength"], limit)

    def test_adjudicator_rules_on_every_clash_turn(self):
        p = protocol(debate_clash=True)
        judge = call(p, "c-adjudication")
        messages = messages_for(judge, REPORT, [], [], p)
        self.assertIn("clash_verdicts", output_schema_for(messages)["required"])
        plain = messages_for(call(protocol(), "c-adjudication"), REPORT, [], [], protocol())
        self.assertNotIn("clash_verdicts", output_schema_for(plain)["required"])
        quoted = {"rationale": "x", "rebutted_opponent_claim": "Revenue declined year over year"}
        records = [record("c-r1-agent-a", "C", "agent-a", 1, OWN), record("c-r2-agent-a", "C", "agent-a", 2, quoted),
                   record("c-r2-agent-b", "C", "agent-b", 2, quoted), record("d-r3-agent-a", "D", "agent-a", 3, quoted)]
        turns = clash_verdict_turns(p, judge, records)
        self.assertEqual(turns, ["c-r2-agent-a", "c-r2-agent-b"])
        listed = messages_for(judge, REPORT, records, [], p)[0]["content"]
        self.assertIn('the clash turns are ["c-r2-agent-a", "c-r2-agent-b"]', listed)
        self.assertIsNone(clash_verdict_turns(protocol(), judge, records))
        def verdict(key):
            return {"turn": key, "supports": "BULL", "reason": "Cash flow outweighs the revenue dip."}
        validate_clash_verdicts({"clash_verdicts": [verdict(k) for k in turns]}, turns)
        for bad in ([verdict("c-r2-agent-a")], [verdict(k) for k in turns] + [verdict("c-r2-agent-a")],
                    [verdict("c-r3-agent-a"), verdict("c-r2-agent-b")]):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                validate_clash_verdicts({"clash_verdicts": bad}, turns)

    def test_rq3_domain_debate_refuses_debate_clash_until_wired(self):
        import json
        import tempfile
        from pathlib import Path
        from research_service.tests import test_design_pilot
        from scripts.run_design_pilot import run
        with tempfile.TemporaryDirectory() as directory:
            args = test_design_pilot.DesignPilotTests().setup_run(Path(directory), rq3=True)
            raw = json.loads(args.cases.read_text(encoding="utf-8"))
            raw["cases"][0]["debate_clash"] = True
            args.cases.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaisesRegex(Exception, "debate_clash"):
                run(args)

if __name__ == "__main__":
    unittest.main()
