import unittest

from hydro_remote_agent.tools.analyze_hydro_agent_bench_gate import _spearman


class HydroAgentBenchGateTest(unittest.TestCase):
    def test_spearman_perfect_monotonic(self):
        self.assertEqual(_spearman([0.0, 1.0, 2.0], [4.0, 5.0, 6.0]), 1.0)

    def test_spearman_handles_ties(self):
        value = _spearman([0.0, 0.0, 1.0, 1.0], [0.0, 0.2, 0.8, 1.0])
        self.assertIsNotNone(value)
        self.assertGreater(value, 0.8)

    def test_spearman_constant_is_undefined(self):
        self.assertIsNone(_spearman([1.0, 1.0], [0.0, 1.0]))


if __name__ == "__main__":
    unittest.main()
