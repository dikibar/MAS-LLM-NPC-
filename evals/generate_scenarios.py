"""
Scenario dataset expander for the UQ + LLM-as-a-Judge benchmark.

Extends evals/scenarios.json from its current size (50) to a target size
(default 100) while preserving:
  - the existing scenarios untouched (IDs sc01..sc50),
  - the group proportions 15:10:15:10
    (context_normal : context_edge : dialogue_normal : dialogue_risk),
  - the exact per-group JSON shape (copied from same-group donor scenarios),
  - ground-truth consistency: expected_context / expected_dialogue are
    recomputed with the same deterministic ranking rule the Coordinator uses
    (3D Euclidean distance to unvisited sites, tie-break by lowercase name,
    top-3).

Generation is fully deterministic given --seed, so the dataset is
reproducible for the thesis.

Usage:
    python evals/generate_scenarios.py --dry-run          # preview only
    python evals/generate_scenarios.py                    # write (with backup)
    python evals/generate_scenarios.py --target 100 --seed 42
"""

import argparse
import copy
import json
import math
import random
import re
import shutil
from datetime import datetime, timedelta
from pathlib import Path

SCENARIOS_PATH = Path(__file__).parent / "scenarios.json"

GROUP_ORDER = ("context_normal", "context_edge", "dialogue_normal", "dialogue_risk")
GROUP_RATIO = {  # existing 15:10:15:10 proportions
    "context_normal": 15,
    "context_edge": 10,
    "dialogue_normal": 15,
    "dialogue_risk": 10,
}

# Canonical registry of the 8 cultural sites (identical across all scenarios).
CANONICAL_SITES = [
    {"id": "Surabi", "name": "Surabi", "cultural_position": "-1.34956, 1.52654, 23.7432"},
    {"id": "Angklung", "name": "Angklung", "cultural_position": "14.62413, 1.37554, 18.67057"},
    {"id": "Julang Ngapak", "name": "Julang Ngapak", "cultural_position": "21.48713, 2.18983, 17.03246"},
    {"id": "Kujang", "name": "Kujang", "cultural_position": "19.72784, 0.30118, 21.86564"},
    {"id": "Badak Heuay", "name": "Badak Heuay", "cultural_position": "6.84231, 1.18492, 28.41675"},
    {"id": "Tagog Anjing", "name": "Tagog Anjing", "cultural_position": "24.31892, 1.04735, 10.59284"},
    {"id": "Tari Jaipong", "name": "Tari Jaipong", "cultural_position": "11.27364, 1.66247, 6.73451"},
    {"id": "Suling Sunda", "name": "Suling Sunda", "cultural_position": "27.95618, 1.23804, 24.37192"},
]
ALL_SITE_NAMES = [site["name"] for site in CANONICAL_SITES]

SCENES = ("Heritage_Museum_Wing_A", "Heritage_Museum_Wing_B")


def _parse_vector3(raw: str) -> tuple[float, float, float]:
    x, y, z = (float(part.strip()) for part in raw.split(","))
    return x, y, z


def _distance(player_position: str, site_position: str) -> float:
    ax, ay, az = _parse_vector3(player_position)
    bx, by, bz = _parse_vector3(site_position)
    return math.sqrt((ax - bx) ** 2 + (ay - by) ** 2 + (az - bz) ** 2)


def rank_unvisited(player_position: str, sites: list[dict], visited: dict[str, bool]) -> list[dict]:
    """Mirror of coordinator._rank_unvisited_sites: Euclid, tie-break name, top-3."""
    unvisited = [site for site in sites if not visited[site["name"]]]
    ranked = sorted(
        unvisited,
        key=lambda site: (_distance(player_position, site["cultural_position"]), site["name"].lower()),
    )
    return ranked[:3]


def scenario_group(scenario_id: str) -> str:
    match = re.match(r"sc\d+_(.+?)_\d+$", scenario_id)
    return match.group(1) if match else "other"


def pick_donor(existing: list[dict], group: str, *, with_selection: bool, alias_payload: bool) -> dict:
    """Find a same-group donor scenario matching the requested shape."""
    for scenario in existing:
        if scenario_group(scenario["id"]) != group:
            continue
        if "llm_judge_criteria" in scenario:
            continue  # first-of-group carries bespoke criteria text; skip as donor
        has_selection = "selection_request" in scenario
        is_alias = "culturalObjects" in scenario["request"]
        if has_selection == with_selection and is_alias == alias_payload:
            return scenario
    # Relax the alias constraint if no exact match exists.
    for scenario in existing:
        if scenario_group(scenario["id"]) != group:
            continue
        if "llm_judge_criteria" in scenario:
            continue
        if ("selection_request" in scenario) == with_selection:
            return scenario
    raise ValueError(f"No donor found for group={group} selection={with_selection}")


def build_request(
    rng: random.Random,
    timestamp: str,
    scene: str,
    player_position: str,
    visited: dict[str, bool],
    alias_payload: bool,
) -> dict:
    if alias_payload:
        sites_payload = [
            {
                "id": site["id"],
                "name": site["name"],
                "coordinate": site["cultural_position"],
                "isObjectVisited": visited[site["name"]],
            }
            for site in CANONICAL_SITES
        ]
        return {
            "timestamp": timestamp,
            "scene": scene,
            "playerPosition": player_position,
            "culturalObjects": sites_payload,
        }
    sites_payload = [
        {
            "id": site["id"],
            "name": site["name"],
            "cultural_position": site["cultural_position"],
            "visited": visited[site["name"]],
        }
        for site in CANONICAL_SITES
    ]
    return {
        "timestamp": timestamp,
        "scene": scene,
        "playerPosition": player_position,
        "culturalSites": sites_payload,
    }


def random_player_position(rng: random.Random) -> str:
    # Bounds derived from the site coordinate envelope (x: -2..28, z: 6..29).
    x = round(rng.uniform(-2.0, 28.0), 1)
    z = round(rng.uniform(6.0, 29.0), 1)
    return f"{x}, 1.0, {z}"


def visited_profile(rng: random.Random, group: str, edge_case: str | None) -> dict[str, bool]:
    names = list(ALL_SITE_NAMES)
    if edge_case == "single_remaining":
        keep = rng.choice(names)
        return {name: name != keep for name in names}
    if edge_case == "all_visited":
        return {name: True for name in names}
    if edge_case == "many_visited":
        unvisited = rng.sample(names, 3)  # heavily visited but still 3 candidates
        return {name: name not in unvisited for name in names}
    if group == "dialogue_risk":
        visited_count = rng.choice([4, 5])  # complex visited mix, >=3 candidates
    else:
        visited_count = rng.choice([0, 1, 2, 3, 4, 5])
    chosen = rng.sample(names, visited_count)
    return {name: name in chosen for name in names}


def build_scenario(
    rng: random.Random,
    existing: list[dict],
    group: str,
    global_index: int,
    group_index: int,
    edge_case: str | None,
    with_selection: bool,
    alias_payload: bool,
    base_time: datetime,
) -> dict:
    visited = visited_profile(rng, group, edge_case)
    player_position = random_player_position(rng)
    ranked = rank_unvisited(player_position, CANONICAL_SITES, visited)
    ranked_names = [site["name"] for site in ranked]

    timestamp = (base_time + timedelta(minutes=67 * global_index)).strftime("%Y-%m-%dT%H:%M:00Z")
    scene = SCENES[global_index % len(SCENES)]

    donor = pick_donor(existing, group, with_selection=with_selection, alias_payload=alias_payload)
    scenario = copy.deepcopy(donor)

    scenario["id"] = f"sc{global_index:02d}_{group}_{group_index:02d}"
    scenario["request"] = build_request(rng, timestamp, scene, player_position, visited, alias_payload)

    if not ranked_names:
        scenario["expected_context"] = {
            "recommendation_count": 0,
            "nav_target": "",
            "situation_type": "all_sites_visited",
        }
    elif len(ranked_names) == 1:
        scenario["expected_context"] = {
            "recommendation_count": 1,
            "nav_target": ranked_names[0],
            "situation_type": "single_recommendation",
            "recommendation_rank_1": ranked_names[0],
        }
    else:
        scenario["expected_context"] = {
            "recommendation_count": len(ranked_names),
            "nav_target": ranked_names[0],
            "situation_type": "multiple_recommendations",
            "recommendation_rank_1": ranked_names[0],
        }

    scenario["expected_dialogue"] = {
        "recommendation_options": ranked_names,
        "subtitle_max_words": 15,
        "no_technical_leak": True,
    }
    scenario["faithfulness_check"] = {
        "field": "recommendation_reason",
        "valid_site_names": list(ALL_SITE_NAMES),
        "check_no_hallucinated_names": True,
        "check_rank1_mentioned": bool(ranked_names),
    }

    if with_selection:
        # Valid selection: pick an alternative (rank 2 when available, else rank 1).
        selected = ranked_names[1] if len(ranked_names) > 1 else ranked_names[0]
        scenario["selection_request"] = {"selectedOption": selected}
        scenario["expected"] = {"selection_error": False, "error_code": 200}
    else:
        scenario.pop("selection_request", None)
        scenario.pop("expected", None)

    return scenario


def edge_case_cycle(count: int) -> list[str | None]:
    """Rotate the four context_edge sub-cases, mirroring the original dataset mix."""
    cycle = ["single_remaining", "many_visited", "all_visited", "many_visited", "single_remaining"]
    return [cycle[i % len(cycle)] for i in range(count)]


def main() -> int:
    parser = argparse.ArgumentParser(description="Expand scenarios.json to a target scenario count")
    parser.add_argument("--target", type=int, default=100, help="Total scenario count after expansion (default 100)")
    parser.add_argument("--seed", type=int, default=42, help="RNG seed for reproducibility (default 42)")
    parser.add_argument("--output", type=Path, default=SCENARIOS_PATH, help="Output path (default: overwrite scenarios.json, with backup)")
    parser.add_argument("--dry-run", action="store_true", help="Print the plan and one sample scenario; write nothing")
    args = parser.parse_args()

    data = json.loads(SCENARIOS_PATH.read_text(encoding="utf-8"))
    existing = data["scenarios"]
    current_total = len(existing)
    if args.target <= current_total:
        print(f"Dataset already has {current_total} scenarios (target {args.target}); nothing to do.")
        return 0

    extra_total = args.target - current_total
    ratio_sum = sum(GROUP_RATIO.values())
    extra_per_group = {
        group: round(extra_total * GROUP_RATIO[group] / ratio_sum) for group in GROUP_ORDER
    }
    # Fix rounding drift so the group counts sum exactly to extra_total.
    drift = extra_total - sum(extra_per_group.values())
    extra_per_group[GROUP_ORDER[0]] += drift

    group_counts = {group: sum(1 for s in existing if scenario_group(s["id"]) == group) for group in GROUP_ORDER}

    rng = random.Random(args.seed)
    base_time = datetime(2026, 5, 2, 9, 0)
    new_scenarios: list[dict] = []
    global_index = current_total

    for group in GROUP_ORDER:
        count = extra_per_group[group]
        edge_cases = edge_case_cycle(count) if group == "context_edge" else [None] * count
        for offset in range(count):
            global_index += 1
            group_index = group_counts[group] + offset + 1
            with_selection = group in ("dialogue_normal", "dialogue_risk") and offset % 4 == 2
            alias_payload = (
                (group == "context_normal" and offset % 7 == 4)
                or (group == "context_edge" and offset % 5 == 3)
                or (group == "dialogue_risk" and offset % 6 == 4)
            )
            edge_case = edge_cases[offset]
            if edge_case == "all_visited":
                with_selection = False  # no options to select when nothing remains
            new_scenarios.append(
                build_scenario(
                    rng, existing, group, global_index, group_index,
                    edge_case, with_selection, alias_payload, base_time,
                )
            )

    plan = {group: extra_per_group[group] for group in GROUP_ORDER}
    print(f"Existing scenarios : {current_total}")
    print(f"New scenarios      : {len(new_scenarios)}  {plan}")
    print(f"Total after write  : {current_total + len(new_scenarios)}")

    if args.dry_run:
        print("\n--dry-run: sample of the first generated scenario:")
        print(json.dumps(new_scenarios[0], ensure_ascii=False, indent=2)[:2500])
        return 0

    if args.output == SCENARIOS_PATH:
        backup = SCENARIOS_PATH.with_name(f"scenarios_backup_{current_total}.json")
        if not backup.exists():
            shutil.copy2(SCENARIOS_PATH, backup)
            print(f"Backup written     : {backup.name}")

    data["scenarios"] = existing + new_scenarios
    args.output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Dataset written    : {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
