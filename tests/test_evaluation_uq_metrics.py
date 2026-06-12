import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EVALS_DIR = ROOT / "evals"
if str(EVALS_DIR) not in sys.path:
    sys.path.insert(0, str(EVALS_DIR))

import run_agent_evaluation as evaluation


class FaithfulnessEvaluationTests(unittest.TestCase):
    def test_sentence_initial_common_word_is_not_hallucinated_entity(self):
        result = evaluation.compute_faithfulness_score(
            "Semua situs sudah dikunjungi sehingga tidak ada rekomendasi baru.",
            ["Surabi", "Angklung"],
        )

        self.assertEqual(result["faithfulness_score"], 1.0)
        self.assertEqual(result["hallucinated_names"], [])

    def test_unknown_proper_name_inside_sentence_is_detected(self):
        result = evaluation.compute_faithfulness_score(
            "Surabi dipilih sebagai tujuan utama, bukan Borobudur.",
            ["Surabi", "Angklung"],
        )

        self.assertEqual(result["faithfulness_score"], 0.8)
        self.assertEqual(result["hallucinated_names"], ["Borobudur"])


class SelectiveUQMetricTests(unittest.TestCase):
    @staticmethod
    def _result(scenario_id, uncertainty, correct):
        return {
            "scenario_id": scenario_id,
            "context_uq": {"udeg": uncertainty},
            "deterministic_checks": {
                name: correct
                for name in evaluation.CONTEXT_UQ_CORRECTNESS_CHECKS
            },
            "passed": correct,
        }

    def test_all_correct_run_reports_no_error_variation(self):
        results = [
            self._result("sc01_context_normal_01", 0.1, True),
            self._result("sc02_context_normal_02", 0.2, True),
        ]

        metrics = evaluation.compute_selective_uq_metrics(
            results,
            "context_uq",
            evaluation.CONTEXT_UQ_CORRECTNESS_CHECKS,
        )

        self.assertEqual(metrics["auarc"], 1.0)
        self.assertIsNone(metrics["error_detection_auroc"])
        self.assertEqual(metrics["status"], "no_error_variation")

    def test_higher_uncertainty_detects_incorrect_outputs(self):
        results = [
            self._result("sc01_context_normal_01", 0.1, True),
            self._result("sc02_context_normal_02", 0.2, True),
            self._result("sc03_context_normal_03", 0.8, False),
            self._result("sc04_context_normal_04", 0.9, False),
        ]

        metrics = evaluation.compute_selective_uq_metrics(
            results,
            "context_uq",
            evaluation.CONTEXT_UQ_CORRECTNESS_CHECKS,
        )

        self.assertEqual(metrics["error_detection_auroc"], 1.0)
        self.assertEqual(metrics["status"], "measurable")
        self.assertGreater(metrics["mean_udeg_incorrect"], metrics["mean_udeg_correct"])


if __name__ == "__main__":
    unittest.main()
