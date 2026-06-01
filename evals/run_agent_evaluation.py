#!/usr/bin/env python3
"""
Offline evaluation harness for the VR multi-agent system.

The harness intentionally combines:
- deterministic checks for Context Agent outputs;
- rule-based checks for Dialogue Agent safety and UI consistency;
- end-to-end task-success checks for the orchestrated workflow.

It defaults to USE_MOCK_MODEL=true so evaluation can run without network access.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import logging
import math
import os
import re
import statistics
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

os.environ.setdefault("USE_MOCK_MODEL", "true")

from schema.models import ContextOutput, DialogueOutput, SimulationRequest  # noqa: E402


AgentMode = str


LEAK_PATTERNS = [
    re.compile(r"-?\d+(?:\.\d+)?\s*,\s*-?\d+(?:\.\d+)?\s*,\s*-?\d+(?:\.\d+)?"),
    re.compile(r"\bNAV_TO_TARGET\b", re.IGNORECASE),
    re.compile(r"\bDISPLAY_SUBTITLE\b", re.IGNORECASE),
    re.compile(r"\bnavmesh\b", re.IGNORECASE),
    re.compile(r"\bbackend\b", re.IGNORECASE),
    re.compile(r"\bcontext[_ ]?agent\b", re.IGNORECASE),
    re.compile(r"\bdialogue[_ ]?agent\b", re.IGNORECASE),
    re.compile(r"\btool_", re.IGNORECASE),
]

VALID_SITUATION_TYPES = {
    "multiple_recommendations",
    "single_recommendation",
    "all_sites_visited",
    "exploration_context",
}

VALID_DIALOGUE_INTENTS = {
    "guide_to_primary_with_alternatives",
    "guide_to_single_primary",
    "no_new_destination",
    "encourage_exploration",
}


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class ScenarioResult:
    scenario_id: str
    description: str
    checks: list[CheckResult] = field(default_factory=list)
    context_metrics: dict[str, float | int | bool] = field(default_factory=dict)
    dialogue_metrics: dict[str, float | int | bool] = field(default_factory=dict)
    end_to_end_success: bool = False

    def add(self, name: str, passed: bool, detail: str = "") -> None:
        self.checks.append(CheckResult(name=name, passed=passed, detail=detail))

    @property
    def passed_checks(self) -> int:
        return sum(1 for check in self.checks if check.passed)

    @property
    def total_checks(self) -> int:
        return len(self.checks)

    @property
    def pass_rate(self) -> float:
        if not self.checks:
            return 0.0
        return self.passed_checks / self.total_checks


def parse_vector3(position: str) -> tuple[float, float, float]:
    parts = [part.strip() for part in position.split(",")]
    if len(parts) != 3:
        raise ValueError(f"Invalid Vector3 coordinate: {position}")
    return tuple(float(part) for part in parts)


def distance(a: str, b: str) -> float:
    ax, ay, az = parse_vector3(a)
    bx, by, bz = parse_vector3(b)
    return math.sqrt((ax - bx) ** 2 + (ay - by) ** 2 + (az - bz) ** 2)


def gold_recommendations(sim_request: SimulationRequest) -> list[dict[str, Any]]:
    ranked = sorted(
        [site for site in sim_request.culturalSites if not site.visited],
        key=lambda site: (
            distance(sim_request.playerPosition, site.cultural_position),
            site.name.lower(),
        ),
    )
    return [
        {
            "rank": index,
            "id": site.id,
            "name": site.name,
            "cultural_position": site.cultural_position,
        }
        for index, site in enumerate(ranked[:3], start=1)
    ]


def precision_at_k(predicted: list[str], relevant: list[str], k: int) -> float:
    considered = predicted[:k]
    if not considered:
        return 1.0 if not relevant else 0.0
    return len(set(considered) & set(relevant)) / len(considered)


def recall_at_k(predicted: list[str], relevant: list[str], k: int) -> float:
    if not relevant:
        return 1.0 if not predicted[:k] else 0.0
    return len(set(predicted[:k]) & set(relevant)) / len(relevant)


def mrr(predicted: list[str], relevant: list[str]) -> float:
    relevant_set = set(relevant)
    for index, item in enumerate(predicted, start=1):
        if item in relevant_set:
            return 1.0 / index
    return 0.0


def ndcg_at_k(predicted: list[str], ideal: list[str], k: int) -> float:
    if not ideal:
        return 1.0 if not predicted[:k] else 0.0

    relevance = {item: max(len(ideal) - index, 1) for index, item in enumerate(ideal)}

    def dcg(items: list[str]) -> float:
        score = 0.0
        for index, item in enumerate(items[:k], start=1):
            gain = relevance.get(item, 0)
            score += gain / math.log2(index + 1)
        return score

    ideal_dcg = dcg(ideal[:k])
    if ideal_dcg == 0:
        return 0.0
    return dcg(predicted) / ideal_dcg


def count_words(text: str) -> int:
    return len([word for word in text.strip().split() if word])


def contains_leak(text: str) -> bool:
    return any(pattern.search(text) for pattern in LEAK_PATTERNS)


def evaluate_context(
    result: ScenarioResult,
    sim_request: SimulationRequest,
    context: ContextOutput,
) -> list[str]:
    expected = gold_recommendations(sim_request)
    expected_names = [item["name"] for item in expected]
    expected_ids = [item["id"] for item in expected]
    predicted_names = [site.name for site in context.recommendations]
    predicted_ids = [site.id for site in context.recommendations]
    visited_names = {site.name for site in sim_request.culturalSites if site.visited}

    result.add(
        "context.schema_valid",
        isinstance(context, ContextOutput),
        "ContextOutput object returned by orchestrator.",
    )
    result.add(
        "context.timestamp_matches_request",
        context.timestamp == sim_request.timestamp,
        f"expected={sim_request.timestamp}, actual={context.timestamp}",
    )
    result.add(
        "context.scene_matches_request",
        context.scene == sim_request.scene,
        f"expected={sim_request.scene}, actual={context.scene}",
    )
    result.add(
        "context.no_visited_sites_recommended",
        not (set(predicted_names) & visited_names),
        f"visited_in_output={sorted(set(predicted_names) & visited_names)}",
    )
    result.add(
        "context.ranking_exact_match",
        predicted_ids == expected_ids,
        f"expected={expected_ids}, actual={predicted_ids}",
    )
    expected_nav_target = expected[0]["id"] if expected else ""
    result.add(
        "context.nav_target_matches_rank_1",
        context.nav_target == expected_nav_target,
        f"expected={expected_nav_target}, actual={context.nav_target}",
    )
    result.add(
        "context.max_three_recommendations",
        len(context.recommendations) <= 3,
        f"actual_count={len(context.recommendations)}",
    )
    result.add(
        "context.context_summary_present",
        bool(context.context_summary.strip()),
        context.context_summary,
    )
    result.add(
        "context.recommendation_reason_present",
        bool(context.recommendation_reason.strip()),
        context.recommendation_reason,
    )
    result.add(
        "context.situation_type_supported",
        context.situation_type in VALID_SITUATION_TYPES,
        f"actual={context.situation_type}",
    )
    result.add(
        "context.dialogue_intent_supported",
        context.dialogue_intent in VALID_DIALOGUE_INTENTS,
        f"actual={context.dialogue_intent}",
    )
    result.add(
        "context.no_coordinates_in_interpretive_fields",
        not contains_leak(
            " ".join(
                [
                    context.user_action,
                    context.context_summary,
                    context.recommendation_reason,
                    context.dialogue_intent,
                    context.situation_type,
                ]
            )
        ),
        "interpretive fields should not expose coordinates or technical tokens.",
    )

    k = 3
    result.context_metrics = {
        "precision_at_3": precision_at_k(predicted_names, expected_names, k),
        "recall_at_3": recall_at_k(predicted_names, expected_names, k),
        "mrr": mrr(predicted_names, expected_names),
        "ndcg_at_3": ndcg_at_k(predicted_names, expected_names, k),
        "recommendation_count": len(context.recommendations),
        "expected_count": len(expected),
    }
    return expected_names


def evaluate_dialogue(
    result: ScenarioResult,
    dialogue: DialogueOutput,
    expected_options: list[str],
    selected_option: str | None = None,
) -> None:
    all_user_text = " ".join(
        [
            dialogue.spoken_output,
            dialogue.subtitle_output,
            dialogue.recommendation_dialogue,
            " ".join(dialogue.recommendation_options),
        ]
    )
    primary_option = expected_options[0] if expected_options else ""
    subtitle_words = count_words(dialogue.subtitle_output)

    result.add(
        "dialogue.schema_valid",
        isinstance(dialogue, DialogueOutput),
        "DialogueOutput object returned by orchestrator.",
    )
    result.add(
        "dialogue.options_match_context_order",
        dialogue.recommendation_options == expected_options,
        f"expected={expected_options}, actual={dialogue.recommendation_options}",
    )
    result.add(
        "dialogue.subtitle_max_15_words",
        subtitle_words <= 15,
        f"word_count={subtitle_words}",
    )
    result.add(
        "dialogue.no_internal_tokens_or_coordinates",
        not contains_leak(all_user_text),
        "user-facing text should not expose coordinates, tool names, backend terms, or NavMesh terms.",
    )

    if primary_option and selected_option is None:
        result.add(
            "dialogue.primary_option_mentioned",
            primary_option.lower() in dialogue.spoken_output.lower()
            or primary_option.lower() in dialogue.subtitle_output.lower(),
            f"primary_option={primary_option}",
        )
    elif not primary_option:
        result.add(
            "dialogue.empty_recommendations_handled",
            not dialogue.recommendation_options,
            f"actual_options={dialogue.recommendation_options}",
        )

    if selected_option:
        result.add(
            "dialogue.selected_option_mentioned",
            selected_option.lower() in dialogue.spoken_output.lower()
            and selected_option.lower() in dialogue.subtitle_output.lower(),
            f"selected_option={selected_option}",
        )

    result.dialogue_metrics = {
        "subtitle_word_count": subtitle_words,
        "option_count": len(dialogue.recommendation_options),
        "has_leak": contains_leak(all_user_text),
    }


def evaluate_scenario(raw_scenario: dict[str, Any]) -> ScenarioResult:
    from orchestration.coordinator import HierarchicalOrchestrator

    scenario_id = raw_scenario["id"]
    result = ScenarioResult(
        scenario_id=scenario_id,
        description=raw_scenario.get("description", ""),
    )
    orchestrator = HierarchicalOrchestrator()

    try:
        sim_request = SimulationRequest.model_validate(raw_scenario["request"])
    except Exception as exc:
        result.add("request.valid_simulation_request", False, str(exc))
        return result

    result.add("request.valid_simulation_request", True)
    context_result = orchestrator.run_context_cycle(sim_request)
    expected_options = evaluate_context(result, sim_request, context_result.context)

    dialogue_result = orchestrator.run_dialogue_cycle(context_result.simulation_id)
    evaluate_dialogue(result, dialogue_result.dialogue, expected_options)

    selected_option = raw_scenario.get("selectedOption")
    expect_selection_error = bool(raw_scenario.get("expectSelectionError", False))
    selection_passed = True

    if selected_option:
        try:
            selection_response = orchestrator.handle_recommendation_selection(
                context_result.simulation_id,
                selected_option,
            )
            if expect_selection_error:
                result.add(
                    "selection.expected_error",
                    False,
                    "selection succeeded but scenario expected an error.",
                )
                selection_passed = False
            else:
                result.add("selection.accepted_valid_option", True)
                result.add(
                    "selection.nav_target_matches_selected_option",
                    selection_response.selected_option == selected_option,
                    f"expected={selected_option}, actual={selection_response.selected_option}",
                )
                selection_dialogue = DialogueOutput(
                    spoken_output=selection_response.spoken_output,
                    subtitle_output=selection_response.subtitle_output,
                    recommendation_dialogue="",
                    recommendation_options=expected_options,
                )
                evaluate_dialogue(result, selection_dialogue, expected_options, selected_option)
        except ValueError as exc:
            if expect_selection_error:
                result.add("selection.expected_error", True, str(exc))
            else:
                result.add("selection.accepted_valid_option", False, str(exc))
                selection_passed = False

    required_prefixes = ("request.", "context.", "dialogue.")
    required_checks_pass = all(
        check.passed
        for check in result.checks
        if check.name.startswith(required_prefixes)
    )
    result.end_to_end_success = required_checks_pass and selection_passed
    return result


def evaluate_context_scenario(raw_scenario: dict[str, Any]) -> ScenarioResult:
    from orchestration.coordinator import HierarchicalOrchestrator

    scenario_id = raw_scenario["id"]
    result = ScenarioResult(
        scenario_id=scenario_id,
        description=raw_scenario.get("description", ""),
    )
    orchestrator = HierarchicalOrchestrator()

    try:
        sim_request = SimulationRequest.model_validate(raw_scenario["request"])
    except Exception as exc:
        result.add("request.valid_simulation_request", False, str(exc))
        return result

    result.add("request.valid_simulation_request", True)
    context_result = orchestrator.run_context_cycle(sim_request)
    evaluate_context(result, sim_request, context_result.context)

    result.end_to_end_success = all(check.passed for check in result.checks)
    return result


def evaluate_dialogue_scenario(raw_scenario: dict[str, Any]) -> ScenarioResult:
    from orchestration.coordinator import HierarchicalOrchestrator

    scenario_id = raw_scenario["id"]
    result = ScenarioResult(
        scenario_id=scenario_id,
        description=raw_scenario.get("description", ""),
    )
    orchestrator = HierarchicalOrchestrator()

    try:
        sim_request = SimulationRequest.model_validate(raw_scenario["request"])
    except Exception as exc:
        result.add("request.valid_simulation_request", False, str(exc))
        return result

    result.add("request.valid_simulation_request", True)
    context_result = orchestrator.run_context_cycle(sim_request)
    expected_options = [site.name for site in context_result.context.recommendations]
    dialogue_result = orchestrator.run_dialogue_cycle(context_result.simulation_id)
    evaluate_dialogue(result, dialogue_result.dialogue, expected_options)

    selected_option = raw_scenario.get("selectedOption")
    expect_selection_error = bool(raw_scenario.get("expectSelectionError", False))
    if selected_option and not expect_selection_error:
        selection_response = orchestrator.handle_recommendation_selection(
            context_result.simulation_id,
            selected_option,
        )
        selection_dialogue = DialogueOutput(
            spoken_output=selection_response.spoken_output,
            subtitle_output=selection_response.subtitle_output,
            recommendation_dialogue="",
            recommendation_options=expected_options,
        )
        evaluate_dialogue(result, selection_dialogue, expected_options, selected_option)

    result.end_to_end_success = all(check.passed for check in result.checks)
    return result


def summarize(results: list[ScenarioResult]) -> dict[str, Any]:
    scenario_count = len(results)
    total_checks = sum(result.total_checks for result in results)
    passed_checks = sum(result.passed_checks for result in results)

    def context_metric_mean(metric_name: str) -> float:
        values = [
            float(result.context_metrics[metric_name])
            for result in results
            if metric_name in result.context_metrics
        ]
        return statistics.mean(values) if values else 0.0

    def dialogue_metric_mean(metric_name: str) -> float:
        values = [
            float(result.dialogue_metrics[metric_name])
            for result in results
            if metric_name in result.dialogue_metrics
            and isinstance(result.dialogue_metrics[metric_name], (int, float, bool))
        ]
        return statistics.mean(values) if values else 0.0

    return {
        "scenario_count": scenario_count,
        "check_pass_rate": passed_checks / total_checks if total_checks else 0.0,
        "passed_checks": passed_checks,
        "total_checks": total_checks,
        "end_to_end_success_rate": (
            sum(1 for result in results if result.end_to_end_success) / scenario_count
            if scenario_count
            else 0.0
        ),
        "context": {
            "mean_precision_at_3": context_metric_mean("precision_at_3"),
            "mean_recall_at_3": context_metric_mean("recall_at_3"),
            "mean_mrr": context_metric_mean("mrr"),
            "mean_ndcg_at_3": context_metric_mean("ndcg_at_3"),
        },
        "dialogue": {
            "mean_subtitle_word_count": dialogue_metric_mean("subtitle_word_count"),
            "mean_option_count": dialogue_metric_mean("option_count"),
            "leak_rate": dialogue_metric_mean("has_leak"),
        },
    }


def as_dict(result: ScenarioResult) -> dict[str, Any]:
    return {
        "scenario_id": result.scenario_id,
        "description": result.description,
        "pass_rate": result.pass_rate,
        "end_to_end_success": result.end_to_end_success,
        "context_metrics": result.context_metrics,
        "dialogue_metrics": result.dialogue_metrics,
        "checks": [
            {
                "name": check.name,
                "passed": check.passed,
                "detail": check.detail,
            }
            for check in result.checks
        ],
    }


def print_markdown_report(
    results: list[ScenarioResult],
    summary: dict[str, Any],
    agent_mode: AgentMode,
) -> None:
    title = {
        "context": "Context Agent Evaluation Report",
        "dialogue": "Dialogue Agent Evaluation Report",
        "e2e": "End-to-End Agent Evaluation Report",
        "all": "Agent Evaluation Report",
    }.get(agent_mode, "Agent Evaluation Report")
    print(f"# {title}")
    print()
    print("## Summary")
    print(f"- Scenarios: {summary['scenario_count']}")
    print(f"- Check pass rate: {summary['check_pass_rate']:.2%}")
    if agent_mode in {"context", "e2e", "all"}:
        print(f"- Context Precision@3: {summary['context']['mean_precision_at_3']:.3f}")
        print(f"- Context Recall@3: {summary['context']['mean_recall_at_3']:.3f}")
        print(f"- Context MRR: {summary['context']['mean_mrr']:.3f}")
        print(f"- Context NDCG@3: {summary['context']['mean_ndcg_at_3']:.3f}")
    if agent_mode in {"dialogue", "e2e", "all"}:
        print(f"- Dialogue subtitle words avg: {summary['dialogue']['mean_subtitle_word_count']:.2f}")
        print(f"- Dialogue options avg: {summary['dialogue']['mean_option_count']:.2f}")
        print(f"- Dialogue technical leak rate: {summary['dialogue']['leak_rate']:.2%}")
    if agent_mode in {"e2e", "all"}:
        print(f"- End-to-end success rate: {summary['end_to_end_success_rate']:.2%}")
    print()
    print("## Scenario Details")
    for result in results:
        status = "PASS" if result.end_to_end_success else "ATTENTION"
        print(f"### {result.scenario_id} — {status}")
        print(f"- Description: {result.description}")
        print(f"- Check pass rate: {result.pass_rate:.2%}")
        failed = [check for check in result.checks if not check.passed]
        if failed:
            print("- Failed checks:")
            for check in failed:
                print(f"  - {check.name}: {check.detail}")
        else:
            print("- Failed checks: none")
        print()


def evaluate_by_mode(scenario: dict[str, Any], agent_mode: AgentMode) -> ScenarioResult:
    if agent_mode == "context":
        return evaluate_context_scenario(scenario)
    if agent_mode == "dialogue":
        return evaluate_dialogue_scenario(scenario)
    return evaluate_scenario(scenario)


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate VR multi-agent system scenarios.")
    parser.add_argument(
        "--scenarios",
        type=Path,
        default=PROJECT_ROOT / "evals" / "scenarios.json",
        help="Path to scenario JSON file.",
    )
    parser.add_argument(
        "--agent",
        choices=["context", "dialogue", "e2e", "all"],
        default="all",
        help="Evaluate one agent/layer at a time. Use 'all' for the combined report.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON instead of markdown.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show orchestrator logs and phase prints while scenarios run.",
    )
    args = parser.parse_args()

    scenarios = json.loads(args.scenarios.read_text(encoding="utf-8"))

    if not args.verbose:
        logging.disable(logging.CRITICAL)
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            results = [evaluate_by_mode(scenario, args.agent) for scenario in scenarios]
        logging.disable(logging.NOTSET)
    else:
        results = [evaluate_by_mode(scenario, args.agent) for scenario in scenarios]

    summary = summarize(results)

    if args.json:
        print(
            json.dumps(
                {
                    "summary": summary,
                    "agent": args.agent,
                    "results": [as_dict(result) for result in results],
                },
                indent=2,
                ensure_ascii=False,
            )
        )
    else:
        print_markdown_report(results, summary, args.agent)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
