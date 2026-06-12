#!/usr/bin/env python3
"""
Evaluation runner for the VR Museum Guide multi-agent system.

Layers:
  1. Structural and deterministic checks.
  2. LLM-as-a-Judge G-Eval style scoring.
  3. Faithfulness, trajectory, reliability, and ablation checks.
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
import time
from datetime import datetime
from pathlib import Path
from typing import Any

os.environ.setdefault("MPLCONFIGDIR", "/private/tmp/agentfinal_matplotlib")

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from openai import OpenAI
from sklearn.metrics import cohen_kappa_score, ndcg_score, roc_auc_score


ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from core.config import settings

SCENARIOS_PATH = Path(__file__).parent / "scenarios.json"
FIGURES_DIR = Path(__file__).parent / "figures"
RESULTS_DIR = Path(__file__).parent / "results"
FIGURES_DIR.mkdir(exist_ok=True)
RESULTS_DIR.mkdir(exist_ok=True)


def env_or_dotenv(name: str, default: str = "") -> str:
    value = os.getenv(name)
    if value:
        return value
    env_path = ROOT / ".env"
    if not env_path.exists():
        return default
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, raw_value = stripped.split("=", 1)
        if key.strip() == name:
            return raw_value.strip().strip('"').strip("'")
    return default


JUDGE_MODEL = env_or_dotenv("OPENROUTER_MODEL", "openai/gpt-4.1")
OPENROUTER_API_KEY = env_or_dotenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = env_or_dotenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")

judge_client = (
    OpenAI(base_url=OPENROUTER_BASE_URL, api_key=OPENROUTER_API_KEY)
    if OPENROUTER_API_KEY
    else None
)

# Default to real mode per the evaluation spec. If credentials are unavailable,
# the project orchestrator falls back to MockModel.
os.environ.setdefault("USE_MOCK_MODEL", "false")

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)
VERBOSE = False

LEAK_PATTERNS = [
    re.compile(r"-?\d+(?:\.\d{3,})\s*,\s*-?\d+(?:\.\d{3,})?\s*,\s*-?\d+(?:\.\d{3,})?"),
    re.compile(r"\b\d+\.\d{3,}\b"),
    re.compile(r"\bNAV_TO_TARGET\b", re.IGNORECASE),
    re.compile(r"\bDISPLAY_SUBTITLE\b", re.IGNORECASE),
    re.compile(r"\bnavmesh\b", re.IGNORECASE),
    re.compile(r"\bbackend\b", re.IGNORECASE),
    re.compile(r"\btool_get\b", re.IGNORECASE),
    re.compile(r"\btool_", re.IGNORECASE),
    re.compile(r"\bcultural_position\b", re.IGNORECASE),
    re.compile(r"\bprecomputed\b", re.IGNORECASE),
    re.compile(r"\bcontext_output\b", re.IGNORECASE),
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


def parse_vector3(pos_str: str) -> tuple[float, float, float]:
    parts = [part.strip() for part in pos_str.split(",")]
    if len(parts) != 3:
        raise ValueError(f"Invalid Vector3 coordinate: {pos_str}")
    return float(parts[0]), float(parts[1]), float(parts[2])


def euclidean_distance(a: str, b: str) -> float:
    ax, ay, az = parse_vector3(a)
    bx, by, bz = parse_vector3(b)
    return math.sqrt((ax - bx) ** 2 + (ay - by) ** 2 + (az - bz) ** 2)


def normalize_site_dicts(req_data: dict[str, Any]) -> list[dict[str, Any]]:
    raw_sites = req_data.get("culturalSites") or req_data.get("culturalObjects") or req_data.get("culturalObject") or []
    normalized = []
    for site in raw_sites:
        normalized.append(
            {
                "id": site.get("id") or site.get("name", ""),
                "name": site.get("name", ""),
                "cultural_position": site.get("cultural_position") or site.get("coordinate", ""),
                "visited": site.get("visited", site.get("isObjectVisited", False)),
            }
        )
    return normalized


def compute_expected_ranking(player_pos: str, sites: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unvisited = [site for site in sites if not site.get("visited", False)]
    ranked = sorted(
        unvisited,
        key=lambda site: (
            euclidean_distance(player_pos, site["cultural_position"]),
            site["name"].lower(),
        ),
    )
    return ranked[:3]


def check_schema_valid_context(context_output: dict[str, Any]) -> bool:
    required = [
        "timestamp",
        "scene",
        "user_action",
        "context_summary",
        "situation_type",
        "recommendation_reason",
        "dialogue_intent",
        "recommendations",
        "nav_target",
    ]
    return all(key in context_output for key in required)


def check_schema_valid_dialogue(dialogue_output: dict[str, Any]) -> bool:
    required = [
        "spoken_output",
        "subtitle_output",
        "recommendation_dialogue",
        "recommendation_options",
    ]
    return all(key in dialogue_output for key in required)


def check_no_visited_sites(context_output: dict[str, Any], sites: list[dict[str, Any]]) -> bool:
    visited_ids = {site["id"] for site in sites if site.get("visited", False)}
    rec_ids = {rec["id"] for rec in context_output.get("recommendations", [])}
    return not (visited_ids & rec_ids)


def check_nav_target_rank1(context_output: dict[str, Any]) -> bool:
    recommendations = context_output.get("recommendations", [])
    nav_target = context_output.get("nav_target", "")
    if not recommendations:
        return nav_target == ""
    return nav_target == recommendations[0]["id"]


def check_subtitle_max_15_words(dialogue_output: dict[str, Any]) -> tuple[bool, int]:
    subtitle = dialogue_output.get("subtitle_output", "")
    count = len([word for word in subtitle.split() if word.strip()])
    return count <= 15, count


def check_no_technical_leak(text: str) -> bool:
    return not any(pattern.search(text or "") for pattern in LEAK_PATTERNS)


def check_primary_option_mentioned(dialogue_output: dict[str, Any], primary_site: str) -> bool:
    if not primary_site:
        return True
    user_text = " ".join(
        [
            dialogue_output.get("subtitle_output", ""),
            dialogue_output.get("recommendation_dialogue", ""),
            " ".join(dialogue_output.get("recommendation_options", [])),
        ]
    ).lower()
    return primary_site.lower() in user_text


def check_options_match_context(dialogue_output: dict[str, Any], context_output: dict[str, Any]) -> bool:
    expected = [rec["name"] for rec in context_output.get("recommendations", [])]
    actual = dialogue_output.get("recommendation_options", [])
    return actual == expected


def compute_ir_metrics(predicted: list[str], relevant: list[str]) -> dict[str, float]:
    k = 3
    pred_k = predicted[:k]
    relevant_set = set(relevant)
    hits = [1 if item in relevant_set else 0 for item in pred_k]
    precision = sum(hits) / len(pred_k) if pred_k else (1.0 if not relevant else 0.0)
    recall = sum(hits) / len(relevant_set) if relevant_set else (1.0 if not pred_k else 0.0)

    mrr = 0.0
    for index, item in enumerate(pred_k, start=1):
        if item in relevant_set:
            mrr = 1.0 / index
            break

    if not pred_k and not relevant:
        ndcg = 1.0
    elif not pred_k:
        ndcg = 0.0
    else:
        y_true = np.array([[1 if item in relevant_set else 0 for item in pred_k]])
        y_score = np.array([[k - index for index in range(len(pred_k))]])
        try:
            ndcg = float(ndcg_score(y_true, y_score, k=k))
        except Exception:
            ndcg = 0.0

    return {
        "precision_at_3": round(precision, 4),
        "recall_at_3": round(recall, 4),
        "mrr": round(mrr, 4),
        "ndcg_at_3": round(ndcg, 4),
    }


def compute_faithfulness_score(text: str, valid_names: list[str], check_rank1: str | None = None) -> dict[str, Any]:
    text_lower = (text or "").lower()
    mentioned_valid = [name for name in valid_names if name.lower() in text_lower]
    valid_lower = {name.lower() for name in valid_names}
    hallucinated = []

    # Candidate named entities are capitalized spans. This is intentionally
    # conservative because Indonesian user-facing text often capitalizes sentence starts.
    candidate_matches = re.finditer(
        r"\b[A-Z][A-Za-z]*(?:\s+[A-Z][A-Za-z]*)*\b",
        text or "",
    )
    common_words = {
        "Pemain",
        "Anda",
        "Museum",
        "Budaya",
        "Objek",
        "Situs",
        "Heritage",
        "Wing",
        "Alternatif",
        "Tidak",
        "Semua",
        "Satu",
        "Dua",
        "Tiga",
    }
    for match in candidate_matches:
        candidate = match.group(0).strip()
        if len(candidate) < 3 or candidate in common_words:
            continue
        prefix = (text or "")[: match.start()].rstrip()
        is_sentence_initial = not prefix or prefix.endswith((".", "!", "?", ":", ";"))
        if is_sentence_initial and " " not in candidate:
            continue
        candidate_lower = candidate.lower()
        is_valid = any(candidate_lower in valid_name or valid_name in candidate_lower for valid_name in valid_lower)
        if not is_valid and candidate not in hallucinated:
            hallucinated.append(candidate)

    faithfulness_score = 1.0 if not hallucinated else max(0.0, 1.0 - (len(hallucinated) * 0.2))
    rank1_mentioned = bool(check_rank1 and check_rank1.lower() in text_lower)
    return {
        "faithfulness_score": round(faithfulness_score, 4),
        "hallucinated_names": hallucinated,
        "hallucinated_entity_count": len(hallucinated),
        "rank1_mentioned": rank1_mentioned,
        "mentioned_valid_sites": mentioned_valid,
    }


CONTEXT_UQ_CORRECTNESS_CHECKS = (
    "context_schema_valid",
    "no_visited_sites_recommended",
    "ranking_exact_match",
    "nav_target_matches_rank_1",
    "nav_target_empty_when_no_recommendations",
    "max_three_recommendations",
    "situation_type_supported",
    "dialogue_intent_supported",
    "recommendation_reason_present",
    "no_coordinates_in_interpretive_fields",
)

DIALOGUE_UQ_CORRECTNESS_CHECKS = (
    "dialogue_schema_valid",
    "subtitle_max_15_words",
    "no_internal_tokens_or_coordinates",
    "options_match_context_order",
    "option_count",
    "empty_recommendations_handled",
    "primary_option_mentioned",
    "invalid_option_returns_error",
)


def _all_checks_pass(result: dict[str, Any], check_names: tuple[str, ...]) -> bool:
    checks = result.get("deterministic_checks", {})
    return all(checks.get(name, False) for name in check_names)


def compute_selective_uq_metrics(
    all_results: list[dict[str, Any]],
    uq_key: str,
    correctness_checks: tuple[str, ...],
) -> dict[str, Any]:
    """Evaluate whether higher UDeg identifies outputs that should be rejected."""
    rows = []
    for result in all_results:
        uq_report = result.get(uq_key, {})
        uncertainty = uq_report.get("udeg")
        if uncertainty is None:
            continue
        rows.append(
            {
                "scenario_id": result.get("scenario_id", ""),
                "uncertainty": float(uncertainty),
                "correct": _all_checks_pass(result, correctness_checks),
            }
        )

    if not rows:
        return {
            "sample_count": 0,
            "status": "unavailable",
            "note": "No UDeg values were available.",
        }

    rows.sort(key=lambda row: row["uncertainty"])
    correctness = [1 if row["correct"] else 0 for row in rows]
    uncertainties = [row["uncertainty"] for row in rows]
    sample_count = len(rows)
    error_count = sample_count - sum(correctness)

    curve = []
    for rejected_count in range(sample_count):
        kept = rows[: sample_count - rejected_count]
        accuracy = sum(1 for row in kept if row["correct"]) / len(kept)
        curve.append(
            {
                "rejection_rate": round(rejected_count / sample_count, 4),
                "coverage": round(len(kept) / sample_count, 4),
                "accuracy": round(accuracy, 4),
            }
        )
    curve.append(
        {
            "rejection_rate": 1.0,
            "coverage": 0.0,
            "accuracy": curve[-1]["accuracy"],
        }
    )

    auarc = 0.0
    for left, right in zip(curve, curve[1:]):
        width = right["rejection_rate"] - left["rejection_rate"]
        auarc += width * (left["accuracy"] + right["accuracy"]) / 2

    correct_uncertainties = [
        uncertainty
        for uncertainty, correct in zip(uncertainties, correctness)
        if correct
    ]
    incorrect_uncertainties = [
        uncertainty
        for uncertainty, correct in zip(uncertainties, correctness)
        if not correct
    ]
    measurable = bool(correct_uncertainties and incorrect_uncertainties)
    error_auroc = (
        float(roc_auc_score([1 - value for value in correctness], uncertainties))
        if measurable
        else None
    )

    return {
        "sample_count": sample_count,
        "correct_count": sum(correctness),
        "error_count": error_count,
        "accuracy_at_zero_rejection": round(sum(correctness) / sample_count, 4),
        "auarc": round(auarc, 4),
        "error_detection_auroc": round(error_auroc, 4) if error_auroc is not None else None,
        "mean_udeg_correct": (
            round(statistics.mean(correct_uncertainties), 4)
            if correct_uncertainties
            else None
        ),
        "mean_udeg_incorrect": (
            round(statistics.mean(incorrect_uncertainties), 4)
            if incorrect_uncertainties
            else None
        ),
        "status": "measurable" if measurable else "no_error_variation",
        "note": (
            "UQ discrimination is measurable because both correct and incorrect outputs exist."
            if measurable
            else "All outputs have the same correctness label; AUARC describes selective accuracy, "
            "but error-discrimination ability cannot be established from this run."
        ),
        "accuracy_rejection_curve": curve,
    }


def _scenario_group(scenario_id: str) -> str:
    match = re.match(r"sc\d+_(.+?)_\d+$", scenario_id or "")
    return match.group(1) if match else "other"


def compute_uq_group_summary(all_results: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for result in all_results:
        grouped.setdefault(_scenario_group(result.get("scenario_id", "")), []).append(result)

    summary = {}
    for group_name, results in grouped.items():
        context_udeg = [
            result.get("context_uq", {}).get("udeg")
            for result in results
            if result.get("context_uq", {}).get("udeg") is not None
        ]
        dialogue_udeg = [
            result.get("dialogue_uq", {}).get("udeg")
            for result in results
            if result.get("dialogue_uq", {}).get("udeg") is not None
        ]
        grounding = [
            result.get("dialogue_uq", {}).get("selected_grounding")
            for result in results
            if result.get("dialogue_uq", {}).get("selected_grounding") is not None
        ]
        summary[group_name] = {
            "scenario_count": len(results),
            "pass_rate": round(
                sum(1 for result in results if result.get("passed", False)) / len(results),
                4,
            ),
            "context_udeg_mean": round(statistics.mean(context_udeg), 4) if context_udeg else None,
            "dialogue_udeg_mean": round(statistics.mean(dialogue_udeg), 4) if dialogue_udeg else None,
            "dialogue_grounding_mean": round(statistics.mean(grounding), 4) if grounding else None,
        }
    return summary


def llm_judge_dimension(
    dimension: str,
    criteria: str,
    context_output: dict[str, Any],
    dialogue_output: dict[str, Any] | None = None,
    extra_context: str = "",
) -> dict[str, Any]:
    if judge_client is None:
        return {"score": 0, "reasoning": "SKIPPED - OPENROUTER_API_KEY is not set", "dimension": dimension}

    context_str = json.dumps(context_output, ensure_ascii=False, indent=2)
    dialogue_str = json.dumps(dialogue_output, ensure_ascii=False, indent=2) if dialogue_output else "N/A"
    system_prompt = (
        "Kamu adalah evaluator kualitas sistem multi-agent NPC pemandu budaya VR. "
        "Evaluasi secara objektif dan kritis. Output hanya JSON valid."
    )
    user_prompt = f"""DIMENSI EVALUASI: {dimension}

CONTEXT OUTPUT:
{context_str}

DIALOGUE OUTPUT:
{dialogue_str}

{f"INFORMASI TAMBAHAN: {extra_context}" if extra_context else ""}

KRITERIA:
{criteria}

LANGKAH EVALUASI:
1. Baca context dan dialogue output dengan teliti.
2. Periksa apakah kriteria terpenuhi.
3. Berikan bukti spesifik.
4. Beri skor 1-5.

SKALA:
1 = sangat buruk
2 = buruk
3 = cukup
4 = baik
5 = sangat baik

OUTPUT JSON:
{{"reasoning": "penjelasan singkat berbasis bukti", "score": 1}}
"""

    try:
        completion_params = settings.llm_model_params_for(500)
        if "temperature" in completion_params:
            completion_params["temperature"] = 0

        response = judge_client.chat.completions.create(
            model=JUDGE_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            **completion_params,
        )
        raw = response.choices[0].message.content.strip()
        raw = re.sub(r"```json\s*|\s*```", "", raw).strip()
        parsed = json.loads(raw)
        return {
            "score": int(parsed.get("score", 0)),
            "reasoning": parsed.get("reasoning", ""),
            "dimension": dimension,
        }
    except Exception as exc:
        logger.warning("LLM judge error for %s: %s", dimension, exc)
        return {"score": 0, "reasoning": f"ERROR: {exc}", "dimension": dimension}


def run_llm_judge_all_dimensions(
    scenario: dict[str, Any],
    context_output: dict[str, Any],
    dialogue_output: dict[str, Any] | None = None,
) -> dict[str, Any]:
    criteria_map = scenario.get("llm_judge_criteria", {})
    default_criteria = {
        "context_relevance": "Output harus relevan dengan ContextOutput aktual dan tidak generik.",
        "faithfulness": "Output tidak boleh menyebut informasi yang tidak ada di context.",
        "navigation_clarity": "Pemain harus jelas tahu ke mana harus pergi.",
        "persona_alignment": "Arif harus hangat, ramah, berbahasa Indonesia natural, dan berperan sebagai pemandu budaya.",
        "language_quality": "Bahasa Indonesia natural, tidak kaku, dan tidak bercampur Inggris.",
        "ui_usefulness": "Teks dan opsi UI harus jelas, berguna, dan tanpa kode internal.",
        "technical_leak_safety": "Tidak ada koordinat, tool, backend token, atau istilah teknis di output user-facing.",
        "user_action_quality": "user_action harus natural dan spesifik terhadap keadaan pemain.",
        "recommendation_reason_quality": "recommendation_reason harus menyebut rank-1 dan memberi alasan logis.",
        "situation_type_consistency": "situation_type harus konsisten dengan jumlah rekomendasi.",
        "dialogue_intent_consistency": "dialogue_intent harus konsisten dengan situation_type.",
        "tool_call_validity": "Agent harus menggunakan bounded tools yang diwajibkan.",
        "reasoning_quality": "Reasoning harus memakai observasi tool, bukan formalitas.",
        "subtitle_quality": "subtitle_output harus ringkas dan bermakna.",
        "consistency": "Output multiple run harus konsisten pada field kritis.",
    }
    results = {}
    for dimension in scenario.get("judge_dimensions", []):
        criteria = criteria_map.get(dimension, default_criteria.get(dimension, f"Evaluasi {dimension} dengan skor 1-5."))
        results[dimension] = llm_judge_dimension(dimension, criteria, context_output, dialogue_output)
    return results


def check_react_trajectory(agent_raw_output: str, required_tools: list[str]) -> dict[str, Any]:
    raw_lower = (agent_raw_output or "").lower()
    tools_called = [tool for tool in required_tools if tool.lower() in raw_lower]
    return {
        "tools_called": tools_called,
        "all_required_called": set(required_tools).issubset(set(tools_called)),
        "tools_missing": [tool for tool in required_tools if tool not in tools_called],
        "tool_call_count": len(tools_called),
        "note": "Current Strands trace is not exposed by the production orchestrator; this is a best-effort raw-output check.",
    }


def build_simulation_request(req_data: dict[str, Any]):
    from schema.models import SimulationRequest

    return SimulationRequest.model_validate(
        {
            "timestamp": req_data["timestamp"],
            "scene": req_data["scene"],
            "playerPosition": req_data["playerPosition"],
            "culturalSites": normalize_site_dicts(req_data),
        }
    )


def run_orchestrator_quietly(func, *args, **kwargs):
    if VERBOSE:
        return func(*args, **kwargs)
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return func(*args, **kwargs)


def copy_uq_report(report: dict[str, Any] | None) -> dict[str, Any]:
    """Return a JSON-safe snapshot of the latest agent UQ report."""
    if not report:
        return {}
    return json.loads(json.dumps(report, ensure_ascii=False))


def run_single_scenario(scenario: dict[str, Any]) -> dict[str, Any]:
    from orchestration.coordinator import HierarchicalOrchestrator
    from agents import get_context_agent, get_dialogue_agent

    scenario_id = scenario["id"]
    logger.info("Running scenario: %s", scenario_id)
    result = {
        "scenario_id": scenario_id,
        "layer": scenario.get("layer"),
        "focus": scenario.get("focus", []),
        "timestamp": datetime.utcnow().isoformat(),
        "deterministic_checks": {},
        "ir_metrics": {},
        "faithfulness": {},
        "llm_judge_scores": {},
        "trajectory": {},
        "context_output": None,
        "dialogue_output": None,
        "context_uq": {},
        "dialogue_uq": {},
        "selection_dialogue_uq": {},
        "errors": [],
        "passed": False,
    }

    try:
        req_data = scenario["request"]
        sites = normalize_site_dicts(req_data)
        sim_req = build_simulation_request(req_data)
        orchestrator = HierarchicalOrchestrator()

        context_cycle = run_orchestrator_quietly(orchestrator.run_context_cycle, sim_req)
        context_output = context_cycle.context.model_dump()
        result["context_output"] = context_output
        result["context_uq"] = copy_uq_report(get_context_agent().last_uq_report)

        dialogue_cycle = run_orchestrator_quietly(orchestrator.run_dialogue_cycle, context_cycle.simulation_id)
        dialogue_output = dialogue_cycle.dialogue.model_dump()
        result["dialogue_output"] = dialogue_output
        result["dialogue_uq"] = copy_uq_report(get_dialogue_agent().last_uq_report)

        checks: dict[str, bool] = {}
        expected_sites = compute_expected_ranking(req_data["playerPosition"], sites)
        expected_ids = [site["id"] for site in expected_sites]
        expected_names = [site["name"] for site in expected_sites]
        actual_ids = [rec["id"] for rec in context_output.get("recommendations", [])]

        checks["context_schema_valid"] = check_schema_valid_context(context_output)
        checks["dialogue_schema_valid"] = check_schema_valid_dialogue(dialogue_output)
        checks["no_visited_sites_recommended"] = check_no_visited_sites(context_output, sites)
        checks["ranking_exact_match"] = actual_ids == expected_ids[: len(actual_ids)]
        checks["nav_target_matches_rank_1"] = check_nav_target_rank1(context_output)
        checks["nav_target_empty_when_no_recommendations"] = (
            context_output.get("nav_target", "") == "" if not expected_ids else True
        )
        checks["max_three_recommendations"] = len(context_output.get("recommendations", [])) <= 3
        checks["situation_type_supported"] = context_output.get("situation_type") in VALID_SITUATION_TYPES
        checks["dialogue_intent_supported"] = context_output.get("dialogue_intent") in VALID_DIALOGUE_INTENTS
        checks["recommendation_reason_present"] = bool(context_output.get("recommendation_reason", "").strip())
        checks["no_coordinates_in_interpretive_fields"] = check_no_technical_leak(
            " ".join(
                [
                    context_output.get("user_action", ""),
                    context_output.get("context_summary", ""),
                    context_output.get("recommendation_reason", ""),
                    context_output.get("situation_type", ""),
                    context_output.get("dialogue_intent", ""),
                ]
            )
        )

        subtitle_ok, subtitle_word_count = check_subtitle_max_15_words(dialogue_output)
        checks["subtitle_max_15_words"] = subtitle_ok
        result["subtitle_word_count"] = subtitle_word_count
        checks["no_internal_tokens_or_coordinates"] = check_no_technical_leak(
            " ".join(
                [
                    dialogue_output.get("subtitle_output", ""),
                    dialogue_output.get("recommendation_dialogue", ""),
                    " ".join(dialogue_output.get("recommendation_options", [])),
                ]
            )
        )
        checks["options_match_context_order"] = check_options_match_context(dialogue_output, context_output)
        checks["option_count"] = len(dialogue_output.get("recommendation_options", [])) == len(expected_names)
        checks["empty_recommendations_handled"] = (
            not dialogue_output.get("recommendation_options", []) if not expected_names else True
        )

        primary_name = (
            scenario.get("expected_dialogue", {}).get("primary_option_mentioned")
            or scenario.get("expected_context", {}).get("recommendation_rank_1")
            or (expected_names[0] if expected_names else "")
        )
        checks["primary_option_mentioned"] = check_primary_option_mentioned(dialogue_output, primary_name)

        selection_request = scenario.get("selection_request")
        if selection_request:
            selected_option = selection_request.get("selectedOption", "")
            expected_error = bool(scenario.get("expected", {}).get("selection_error"))
            try:
                selection_response = run_orchestrator_quietly(
                    orchestrator.handle_recommendation_selection,
                    context_cycle.simulation_id,
                    selected_option,
                )
                result["selection_dialogue_uq"] = copy_uq_report(get_dialogue_agent().last_uq_report)
                checks["invalid_option_returns_error"] = not expected_error
                if not expected_error:
                    checks["selected_option_mentioned"] = (
                        selected_option.lower() in selection_response.subtitle_output.lower()
                    )
            except ValueError:
                checks["invalid_option_returns_error"] = expected_error
        else:
            checks["invalid_option_returns_error"] = True

        result["deterministic_checks"] = checks
        relevant_ids = [site["id"] for site in sites if not site.get("visited", False)]
        result["ir_metrics"] = compute_ir_metrics(actual_ids, relevant_ids)

        faith_cfg = scenario.get("faithfulness_check", {})
        if faith_cfg:
            field_value = context_output.get(faith_cfg.get("field", "recommendation_reason"), "")
            valid_names = faith_cfg.get("valid_site_names", [])
            rank1_name = expected_names[0] if faith_cfg.get("check_rank1_mentioned") and expected_names else None
            result["faithfulness"] = compute_faithfulness_score(field_value, valid_names, rank1_name)

        if scenario.get("llm_judge", False):
            result["llm_judge_scores"] = run_llm_judge_all_dimensions(scenario, context_output, dialogue_output)

        traj_cfg = scenario.get("trajectory_checks", {})
        if traj_cfg:
            result["trajectory"] = check_react_trajectory(
                json.dumps(context_output, ensure_ascii=False),
                traj_cfg.get("required_tools", []),
            )

        required_checks = scenario.get("deterministic_checks", [])
        check_aliases = {
            "schema_valid": ["context_schema_valid", "dialogue_schema_valid"],
            "ranking_exact_match": ["ranking_exact_match"],
            "nav_target_matches_rank_1": ["nav_target_matches_rank_1"],
            "no_visited_sites_recommended": ["no_visited_sites_recommended"],
            "max_three_recommendations": ["max_three_recommendations"],
            "options_match_context_order": ["options_match_context_order"],
            "subtitle_max_15_words": ["subtitle_max_15_words"],
            "no_internal_tokens_or_coordinates": ["no_internal_tokens_or_coordinates"],
            "no_coordinates_in_interpretive_fields": ["no_coordinates_in_interpretive_fields"],
            "recommendation_reason_present": ["recommendation_reason_present"],
            "situation_type_supported": ["situation_type_supported"],
            "dialogue_intent_supported": ["dialogue_intent_supported"],
            "empty_recommendations_handled": ["empty_recommendations_handled"],
            "nav_target_empty_when_no_recommendations": ["nav_target_empty_when_no_recommendations"],
            "primary_option_mentioned": ["primary_option_mentioned"],
            "option_count": ["option_count"],
            "invalid_option_returns_error": ["invalid_option_returns_error"],
        }
        deterministic_pass = all(
            all(checks.get(name, False) for name in check_aliases.get(check, [check]))
            for check in required_checks
        )
        if not required_checks:
            deterministic_pass = all(checks.values())

        judge_pass = True
        for dimension, score_result in result["llm_judge_scores"].items():
            score = score_result.get("score", 0)
            if score == 0:
                continue
            threshold = 5 if dimension == "technical_leak_safety" else 4
            if score < threshold:
                judge_pass = False

        result["passed"] = deterministic_pass and judge_pass

    except Exception as exc:
        logger.error("Error running scenario %s: %s", scenario_id, exc, exc_info=VERBOSE)
        result["errors"].append(str(exc))
        result["passed"] = False

    return result


def run_pass_k_scenario(scenario: dict[str, Any], k: int = 5) -> dict[str, Any]:
    logger.info("Running pass^k for %s with k=%s", scenario["id"], k)
    runs = []
    for index in range(k):
        logger.info("  Run %s/%s", index + 1, k)
        runs.append(run_single_scenario(scenario))
        if judge_client is not None:
            time.sleep(1)

    pass_criteria = scenario.get("reliability_checks", {}).get(
        "pass_criteria",
        ["context_schema_valid", "nav_target_matches_rank_1", "no_visited_sites_recommended"],
    )
    pass_count = sum(
        1
        for run in runs
        if all(run.get("deterministic_checks", {}).get(check, False) for check in pass_criteria)
    )
    judge_stats = {}
    all_dimensions = {
        dimension
        for run in runs
        for dimension in run.get("llm_judge_scores", {}).keys()
    }
    for dimension in all_dimensions:
        scores = [
            run.get("llm_judge_scores", {}).get(dimension, {}).get("score", 0)
            for run in runs
        ]
        scores = [score for score in scores if score > 0]
        if scores:
            judge_stats[dimension] = {
                "mean": round(statistics.mean(scores), 4),
                "std": round(statistics.stdev(scores) if len(scores) > 1 else 0.0, 4),
                "min": min(scores),
                "max": max(scores),
                "scores": scores,
            }

    field_variance = {}
    for field in scenario.get("reliability_checks", {}).get("measure_fields", []):
        values = []
        for run in runs:
            if field in {"user_action", "recommendation_reason"}:
                values.append((run.get("context_output") or {}).get(field, ""))
            elif field == "spoken_output":
                values.append((run.get("dialogue_output") or {}).get(field, ""))
        field_variance[field] = len(set(values))

    return {
        "scenario_id": scenario["id"],
        "layer": "llm_reliability",
        "k": k,
        "pass_count": pass_count,
        "pass_k_score": round(pass_count / k, 4) if k else 0.0,
        "judge_stats": judge_stats,
        "field_variance": field_variance,
        "all_runs": runs,
    }


def run_ablation_stripped(scenario: dict[str, Any], stripped_fields: list[str]) -> dict[str, Any]:
    from orchestration.coordinator import HierarchicalOrchestrator
    from schema.models import ContextOutput
    from agents import get_context_agent, get_dialogue_agent

    result = {
        "scenario_id": scenario["id"] + "_stripped",
        "layer": "llm_ablation_run_b",
        "deterministic_checks": {},
        "llm_judge_scores": {},
        "context_output": None,
        "dialogue_output": None,
        "context_uq": {},
        "dialogue_uq": {},
        "errors": [],
        "passed": False,
    }
    try:
        orchestrator = HierarchicalOrchestrator()
        sim_req = build_simulation_request(scenario["request"])
        context_cycle = run_orchestrator_quietly(orchestrator.run_context_cycle, sim_req)
        stripped_context = context_cycle.context.model_dump()
        result["context_uq"] = copy_uq_report(get_context_agent().last_uq_report)
        for field in stripped_fields:
            if field in stripped_context:
                stripped_context[field] = "Informasi alasan rekomendasi tidak tersedia."

        session = orchestrator.pool.get_session(context_cycle.simulation_id)
        if session is None:
            raise ValueError("Session not found for ablation run.")
        updated_context = ContextOutput.model_validate(stripped_context)
        session = session.model_copy(update={"context": updated_context})
        orchestrator.pool.save_session(session)

        dialogue_cycle = run_orchestrator_quietly(orchestrator.run_dialogue_cycle, context_cycle.simulation_id)
        dialogue_output = dialogue_cycle.dialogue.model_dump()
        result["context_output"] = stripped_context
        result["dialogue_output"] = dialogue_output
        result["dialogue_uq"] = copy_uq_report(get_dialogue_agent().last_uq_report)
        result["deterministic_checks"] = {
            "dialogue_schema_valid": check_schema_valid_dialogue(dialogue_output),
            "options_match_context_order": check_options_match_context(dialogue_output, stripped_context),
            "no_internal_tokens_or_coordinates": check_no_technical_leak(
                " ".join(
                    [
                        dialogue_output.get("spoken_output", ""),
                        dialogue_output.get("subtitle_output", ""),
                        dialogue_output.get("recommendation_dialogue", ""),
                    ]
                )
            ),
        }
        result["llm_judge_scores"] = run_llm_judge_all_dimensions(scenario, stripped_context, dialogue_output)
        result["passed"] = all(result["deterministic_checks"].values())
    except Exception as exc:
        logger.error("Ablation stripped run error: %s", exc, exc_info=VERBOSE)
        result["errors"].append(str(exc))
    return result


def run_ablation_scenario(scenario: dict[str, Any]) -> dict[str, Any]:
    logger.info("Running ablation: %s", scenario["id"])
    stripped_fields = scenario.get("ablation_config", {}).get("stripped_fields", ["recommendation_reason"])
    run_a = run_single_scenario(scenario)
    run_b = run_ablation_stripped(scenario, stripped_fields)
    dimensions = scenario.get("judge_dimensions", [])
    delta = {}
    for dimension in dimensions:
        score_a = run_a.get("llm_judge_scores", {}).get(dimension, {}).get("score", 0)
        score_b = run_b.get("llm_judge_scores", {}).get(dimension, {}).get("score", 0)
        if score_a > 0 and score_b > 0:
            delta[dimension] = round(score_a - score_b, 4)
    hypothesis_confirmed = all(
        delta.get(dimension, 0) > 0
        for dimension in ["context_relevance", "navigation_clarity"]
        if dimension in delta
    )
    return {
        "scenario_id": scenario["id"],
        "layer": "llm_ablation",
        "run_a_scores": {
            dimension: run_a.get("llm_judge_scores", {}).get(dimension, {}).get("score", 0)
            for dimension in dimensions
        },
        "run_b_scores": {
            dimension: run_b.get("llm_judge_scores", {}).get(dimension, {}).get("score", 0)
            for dimension in dimensions
        },
        "delta": delta,
        "hypothesis_confirmed": hypothesis_confirmed,
        "ablation_hypothesis": scenario.get("ablation_hypothesis", ""),
        "run_a_detail": run_a,
        "run_b_detail": run_b,
    }


def save_figure(fig, filename: str) -> None:
    path = FIGURES_DIR / filename
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    logger.info("Saved figure: %s", path)


def plot_deterministic_check_pass_rate(all_results: list[dict[str, Any]]) -> None:
    structural = [result for result in all_results if result.get("layer") == "structural"]
    llm_layer = [result for result in all_results if str(result.get("layer", "")).startswith("llm")]

    def rates(results: list[dict[str, Any]]) -> dict[str, float]:
        grouped: dict[str, list[int]] = {}
        for result in results:
            for name, passed in result.get("deterministic_checks", {}).items():
                grouped.setdefault(name, []).append(1 if passed else 0)
        return {name: sum(values) / len(values) for name, values in grouped.items() if values}

    struct_rates = rates(structural)
    llm_rates = rates(llm_layer)
    keys = sorted(set(struct_rates) | set(llm_rates))
    if not keys:
        return
    x = np.arange(len(keys))
    width = 0.35
    fig, ax = plt.subplots(figsize=(16, 7))
    b1 = ax.bar(x - width / 2, [struct_rates.get(key, 0) for key in keys], width, label="Structural", color="#2196F3")
    b2 = ax.bar(x + width / 2, [llm_rates.get(key, 0) for key in keys], width, label="LLM layer", color="#FF9800")
    ax.set_ylabel("Pass rate")
    ax.set_title("Deterministic Check Pass Rate")
    ax.set_xticks(x)
    ax.set_xticklabels(keys, rotation=45, ha="right", fontsize=8)
    ax.set_ylim(0, 1.15)
    ax.legend()
    ax.bar_label(b1, fmt="%.2f", fontsize=7)
    ax.bar_label(b2, fmt="%.2f", fontsize=7)
    plt.tight_layout()
    save_figure(fig, "01_deterministic_check_pass_rate.png")


def plot_llm_judge_radar(all_results: list[dict[str, Any]]) -> None:
    chart_specs = [
        (
            ["context_relevance", "faithfulness", "navigation_clarity", "persona_alignment", "language_quality", "ui_usefulness", "technical_leak_safety", "subtitle_quality"],
            "Dialogue Agent - LLM Judge Radar",
            "02_dialogue_agent_radar.png",
        ),
        (
            ["user_action_quality", "recommendation_reason_quality", "faithfulness", "situation_type_consistency", "dialogue_intent_consistency", "tool_call_validity", "reasoning_quality"],
            "Context Agent - LLM Judge Radar",
            "03_context_agent_radar.png",
        ),
    ]
    for dimensions, title, filename in chart_specs:
        means = []
        labels = []
        for dimension in dimensions:
            scores = [
                result.get("llm_judge_scores", {}).get(dimension, {}).get("score", 0)
                for result in all_results
            ]
            scores = [score for score in scores if score > 0]
            if scores:
                labels.append(dimension)
                means.append(statistics.mean(scores))
        if not means:
            continue
        angles = [index / float(len(labels)) * 2 * math.pi for index in range(len(labels))]
        angles += angles[:1]
        means_plot = means + means[:1]
        fig, ax = plt.subplots(figsize=(8, 8), subplot_kw={"polar": True})
        ax.plot(angles, means_plot, "o-", linewidth=2, color="#1976D2")
        ax.fill(angles, means_plot, alpha=0.25, color="#1976D2")
        ax.set_xticks(angles[:-1])
        ax.set_xticklabels(labels, fontsize=9)
        ax.set_ylim(0, 5)
        ax.set_yticks([1, 2, 3, 4, 5])
        ax.set_title(title, fontweight="bold", pad=20)
        plt.tight_layout()
        save_figure(fig, filename)


def plot_scenario_heatmap(all_results: list[dict[str, Any]]) -> None:
    if not all_results:
        return
    scenario_ids = [result.get("scenario_id", "") for result in all_results]
    columns = sorted(
        {
            key
            for result in all_results
            for key in list(result.get("deterministic_checks", {}).keys())
            + list(result.get("llm_judge_scores", {}).keys())
        }
    )
    if not columns:
        return
    matrix = []
    for result in all_results:
        row = []
        for column in columns:
            if column in result.get("deterministic_checks", {}):
                row.append(1.0 if result["deterministic_checks"][column] else 0.0)
            elif column in result.get("llm_judge_scores", {}):
                score = result["llm_judge_scores"][column].get("score", 0)
                row.append(score / 5 if score > 0 else np.nan)
            else:
                row.append(np.nan)
        matrix.append(row)
    matrix_np = np.array(matrix, dtype=float)
    fig, ax = plt.subplots(figsize=(max(14, len(columns) * 0.75), max(8, len(scenario_ids) * 0.45)))
    im = ax.imshow(matrix_np, cmap="RdYlGn", aspect="auto", vmin=0, vmax=1)
    ax.set_xticks(np.arange(len(columns)))
    ax.set_yticks(np.arange(len(scenario_ids)))
    ax.set_xticklabels(columns, rotation=60, ha="right", fontsize=7)
    ax.set_yticklabels(scenario_ids, fontsize=7)
    plt.colorbar(im, ax=ax, label="Score")
    ax.set_title("Per-Scenario x Per-Metric Heatmap", fontweight="bold")
    plt.tight_layout()
    save_figure(fig, "04_scenario_metric_heatmap.png")


def plot_reliability_boxplot(pass_k_result: dict[str, Any] | None) -> None:
    if not pass_k_result:
        return
    judge_stats = pass_k_result.get("judge_stats", {})
    dimensions = [dimension for dimension, stats in judge_stats.items() if stats.get("scores")]
    if not dimensions:
        return
    fig, ax = plt.subplots(figsize=(12, 6))
    bp = ax.boxplot([judge_stats[dimension]["scores"] for dimension in dimensions], labels=dimensions, patch_artist=True)
    for patch in bp["boxes"]:
        patch.set_facecolor("#42A5F5")
        patch.set_alpha(0.7)
    ax.axhline(y=4, color="green", linestyle="--", alpha=0.5)
    ax.set_ylim(0, 5.5)
    ax.set_ylabel("Judge score")
    ax.set_title(f"Reliability Distribution - pass^k={pass_k_result.get('k')}", fontweight="bold")
    plt.xticks(rotation=30, ha="right")
    plt.tight_layout()
    save_figure(fig, "05_reliability_boxplot.png")


def plot_ablation_delta(ablation_result: dict[str, Any] | None) -> None:
    if not ablation_result:
        return
    run_a = ablation_result.get("run_a_scores", {})
    run_b = ablation_result.get("run_b_scores", {})
    dimensions = [dimension for dimension in run_a if run_a.get(dimension, 0) > 0 or run_b.get(dimension, 0) > 0]
    if not dimensions:
        return
    x = np.arange(len(dimensions))
    width = 0.3
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))
    ax1.bar(x - width / 2, [run_a.get(dim, 0) for dim in dimensions], width, label="Run A full context", color="#2196F3")
    ax1.bar(x + width / 2, [run_b.get(dim, 0) for dim in dimensions], width, label="Run B stripped", color="#FF5722")
    ax1.axhline(y=4, color="green", linestyle="--", alpha=0.4)
    ax1.set_xticks(x)
    ax1.set_xticklabels(dimensions, rotation=30, ha="right")
    ax1.set_ylim(0, 5.5)
    ax1.set_ylabel("Judge score")
    ax1.legend()
    delta = ablation_result.get("delta", {})
    delta_values = [delta.get(dim, 0) for dim in dimensions]
    ax2.bar(x, delta_values, color=["#4CAF50" if value > 0 else "#F44336" for value in delta_values])
    ax2.axhline(y=0, color="black", linewidth=1)
    ax2.set_xticks(x)
    ax2.set_xticklabels(dimensions, rotation=30, ha="right")
    ax2.set_ylabel("Delta A - B")
    ax2.set_title("Ablation Delta", fontweight="bold")
    plt.tight_layout()
    save_figure(fig, "06_ablation_delta.png")


def plot_ir_metrics_summary(all_results: list[dict[str, Any]]) -> None:
    metrics = ["precision_at_3", "recall_at_3", "mrr", "ndcg_at_3"]
    structural = [result for result in all_results if result.get("layer") == "structural"]
    llm_layer = [result for result in all_results if str(result.get("layer", "")).startswith("llm")]

    def averages(results: list[dict[str, Any]]) -> list[float]:
        values = []
        for metric in metrics:
            metric_values = [result.get("ir_metrics", {}).get(metric) for result in results if metric in result.get("ir_metrics", {})]
            values.append(statistics.mean(metric_values) if metric_values else 0.0)
        return values

    x = np.arange(len(metrics))
    width = 0.35
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.bar(x - width / 2, averages(structural), width, label="Structural")
    ax.bar(x + width / 2, averages(llm_layer), width, label="LLM scenarios")
    ax.set_xticks(x)
    ax.set_xticklabels(metrics)
    ax.set_ylim(0, 1.1)
    ax.set_ylabel("Score")
    ax.set_title("IR Ranking Metrics - Deterministic Backend Verification", fontweight="bold")
    ax.legend()
    plt.tight_layout()
    save_figure(fig, "07_ir_metrics_summary.png")


def plot_uq_accuracy_rejection(summary: dict[str, Any]) -> None:
    validation = summary.get("uncertainty_validation", {})
    chart_specs = [
        ("context_agent", "Context Agent", "#1976D2"),
        ("dialogue_agent", "Dialogue Agent", "#D84315"),
    ]
    fig, ax = plt.subplots(figsize=(10, 6))
    plotted = False
    for key, label, color in chart_specs:
        curve = validation.get(key, {}).get("accuracy_rejection_curve", [])
        if not curve:
            continue
        ax.plot(
            [point["rejection_rate"] for point in curve],
            [point["accuracy"] for point in curve],
            marker="o",
            linewidth=2,
            markersize=3,
            label=f"{label} (AUARC={validation[key].get('auarc', 0):.3f})",
            color=color,
        )
        plotted = True
    if not plotted:
        plt.close(fig)
        return
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1.05)
    ax.set_xlabel("Rejection rate (highest UDeg rejected first)")
    ax.set_ylabel("Accuracy on retained scenarios")
    ax.set_title("UQ Selective Accuracy-Rejection Curve", fontweight="bold")
    ax.grid(alpha=0.25)
    ax.legend()
    plt.tight_layout()
    save_figure(fig, "08_uq_accuracy_rejection_curve.png")


def aggregate_results(all_results: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(all_results)
    passed = sum(1 for result in all_results if result.get("passed", False))
    check_values = [
        value
        for result in all_results
        for value in result.get("deterministic_checks", {}).values()
    ]
    check_pass_rate = (
        sum(1 for value in check_values if value) / len(check_values)
        if check_values
        else 0.0
    )
    dimension_scores: dict[str, list[int]] = {}
    for result in all_results:
        for dimension, score_result in result.get("llm_judge_scores", {}).items():
            score = score_result.get("score", 0)
            if score > 0:
                dimension_scores.setdefault(dimension, []).append(score)
    judge_summary = {
        dimension: {
            "mean": round(statistics.mean(scores), 4),
            "std": round(statistics.stdev(scores) if len(scores) > 1 else 0.0, 4),
            "n": len(scores),
            "pass_rate": round(sum(1 for score in scores if score >= 4) / len(scores), 4),
        }
        for dimension, scores in dimension_scores.items()
    }
    ir_summary = {}
    for metric in ["precision_at_3", "recall_at_3", "mrr", "ndcg_at_3"]:
        values = [result.get("ir_metrics", {}).get(metric) for result in all_results if metric in result.get("ir_metrics", {})]
        if values:
            ir_summary[metric] = round(statistics.mean(values), 4)
    faithfulness_values = [
        result.get("faithfulness", {}).get("faithfulness_score")
        for result in all_results
        if result.get("faithfulness")
    ]
    faithfulness_values = [value for value in faithfulness_values if value is not None]
    uncertainty_validation = {
        "context_agent": compute_selective_uq_metrics(
            all_results,
            "context_uq",
            CONTEXT_UQ_CORRECTNESS_CHECKS,
        ),
        "dialogue_agent": compute_selective_uq_metrics(
            all_results,
            "dialogue_uq",
            DIALOGUE_UQ_CORRECTNESS_CHECKS,
        ),
    }
    return {
        "total_scenarios": total,
        "passed": passed,
        "overall_pass_rate": round(passed / total, 4) if total else 0.0,
        "check_pass_rate": round(check_pass_rate, 4),
        "judge_summary": judge_summary,
        "ir_summary": ir_summary,
        "faithfulness_avg": round(statistics.mean(faithfulness_values), 4) if faithfulness_values else None,
        "uncertainty_validation": uncertainty_validation,
        "uq_group_summary": compute_uq_group_summary(all_results),
        "timestamp": datetime.utcnow().isoformat(),
        "judge_model": JUDGE_MODEL,
        "judge_temperature": 0,
        "cohen_kappa_note": "Use exported per-dimension scores for human/judge agreement analysis.",
        "cohen_kappa_function_available": callable(cohen_kappa_score),
    }


def load_scenarios() -> list[dict[str, Any]]:
    with SCENARIOS_PATH.open(encoding="utf-8") as file:
        data = json.load(file)
    if isinstance(data, list):
        return data
    return data["scenarios"]


def main() -> int:
    global VERBOSE
    parser = argparse.ArgumentParser(description="Multi-Agent Evaluation Runner")
    parser.add_argument("--agent", choices=["context", "dialogue", "e2e", "reliability", "ablation", "all"], default="all")
    parser.add_argument("--json", action="store_true", help="Print JSON summary")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--skip-llm-judge", action="store_true", help="Skip LLM judge calls")
    parser.add_argument("--scenarios", nargs="+", help="Specific scenario IDs to run")
    args = parser.parse_args()
    VERBOSE = args.verbose
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    scenarios = load_scenarios()
    if args.scenarios:
        requested = set(args.scenarios)
        scenarios = [scenario for scenario in scenarios if scenario["id"] in requested]
    if args.skip_llm_judge:
        for scenario in scenarios:
            scenario["llm_judge"] = False
    if args.agent == "context":
        scenarios = [scenario for scenario in scenarios if "context_agent" in scenario.get("focus", [])]
    elif args.agent == "dialogue":
        scenarios = [scenario for scenario in scenarios if "dialogue_agent" in scenario.get("focus", [])]
    elif args.agent == "reliability":
        scenarios = [scenario for scenario in scenarios if scenario.get("layer") == "llm_reliability"]
    elif args.agent == "ablation":
        scenarios = [scenario for scenario in scenarios if scenario.get("layer") == "llm_ablation"]

    all_results = []
    pass_k_result = None
    ablation_result = None
    for scenario in scenarios:
        layer = scenario.get("layer", "structural")
        if layer == "llm_reliability":
            pass_k_result = run_pass_k_scenario(scenario, scenario.get("repeat_k", 5))
            all_results.extend(pass_k_result.get("all_runs", []))
        elif layer == "llm_ablation":
            ablation_result = run_ablation_scenario(scenario)
            if ablation_result.get("run_a_detail"):
                all_results.append(ablation_result["run_a_detail"])
            if ablation_result.get("run_b_detail"):
                all_results.append(ablation_result["run_b_detail"])
        else:
            all_results.append(run_single_scenario(scenario))

    summary = aggregate_results(all_results)
    if pass_k_result:
        summary["reliability"] = {
            "pass_k_score": pass_k_result["pass_k_score"],
            "k": pass_k_result["k"],
            "judge_stats": pass_k_result.get("judge_stats", {}),
            "field_variance": pass_k_result.get("field_variance", {}),
        }
    if ablation_result:
        summary["ablation"] = {
            "delta": ablation_result.get("delta", {}),
            "hypothesis_confirmed": ablation_result.get("hypothesis_confirmed", False),
        }

    logger.info("Generating visualizations...")
    if all_results:
        plot_deterministic_check_pass_rate(all_results)
        plot_llm_judge_radar(all_results)
        plot_scenario_heatmap(all_results)
        plot_ir_metrics_summary(all_results)
        plot_uq_accuracy_rejection(summary)
    if pass_k_result:
        plot_reliability_boxplot(pass_k_result)
    if ablation_result:
        plot_ablation_delta(ablation_result)

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    results_path = RESULTS_DIR / f"eval_results_{timestamp}.json"
    full_output = {
        "summary": summary,
        "scenario_results": all_results,
        "pass_k": pass_k_result,
        "ablation": ablation_result,
    }
    with results_path.open("w", encoding="utf-8") as file:
        json.dump(full_output, file, indent=2, ensure_ascii=False, default=str)
    logger.info("Results saved: %s", results_path)

    if args.json:
        print(json.dumps(summary, indent=2, ensure_ascii=False))
    else:
        print("\n" + "=" * 60)
        print("EVALUATION SUMMARY")
        print("=" * 60)
        print(f"Total scenarios:     {summary['total_scenarios']}")
        print(f"Passed:              {summary['passed']}")
        print(f"Overall pass rate:   {summary['overall_pass_rate']:.2%}")
        print(f"Check pass rate:     {summary['check_pass_rate']:.2%}")
        if summary.get("faithfulness_avg") is not None:
            print(f"Faithfulness avg:    {summary['faithfulness_avg']:.4f}")
        if summary.get("ir_summary"):
            print("\nIR Metrics (deterministic ranking verification):")
            for name, value in summary["ir_summary"].items():
                print(f"  {name}: {value:.4f}")
        if summary.get("judge_summary"):
            print("\nLLM Judge Scores (mean +/- std):")
            for dimension, stats in summary["judge_summary"].items():
                print(f"  {dimension}: {stats['mean']:.2f} +/- {stats['std']:.2f} (n={stats['n']}, pass={stats['pass_rate']:.2%})")
        if summary.get("uncertainty_validation"):
            print("\nUQ Selective Validation:")
            for agent_name, metrics in summary["uncertainty_validation"].items():
                auroc = metrics.get("error_detection_auroc")
                auroc_text = f"{auroc:.4f}" if auroc is not None else "N/A (no error variation)"
                print(
                    f"  {agent_name}: AUARC={metrics.get('auarc', 0):.4f}, "
                    f"error AUROC={auroc_text}, errors={metrics.get('error_count', 0)}"
                )
        if summary.get("reliability"):
            reliability = summary["reliability"]
            print(f"\nReliability (pass^{reliability['k']}): {reliability['pass_k_score']:.4f}")
        if summary.get("ablation"):
            ablation = summary["ablation"]
            confirmed = "Confirmed" if ablation["hypothesis_confirmed"] else "Not confirmed"
            print(f"\nAblation hypothesis: {confirmed}")
            print(f"Delta scores: {ablation['delta']}")
        print(f"\nFigures saved to: {FIGURES_DIR}/")
        print(f"Results saved to:  {results_path}")
        print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
