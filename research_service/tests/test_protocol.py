import unittest
from dataclasses import FrozenInstanceError, asdict, replace

from research_service.protocol import StudyProtocol, cases, decision_plan, decision_wave, visible_history, is_switched


class ProtocolTests(unittest.TestCase):
    def test_primary_plan_is_compute_matched_and_immutable(self):
        protocol = StudyProtocol()
        plan = decision_plan(protocol)
        self.assertEqual({group: sum(call.group == group for call in plan) for group in "ABCD"}, {"A": 1, "B": 7, "C": 7, "D": 7})
        self.assertTrue(protocol.compute_matched)
        self.assertEqual(protocol.fingerprint, StudyProtocol(**asdict(protocol)).fingerprint)
        self.assertNotEqual(protocol.fingerprint, replace(protocol, voting_samples=5).fingerprint)
        self.assertEqual((protocol.version, protocol.missing_data_policy), ("v3-0913.1", "allow_decision"))
        self.assertNotEqual(protocol.fingerprint, replace(protocol, missing_data_policy="force_no_trade").fingerprint)
        StudyProtocol(version="v3-0905.1", missing_data_policy="force_no_trade")
        with self.assertRaises(ValueError):
            StudyProtocol(version="v3-0905.1", missing_data_policy="allow_decision")
        with self.assertRaises(FrozenInstanceError):
            protocol.model = "changed"

    def test_swaps_only_second_round(self):
        plan = decision_plan(StudyProtocol())
        self.assertEqual([call.stance for call in plan if call.group == "D" and call.kind == "debate"], ["BULL", "BEAR", "BEAR", "BULL", "BULL", "BEAR"])
        self.assertEqual([call.stance for call in plan if call.group == "C" and call.kind == "debate"], ["BULL", "BEAR"] * 3)

    def test_b_independence_and_same_round_information_symmetry(self):
        plan = decision_plan(StudyProtocol())
        records = [asdict(call) for call in plan]
        self.assertTrue(all(visible_history(call, records, StudyProtocol()) == [] for call in plan if call.group == "B"))
        for round_number in (1, 2, 3):
            pair = [call for call in plan if call.group == "D" and call.round == round_number]
            self.assertEqual(visible_history(pair[0], records, StudyProtocol()), visible_history(pair[1], records, StudyProtocol()))
            self.assertEqual(len(visible_history(pair[0], records, StudyProtocol())), 0 if round_number == 2 else 2 * (round_number - 1))

    def test_switch_round_isolated_without_changing_control_or_adjudication(self):
        enabled, disabled = StudyProtocol(), StudyProtocol(switch_isolation=False)
        plan = decision_plan(enabled)
        records = [asdict(call) for call in plan if call.kind == "debate"]
        d2 = next(call for call in plan if call.key == "d-r2-agent-a")
        c2 = next(call for call in plan if call.key == "c-r2-agent-a")
        d3 = next(call for call in plan if call.key == "d-r3-agent-a")
        adjudication = next(call for call in plan if call.key == "d-adjudication")
        self.assertTrue(is_switched(enabled, d2))
        self.assertFalse(is_switched(enabled, c2))
        self.assertEqual(visible_history(d2, records, enabled), [])
        self.assertEqual(len(visible_history(d2, records, disabled)), 2)
        self.assertEqual(len(visible_history(c2, records, enabled)), 2)
        self.assertEqual(len(visible_history(c2, records, disabled)), 2)
        self.assertEqual(len(visible_history(d3, records, enabled)), 4)
        self.assertEqual(len(visible_history(adjudication, records, enabled)), 6)

    def test_sample_universe_and_primary_endpoint(self):
        self.assertEqual(len(cases()), 180)
        self.assertEqual(len(set(cases())), 180)
        with self.assertRaises(ValueError):
            StudyProtocol(primary_horizon=30)
        with self.assertRaises(ValueError):
            StudyProtocol(max_rounds=2)
        self.assertFalse(StudyProtocol(voting_samples=5).compute_matched)
        with self.assertRaisesRegex(ValueError, "參數量過小"):
            StudyProtocol(model="ollama/gemma3:4b")
        self.assertEqual(StudyProtocol(model="ollama/gemma3:4b", allow_small_model=True).model,
                         "ollama/gemma3:4b")

    def test_parallel_waves_respect_debate_round_dependencies(self):
        protocol, records = StudyProtocol(), []
        first = decision_wave(protocol, records)
        self.assertEqual({call.group for call in first}, set("ABCD"))
        self.assertEqual(len(first), 12)
        records.extend(asdict(call) for call in first)
        second = decision_wave(protocol, records)
        self.assertEqual([(call.group, call.round) for call in second], [("C", 2), ("C", 2), ("D", 2), ("D", 2)])
        records.extend(asdict(call) for call in second)
        third = decision_wave(protocol, records)
        self.assertEqual([(call.group, call.round) for call in third], [("C", 3), ("C", 3), ("D", 3), ("D", 3)])
        records.extend(asdict(call) for call in third)
        final = decision_wave(protocol, records)
        self.assertEqual([call.kind for call in final], ["adjudication", "adjudication"])


if __name__ == "__main__":
    unittest.main()
