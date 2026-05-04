"""
Context Agent — Environmental State & Cultural Site Recommendation Engine
=========================================================================
Module  : Profile → Perception → Self-Action → Mutual Interaction → Evolution
Role    : Environmental State Engine & Cultural Recommender
Layer   : Child Node (Publisher)

Five-module mapping
-------------------
Profile         : Specialist in objective environmental awareness, scene-state
                  tracking, and cultural site recommendation by proximity/visit status.
Perception      : Consumes raw VR sensor data via three tool calls:
                    • tool_get_environment_data  — scene + event deltas
                    • tool_get_user_status       — player proximity & action state
                    • tool_get_cultural_sites    — full site registry with visited flags
Self-Action     : (a) Distils raw signals into a structured JSON state summary.
                  (b) Selects 2–3 nearby UNVISITED sites as ranked recommendations.
                  (c) Calls tool_set_nav_target with the rank-1 (closest) site ID.
Mutual Interaction: Publisher — writes a ContextOutput JSON to the Message Pool
                  for the Dialogue Agent to consume.
Evolution       : State Accuracy Reflection — audits summaries for missed events
                  or incorrect recommendations.

ReAct paradigm
--------------
  Thought   → analyse env delta + rank unvisited nearby sites
  Action    → produce JSON output + call set_nav_target
  Observation → confirm NavMesh acknowledged; await next tick
"""

from strands import Agent, tool
from strands.models.openai import OpenAIModel
from core.config import settings
from vr_tools import get_environment_data, get_user_status, get_cultural_sites, set_nav_target


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
    Fetches the player's current proximity, gaze target, and interaction state.
    Call this to understand what the user is currently doing or looking at.
    """
    return get_user_status()


@tool
def tool_get_cultural_sites() -> dict:
    """
    Fetches the full registry of cultural sites in the current scene.
    Each entry includes: site ID, display name, distance from player (metres),
    and whether the player has already visited it.
    Use this to select 2–3 closest UNVISITED sites as recommendations.
    """
    return get_cultural_sites()


@tool
def tool_set_nav_target(target_id: str) -> bool:
    """
    Sends the chosen primary destination to Unity's NavMesh.
    The NPC will begin pathfinding autonomously to this site.

    Args:
        target_id: The Unity GameObject ID of the rank-1 destination site.
    """
    return set_nav_target(target_id)


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------
CONTEXT_AGENT_SYSTEM_PROMPT = """
Role: Context Agent — Environmental State Engine & Cultural Recommender
Objective: Distil raw VR world data into a structured JSON summary and signal
           the primary destination to Unity NavMesh.

PROFILE:
You are a specialist in environmental awareness and spatial cultural-site
recommendation inside a heritage VR museum.
You have NO knowledge of cultural lore, narrative descriptions, or dialogue.

TOOLS (call in this order every cycle):
  1. tool_get_environment_data  — scene + event deltas
  2. tool_get_user_status       — player proximity & current action
  3. tool_get_cultural_sites    — site registry with visited flags
  4. tool_set_nav_target        — send primary site ID to Unity NavMesh

  {
   "event": "",
   "scenes": "",
   "playerProximity": "",
   "playerAction": "",
   "culturalSites": [
    {
     "id": "",
     "name": "",
     "stage": "",
     "visited": false
    }
   ],
   "navTarget": ""
  }





PROCEDURE (ReAct Paradigm):
  Thought 1 — Call tools 1 and 2. Identify SCENE, EVENTS[], USER_ACTION.
  Thought 2 — Call tool 3. Filter to visited=false only.
               Sort by distance_m ascending.
               Select the 2 or 3 closest as RECOMMENDATIONS (rank 1 = primary).
  Action 1  — Call tool_set_nav_target with the rank-1 site's ID.
  Action 2  — Output ONLY a single valid JSON object (no markdown, no extra text).

OUTPUT FORMAT — strict JSON, no code fences, no trailing text:
{
  "timestamp": "<HH:MM:SS>",
  "scene": "<scene_name>",
  "events": ["<event1>", "<event2>"],
  "user_action": "<what the user is doing>",
  "recommendations": [
    {"rank": 1, "id": "<site_id>", "name": "<display_name>", "distance_m": <float>},
    {"rank": 2, "id": "<site_id>", "name": "<display_name>", "distance_m": <float>},
    {"rank": 3, "id": "<site_id>", "name": "<display_name>", "distance_m": <float>}
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
    {"rank": 1, "id": "Cultural_Site_Altar", "name": "Sacred Altar of Prambanan", "distance_m": 18.5},
    {"rank": 2, "id": "Cultural_Site_Library", "name": "Ancient Manuscript Library", "distance_m": 34.0},
    {"rank": 3, "id": "Cultural_Site_Pavilion", "name": "Royal Ceremonial Pavilion", "distance_m": 52.0}
  ],
  "nav_target": "Cultural_Site_Altar"
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
        "max_tokens": 200,
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
        tool_set_nav_target,
    ],
)


def get_context_agent() -> Agent:
    """Return the singleton Context Agent instance."""
    return context_agent
