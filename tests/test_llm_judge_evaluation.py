import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
EVALS_DIR = ROOT / "evals"
if str(EVALS_DIR) not in sys.path:
    sys.path.insert(0, str(EVALS_DIR))

import run_agent_evaluation as evaluation


class _Message:
    def __init__(self, content):
        self.content = content


class _Choice:
    def __init__(self, content):
        self.message = _Message(content)


class _Response:
    def __init__(self, content):
        self.choices = [_Choice(content)]


class _Completions:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return _Response(response)


class _Chat:
    def __init__(self, responses):
        self.completions = _Completions(responses)


class _Client:
    def __init__(self, responses):
        self.chat = _Chat(responses)


def _scenario():
    return {
        "id": "judge_test",
        "focus": ["dialogue_agent"],
        "llm_judge": True,
        "expected_context": {"nav_target": "Surabi"},
        "expected_dialogue": {"recommendation_options": ["Surabi"]},
    }


def _valid_payload(dimensions, score=4):
    return json.dumps(
        {
            "scores": {
                dimension: {
                    "score": score,
                    "reasoning": f"Bukti spesifik untuk {dimension}.",
                }
                for dimension in dimensions
            }
        }
    )


class JudgeParsingTests(unittest.TestCase):
    def test_valid_response_is_parsed_for_every_dimension(self):
        dimensions = ["faithfulness", "navigation_clarity"]

        parsed = evaluation.parse_judge_response(
            _valid_payload(dimensions),
            dimensions,
        )

        self.assertEqual(parsed["faithfulness"]["score"], 4)
        self.assertEqual(parsed["navigation_clarity"]["status"], "ok")

    def test_out_of_range_score_is_rejected(self):
        payload = _valid_payload(["faithfulness"], score=6)

        with self.assertRaisesRegex(ValueError, "between 1 and 5"):
            evaluation.parse_judge_response(payload, ["faithfulness"])

    def test_missing_reasoning_is_rejected(self):
        payload = json.dumps(
            {"scores": {"faithfulness": {"score": 4, "reasoning": ""}}}
        )

        with self.assertRaisesRegex(ValueError, "Reasoning is required"):
            evaluation.parse_judge_response(payload, ["faithfulness"])


class JudgePolicyTests(unittest.TestCase):
    def test_judge_error_fails_closed(self):
        scenario = _scenario()
        meta = {
            "status": "error",
            "required_dimensions": ["faithfulness"],
        }

        assessment = evaluation.evaluate_judge_scores(scenario, {}, meta)

        self.assertFalse(assessment["passed"])
        self.assertEqual(assessment["reason"], "judge_error")

    def test_technical_safety_requires_five(self):
        scenario = _scenario()
        dimensions = evaluation.judge_dimensions_for_scenario(scenario)
        scores = {
            dimension: {
                "score": 4,
                "reasoning": "Bukti.",
                "dimension": dimension,
                "status": "ok",
            }
            for dimension in dimensions
        }
        scores["technical_leak_safety"]["score"] = 4
        meta = {"status": "ok", "required_dimensions": dimensions}

        assessment = evaluation.evaluate_judge_scores(scenario, scores, meta)

        self.assertFalse(assessment["passed"])
        self.assertIn(
            "technical_leak_safety",
            assessment["failed_dimensions"],
        )

    def test_summary_uses_same_technical_safety_threshold(self):
        result = {
            "passed": False,
            "deterministic_checks": {"schema": True},
            "llm_judge_scores": {
                "technical_leak_safety": {
                    "score": 4,
                    "reasoning": "Bukti.",
                }
            },
            "llm_judge_meta": {
                "required": True,
                "status": "ok",
                "required_dimensions": ["technical_leak_safety"],
                "thresholds": {"technical_leak_safety": 5},
            },
            "llm_judge_assessment": {
                "passed": False,
                "overall_score": 4.0,
            },
        }

        summary = evaluation.aggregate_results([result])

        self.assertEqual(
            summary["judge_summary"]["technical_leak_safety"]["pass_rate"],
            0.0,
        )


class JudgeExecutionTests(unittest.TestCase):
    def test_dialogue_judge_isolates_user_visible_candidate_from_context_metadata(self):
        scenario = _scenario()
        context_output = {
            "user_action": "Pemain berada di Museum dengan beberapa rekomendasi tujuan.",
            "context_summary": "Tersedia 3 rekomendasi teratas.",
            "situation_type": "multiple_recommendations",
            "recommendation_reason": "Surabi adalah tujuan belum dikunjungi terdekat.",
            "dialogue_intent": "guide_to_primary_with_alternatives",
            "recommendations": [
                {
                    "rank": 1,
                    "id": "Surabi",
                    "name": "Surabi",
                    "cultural_position": "14.62413, 1.37554, 18.67057",
                }
            ],
            "nav_target": "Surabi",
        }
        dialogue_output = {
            "spoken_output": "Mari menuju Surabi.",
            "subtitle_output": "Mari menuju Surabi.",
            "recommendation_dialogue": "Surabi menjadi tujuan utama.",
            "recommendation_options": ["Surabi"],
        }

        payload = evaluation.build_judge_evaluation_input(
            scenario,
            context_output,
            dialogue_output,
        )

        self.assertEqual(
            payload["candidate_under_test"],
            {"dialogue_output": dialogue_output},
        )
        grounding_json = json.dumps(payload["grounding_reference"])
        self.assertNotIn("cultural_position", grounding_json)
        self.assertNotIn("14.62413", grounding_json)
        self.assertIn(
            "HANYA teks pada dialogue_output",
            payload["dimension_scope"]["technical_leak_safety"],
        )

    def test_missing_credentials_are_reported_as_skipped_and_fail_closed(self):
        scenario = _scenario()

        with patch.object(evaluation, "judge_client", None):
            scores, meta = evaluation.run_llm_judge_all_dimensions(
                scenario,
                {},
                {},
            )
        assessment = evaluation.evaluate_judge_scores(scenario, scores, meta)

        self.assertEqual(meta["status"], "skipped")
        self.assertFalse(assessment["passed"])

    def test_malformed_response_is_retried_then_succeeds(self):
        scenario = _scenario()
        dimensions = evaluation.judge_dimensions_for_scenario(scenario)
        client = _Client(["not-json", _valid_payload(dimensions, score=5)])

        with (
            patch.object(evaluation, "judge_client", client),
            patch.object(evaluation, "JUDGE_MAX_RETRIES", 2),
            patch.object(evaluation.time, "sleep"),
        ):
            scores, meta = evaluation.run_llm_judge_all_dimensions(
                scenario,
                {"nav_target": "Surabi"},
                {"subtitle_output": "Mari menuju Surabi."},
            )

        self.assertEqual(meta["status"], "ok")
        self.assertEqual(meta["attempts"], 2)
        self.assertEqual(len(scores), len(dimensions))
        self.assertEqual(len(client.chat.completions.calls), 2)
        user_prompt = client.chat.completions.calls[-1]["messages"][1]["content"]
        self.assertIn("candidate_under_test", user_prompt)
        self.assertIn(
            "technical_leak_safety HANYA menilai spoken_output",
            user_prompt,
        )

    def test_exhausted_retries_return_error_status(self):
        scenario = _scenario()
        client = _Client(["bad", "still bad"])

        with (
            patch.object(evaluation, "judge_client", client),
            patch.object(evaluation, "JUDGE_MAX_RETRIES", 2),
            patch.object(evaluation.time, "sleep"),
        ):
            scores, meta = evaluation.run_llm_judge_all_dimensions(
                scenario,
                {},
                {},
            )

        self.assertEqual(scores, {})
        self.assertEqual(meta["status"], "error")
        self.assertEqual(meta["attempts"], 2)


class HumanAgreementTests(unittest.TestCase):
    def test_human_agreement_metrics_are_calculated(self):
        results = [
            {
                "scenario_id": "sc1",
                "llm_judge_scores": {
                    "faithfulness": {"score": 5},
                    "language_quality": {"score": 3},
                },
            },
            {
                "scenario_id": "sc2",
                "llm_judge_scores": {
                    "faithfulness": {"score": 2},
                },
            },
        ]
        annotations = [
            {"scenario_id": "sc1", "dimension": "faithfulness", "score": 5},
            {"scenario_id": "sc1", "dimension": "language_quality", "score": 4},
            {"scenario_id": "sc2", "dimension": "faithfulness", "score": 2},
        ]

        agreement = evaluation.compute_human_judge_agreement(
            results,
            annotations,
        )

        self.assertEqual(agreement["status"], "available")
        self.assertEqual(agreement["sample_count"], 3)
        self.assertEqual(agreement["within_one_agreement"], 1.0)


class JudgeValidationBenchmarkTests(unittest.TestCase):
    def test_validation_dataset_contains_clean_and_corrupted_cases(self):
        cases = evaluation.load_judge_validation_cases()

        self.assertGreaterEqual(
            sum(1 for case in cases if case["expected_pass"]),
            3,
        )
        self.assertGreaterEqual(
            sum(1 for case in cases if not case["expected_pass"]),
            3,
        )

    def test_validation_benchmark_reports_discrimination(self):
        cases = [
            {"id": "clean", "expected_pass": True},
            {"id": "corrupt", "expected_pass": False},
        ]

        def fake_judge(scenario, context_output, dialogue_output):
            score = 5 if scenario["id"] == "clean" else 1
            return {
                dimension: {
                    "score": score,
                    "reasoning": "Bukti.",
                    "dimension": dimension,
                    "status": "ok",
                }
                for dimension in evaluation.judge_dimensions_for_scenario(scenario)
            }, {
                "status": "ok",
                "required": True,
                "required_dimensions": evaluation.judge_dimensions_for_scenario(
                    scenario
                ),
            }

        with patch.object(
            evaluation,
            "run_llm_judge_all_dimensions",
            side_effect=fake_judge,
        ):
            result = evaluation.run_judge_validation_benchmark(cases)

        self.assertEqual(result["summary"]["label_accuracy"], 1.0)
        self.assertEqual(
            result["summary"]["specificity_corruption_rejection"],
            1.0,
        )
        self.assertTrue(result["summary"]["validation_confirmed"])


if __name__ == "__main__":
    unittest.main()
