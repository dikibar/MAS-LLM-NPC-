import sys
import unittest
import json
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
        self.assertTrue(metrics["higher_uncertainty_on_errors"])
        self.assertGreater(metrics["mean_udeg_gap"], 0)


class ControlledFailureInjectionTests(unittest.TestCase):
    def test_context_fault_injection_adds_divergent_technical_leak(self):
        raw = json.dumps(
            {
                "user_action": "Pemain sedang menjelajah.",
                "context_summary": "Ada tiga tujuan.",
                "situation_type": "multiple_recommendations",
                "recommendation_reason": "Surabi menjadi tujuan utama.",
                "dialogue_intent": "guide_to_primary_with_alternatives",
                "recommendations": [],
                "nav_target": "Surabi",
                "timestamp": "2026-05-01T10:00:00Z",
                "scene": "Museum",
            }
        )

        first = json.loads(
            evaluation.apply_controlled_uq_fault(
                raw,
                "context",
                "divergent_interpretive_leak",
                0,
            )
        )
        second = json.loads(
            evaluation.apply_controlled_uq_fault(
                raw,
                "context",
                "divergent_interpretive_leak",
                1,
            )
        )

        self.assertNotEqual(first["user_action"], second["user_action"])
        self.assertFalse(
            evaluation.check_no_technical_leak(
                " ".join(
                    [
                        first["user_action"],
                        first["context_summary"],
                        first["recommendation_reason"],
                    ]
                )
            )
        )

    def test_dialogue_fault_keeps_primary_but_breaks_hud_safety(self):
        raw = json.dumps(
            {
                "spoken_output": "Mari menuju Surabi.",
                "subtitle_output": "Mari menuju Surabi.",
                "recommendation_dialogue": "Surabi adalah tujuan utama.",
                "recommendation_options": ["Surabi", "Angklung"],
            }
        )

        mutated = json.loads(
            evaluation.apply_controlled_uq_fault(
                raw,
                "dialogue",
                "divergent_hud_leak",
                0,
            )
        )

        self.assertIn("Surabi", mutated["subtitle_output"])
        self.assertFalse(
            evaluation.check_no_technical_leak(
                " ".join(
                    [
                        mutated["subtitle_output"],
                        mutated["recommendation_dialogue"],
                    ]
                )
            )
        )
        subtitle_ok, _ = evaluation.check_subtitle_max_15_words(mutated)
        self.assertFalse(subtitle_ok)

    def test_failure_benchmark_resolves_clean_and_corrupted_cases(self):
        scenarios = evaluation.load_uq_failure_scenarios()

        self.assertEqual(len(scenarios), 20)
        self.assertEqual(
            sum(1 for scenario in scenarios if scenario["uq_expected_correct"]),
            10,
        )
        self.assertEqual(
            sum(1 for scenario in scenarios if scenario["uq_failure_injection"]),
            10,
        )


if __name__ == "__main__":
    unittest.main()
