"""
Context Agent — Environmental State & Cultural Site Recommendation Engine
=========================================================================
Module  : Profile → Perception → Self-Action → Mutual Interaction → Evolution
Role    : Environmental State Engine & Cultural Recommender
Layer   : Child Node (Publisher)

Five-module mapping
-------------------
Profile         : Specialist in objective environmental awareness, scene-state
                  tracking, and cultural site recommendation by position/visit status.
Perception      : Consumes raw VR sensor data via three tool calls:
                    • tool_get_environment_data  — scene + event deltas
                    • tool_get_user_status       — player position
                    • tool_get_cultural_sites    — full site registry with visited flags
Self-Action     : (a) Distils raw signals into a structured JSON state summary.
                  (b) Selects 2–3 nearby UNVISITED sites as ranked recommendations.
Mutual Interaction: Publisher — writes a ContextOutput JSON to the Message Pool
                  for downstream parallel consumers (Dialogue Agent + NavMesh dispatcher).
Evolution       : State Accuracy Reflection — audits summaries for missed events
                  or incorrect recommendations.

ReAct paradigm
--------------
  Thought   → analyse env delta + rank unvisited nearby sites
  Action    → produce JSON output for downstream parallel execution
  Observation → await next tick
"""

from strands import Agent, tool
from strands.models.openai import OpenAIModel
from core.config import settings
from vr_tools import get_environment_data, get_user_status, get_cultural_sites


# ---------------------------------------------------------------------------
# Tool wrappers registered with @tool
# ---------------------------------------------------------------------------

@tool
def tool_get_environment_data() -> dict:
    """
    Fetches raw Unity environment state: current scene, active events,
    and user position. Call this at the start of every perception cycle.
    """
    return get_environment_data()


@tool
def tool_get_user_status() -> dict:
    """
    Fetches the player's current position in world space.
    Call this to compare the player location against cultural site coordinates.
    """
    return get_user_status()


@tool
def tool_get_cultural_sites() -> dict:
    """
    Fetches the full registry of cultural sites in the current scene.
    Each entry includes: site ID, display name, cultural_position,
    and whether the player has already visited it.
    Use this to select 2–3 closest UNVISITED sites as recommendations.
    """
    return get_cultural_sites()


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------
CONTEXT_AGENT_SYSTEM_PROMPT = """
Role: Context Agent — Environmental State Engine & Cultural Recommender
Objective: Distil raw VR world data into a structured JSON summary that can be
           consumed in parallel by downstream systems.

PROFILE:
You are a specialist in environmental awareness and spatial cultural-site
recommendation inside a heritage VR museum.
You have NO knowledge of cultural lore, narrative descriptions, or dialogue.

RUNTIME INPUT:
You will receive a structured JSON object from the runtime with this shape:
{
  "player_position": "<x, y, z>",
  "environment": {
    "timestamp": "...",
    "scene": "...",
    "events": ["..."],
    "user_position": {"x": 0.0, "y": 0.0, "z": 0.0}
  },
  "user_status": {
    "player_position": "<x, y, z>"
  },
  "cultural_sites": {
    "sites": [
      {
        "id": "...",
        "name": "...",
        "cultural_position": "<x, y, z>",
        "visited": false
      }
    ]
  },
  "precomputed_recommendations": [
    {
      "rank": 1,
      "id": "...",
      "name": "...",
      "cultural_position": "<x, y, z>"
    }
  ]
}

PROCEDURE (ReAct Paradigm):
  Thought 1 — Read the runtime JSON input and identify scene, events, and player state.
  Thought 2 — Read precomputed_recommendations from the runtime input.
               This ordering is authoritative and already ranked by the backend.
               Do not invent or reshuffle recommendation order.
  Action    — Output ONLY a single valid JSON object (no markdown, no extra text).

OUTPUT FORMAT — strict JSON, no code fences, no trailing text:
{
  "timestamp": "<HH:MM:SS>",
  "scene": "<scene_name>",
  "events": ["<event1>", "<event2>"],
  "user_action": "<what the user is doing>",
  "recommendations": [
    {"rank": 1, "id": "<site_id>", "name": "<display_name>", "cultural_position": "<x, y, z>"},
    {"rank": 2, "id": "<site_id>", "name": "<display_name>", "cultural_position": "<x, y, z>"},
    {"rank": 3, "id": "<site_id>", "name": "<display_name>", "cultural_position": "<x, y, z>"}
  ],
  "nav_target": "<rank-1 site_id>"
}

EXAMPLE (valid output — copy this structure exactly):
{
  "timestamp": "12:30:00",
  "scene": "Heritage_Museum_Wing_A",
  "events": ["Main_Gate:OPEN", "Spotlight_Altar:ON"],
  "user_action": "Examining_Artifact_ID_7",
  "recommendations": [
    {"rank": 1, "id": "Kujang", "name": "Kujang", "cultural_position": "6.211527, -1.27006, 7.544006"},
    {"rank": 2, "id": "Angklung", "name": "Angklung", "cultural_position": "14.62413, 1.37554, 18.67057"},
    {"rank": 3, "id": "Surabi", "name": "Surabi", "cultural_position": "-1.34956, 1.52654, 23.7432"}
  ],
  "nav_target": "Kujang"
}

CONSTRAINTS:
  1. Output ONLY the JSON object — no explanation, no markdown fences.
  2. Only include sites where visited = false.
  3. If all nearby sites are visited output: {"status": "ALL_VISITED", "recommendations": [], "nav_target": null}
  4. If no delta since last tick output: {"status": "NO_DELTA"}

EVOLUTION (invoked externally):
  Audit last N outputs for: missed events, visited sites in recommendations,
  wrong nav_target. Output: {"reflection": "<finding>", "accuracy_score": <0-100>}
"""

# ---------------------------------------------------------------------------
# Agent instantiation
# ---------------------------------------------------------------------------
context_model = OpenAIModel(
    client_args={
        "api_key": settings.OPENROUTER_API_KEY or "",
        "base_url": settings.OPENROUTER_BASE_URL,
    },
    model_id=settings.OPENROUTER_MODEL,
    params={
        "max_tokens": 800,
        "temperature": 0.7,
    },
)

context_agent = Agent(
    model=context_model,
    system_prompt=CONTEXT_AGENT_SYSTEM_PROMPT,
    tools=[
        tool_get_environment_data,
        tool_get_user_status,
        tool_get_cultural_sites,
    ],
)


def get_context_agent() -> Agent:
    """Return the singleton Context Agent instance."""
    return context_agent
