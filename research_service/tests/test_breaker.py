import unittest

from research_service.breaker import Breaker


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


class BreakerTests(unittest.TestCase):
    def make(self, answers):
        self.clock, self.probes = Clock(), []

        def probe():
            self.probes.append(self.clock.t)
            return answers.pop(0)
        return Breaker(probe, threshold=3, retry_seconds=60, clock=self.clock)

    def test_success_resets_the_count(self):
        breaker = self.make([])
        for ok in (False, False, True, False, False):
            breaker.record(ok)
        self.assertTrue(breaker.allow())
        self.assertEqual(self.probes, [])

    def test_holds_after_three_failures_and_probes_once_a_minute(self):
        breaker = self.make([False, True])
        for _ in range(3):
            breaker.record(False)
        self.assertFalse(breaker.allow())
        self.clock.t = 59
        self.assertFalse(breaker.allow())
        self.assertEqual(self.probes, [])
        self.clock.t = 60
        self.assertFalse(breaker.allow())
        self.clock.t = 119
        self.assertFalse(breaker.allow())
        self.clock.t = 120
        self.assertTrue(breaker.allow())
        self.assertEqual(self.probes, [60, 120])
        self.assertFalse(breaker.open)
        self.assertEqual(breaker.public()["consecutive_failures"], 0)

    def test_probe_exception_keeps_the_queue_held(self):
        breaker = Breaker(lambda: 1 / 0, threshold=1, retry_seconds=0, clock=Clock())
        breaker.record(False)
        self.assertFalse(breaker.allow())
        self.assertTrue(breaker.open)


if __name__ == "__main__":
    unittest.main()
