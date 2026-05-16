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
Perception      : Consumes one structured runtime payload from the backend.
                  The backend has already collected environment state, player position,
                  and live cultural site data from Unity.
Self-Action     : (a) Distils raw signals into a structured JSON state summary.
                  (b) Preserves the backend-ranked UNVISITED recommendations.
Mutual Interaction: Publisher — writes a ContextOutput JSON to the Message Pool
                  for downstream parallel consumers (Dialogue Agent + NavMesh dispatcher).
Evolution       : State Accuracy Reflection — audits summaries for missed events
                  or incorrect recommendations.

ReAct paradigm
--------------
  Reasoning   → inspect runtime perception, visited flags, and backend-ranked recommendations
  Action      → produce one complete JSON context object for downstream execution
  Observation → downstream systems use the JSON for NavMesh and Dialogue Agent
"""

from copy import deepcopy

from strands import Agent, tool
from strands.models.openai import OpenAIModel
from core.config import settings


# ---------------------------------------------------------------------------
# Runtime snapshot shared by bounded tools
# ---------------------------------------------------------------------------
_RUNTIME_SNAPSHOT: dict = {}


def set_context_runtime_snapshot(payload: dict) -> None:
    """
    Store the current request snapshot for bounded Context Agent tool access.
    Tools may only read from this in-memory payload and must not access any
    external source of truth.
    """
    global _RUNTIME_SNAPSHOT
    _RUNTIME_SNAPSHOT = deepcopy(payload)


@tool
def tool_get_runtime_user_status() -> dict:
    """Read only the current request's user_status snapshot."""
    return deepcopy(_RUNTIME_SNAPSHOT.get("user_status", {}))


@tool
def tool_get_runtime_cultural_sites() -> dict:
    """Read only the current request's cultural site payload."""
    return deepcopy(_RUNTIME_SNAPSHOT.get("cultural_sites", {}))


@tool
def tool_get_runtime_recommendations() -> dict:
    """Read only the backend-ranked recommendations for the current request."""
    return {
        "precomputed_recommendations": deepcopy(
            _RUNTIME_SNAPSHOT.get("precomputed_recommendations", [])
        )
    }


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------
CONTEXT_AGENT_SYSTEM_PROMPT = """
Role: Context Agent — Environmental State Engine
Objective: Distil the runtime payload from the backend into one structured JSON
           context object for downstream systems.

PROFILE:
You are a specialist in environmental awareness and spatial cultural-site
recommendation inside a heritage VR museum.
You have NO knowledge of cultural lore, narrative descriptions, or dialogue.
You must not invent, fetch, or assume any data outside the bounded runtime snapshot.

BOUNDED TOOLS:
You may use only these internal tools, and each tool reads the same request snapshot
already prepared by the backend:
  • tool_get_runtime_user_status
  • tool_get_runtime_cultural_sites
  • tool_get_runtime_recommendations
These tools do NOT access external systems, files, or alternative sources of truth.

RUNTIME INPUT:
You will receive a short runtime instruction from the backend for the current request.
Use the bounded tools above to inspect the request snapshot before producing output.

PROCEDURE (ReAct Paradigm):
  Reasoning 1 — Understand that all valid information comes from the bounded tools.
  Action 1    — Call tool_get_runtime_user_status.
  Observation 1 — Read player position from the current request snapshot.
  Reasoning 2 — You may inspect supporting state, but you must not create a new ranking.
  Action 2    — Call tool_get_runtime_cultural_sites and tool_get_runtime_recommendations.
  Observation 2 — Read visited flags and treat precomputed_recommendations as the only authoritative
                  recommendation order prepared by the backend.
  Reasoning 3 — Preserve recommendation order exactly and infer a concise user_action
                that matches the runtime request context without inventing hidden facts.
  Action      — Output ONLY one complete valid JSON object in the schema below.
  Observation — Downstream systems will use your JSON for NavMesh dispatch
                and Dialogue Agent synthesis.

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
  2. Use only the bounded runtime tools and the runtime instruction.
     Never reference hidden state and never assume data outside the snapshot.
  3. Only include sites where visited = false.
  4. Always output the full schema with timestamp, scene, events, user_action,
     recommendations, and nav_target.
  5. If all sites are visited, output the full schema with recommendations: [] and nav_target: "".
  6. Do not output status-only objects such as {"status": "NO_DELTA"}.
  7. Preserve recommendation order from precomputed_recommendations exactly.
  8. nav_target must equal the id of the rank-1 recommendation, or "" if no recommendation exists.

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
        tool_get_runtime_user_status,
        tool_get_runtime_cultural_sites,
        tool_get_runtime_recommendations,
    ],
)


def get_context_agent() -> Agent:
    """Return the singleton Context Agent instance."""
    return context_agent
