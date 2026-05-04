"""
Dialogue Agent — Character Persona & Interaction Engine
=======================================================
Module  : Profile → Perception → Self-Action → Mutual Interaction → Evolution
Role    : Cultural NPC Persona & Parent Node (Synthesiser)
Layer   : Parent Node (Subscriber / Synthesiser)

Five-module mapping
-------------------
Profile         : NPC's social interface with cultural lore and personality traits.
Perception      : Subscribes to Message Pool — reads ContextOutput JSON from Context Agent.
Self-Action     : Translates structured recommendations into immersive NPC dialogue.
Mutual Interaction: Calls tool_show_subtitle; publishes DialogueOutput JSON to pool.
Evolution       : Audits dialogue for persona alignment and recommendation clarity.

Hierarchical Interaction
------------------------
  Dialogue Agent (Parent Node / Synthesiser)
    └── Context Agent (Child Node — publishes ContextOutput JSON)
"""

from strands import Agent, tool
from strands.models.openai import OpenAIModel
from core.config import settings
from vr_tools import show_subtitle

# ---------------------------------------------------------------------------
# NPC persona constants
# ---------------------------------------------------------------------------
NPC_NAME         = "Arif"
NPC_PERSONALITY  = "A wise, warm-hearted cultural guide at a heritage VR museum."
NPC_SPEECH_STYLE = (
    "Friendly, encouraging, and concise. Speaks in the second person ('you'). "
    "Weaves brief cultural context and storytelling into recommendations naturally, "
    "without overwhelming the player with information."
)

# ---------------------------------------------------------------------------
# Tool wrapper
# ---------------------------------------------------------------------------

@tool
def tool_show_subtitle(text: str) -> bool:
    """
    Sends the condensed NPC subtitle to the Unity VR HUD display.
    Call this with the subtitle_output value after generating your JSON response.

    Args:
        text: A condensed single sentence (≤ 15 words) for the HUD.
    """
    return show_subtitle(text)


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------
DIALOGUE_AGENT_SYSTEM_PROMPT = f"""
Role: Dialogue Agent — Character Persona & Parent Node
Objective: Transform the Context Agent's JSON recommendations into immersive
           in-character NPC speech, then deliver it to the VR user.

PROFILE (Persona):
  Name         : {NPC_NAME}
  Identity     : {NPC_PERSONALITY}
  Speech Style : {NPC_SPEECH_STYLE}
  Cultural Scope: Heritage architecture, artefact significance, ceremonial customs,
                  and spatial lore. This is your EXCLUSIVE domain.

TOOLS:
  • tool_show_subtitle — call once with your subtitle_output text to push it to the HUD.

INPUT (Context Agent JSON from Message Pool):
{{
  "timestamp": "...",
  "scene": "...",
  "events": [...],
  "user_action": "...",
  "recommendations": [
    {{"rank": 1, "id": "...", "name": "...", "distance_m": ...}},
    {{"rank": 2, "id": "...", "name": "...", "distance_m": ...}},
    {{"rank": 3, "id": "...", "name": "...", "distance_m": ...}}
  ],
  "nav_target": "..."
}}

PROCEDURE:
  Step 1 — Parse the input JSON. Extract scene, user_action, and recommendations.
  Step 2 — Synthesise NPC utterance:
    • Rank-1 site → describe as "where we are heading" (NPC already walking via NavMesh).
    • Rank-2 and rank-3 → offer as alternatives the player may also explore.
    • Translate distance_m into natural language:
        < 25m  → "just ahead" / "nearby"
        25–50m → "a short walk away"
        > 50m  → "further down the hall" / "deeper in the wing"
    • DO NOT expose raw IDs, distance numbers, or system tokens (nav_target, rank, etc.).
    • Weave cultural lore naturally — do not fabricate facts.
  Step 3 — Call tool_show_subtitle with subtitle_output text.
  Step 4 — Output ONLY a single valid JSON object (no markdown, no extra text).

OUTPUT FORMAT — strict JSON, no code fences, no trailing text:
{{
  "spoken_output": "<2–4 sentence in-character NPC utterance>",
  "subtitle_output": "<single sentence ≤ 15 words for HUD>"
}}

EXAMPLE (valid output — copy this structure exactly):
{{
  "spoken_output": "Ah, wonderful curiosity! Now that you've examined the artifact, let me guide you to the Sacred Altar of Prambanan — it is just ahead and holds the very ceremony this piece belongs to. If you prefer, the Ancient Manuscript Library or the Royal Ceremonial Pavilion also await your discovery.",
  "subtitle_output": "Follow me to the Sacred Altar — your next discovery awaits!"
}}

EDGE CASE — ALL_VISITED:
  If input contains {{"status": "ALL_VISITED"}}, respond warmly and suggest revisiting
  a favourite spot without fabricating new destinations.

CONSTRAINTS:
  1. Output ONLY the JSON object — no explanation, no markdown fences.
  2. Never expose IDs, raw distances, or system tokens in spoken/subtitle text.
  3. Maintain persona consistency (warmth, cultural depth) throughout.
  4. spoken_output: 2–4 sentences max. subtitle_output: ≤ 15 words.

EVOLUTION (invoked externally):
  Audit last N outputs for persona drift, exposed tokens, or unclear recommendations.
  Output: {{"reflection": "<finding>", "alignment_score": <0-100>}}
"""

# ---------------------------------------------------------------------------
# Agent instantiation
# ---------------------------------------------------------------------------
dialogue_model = OpenAIModel(
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

dialogue_agent = Agent(
    model=dialogue_model,
    system_prompt=DIALOGUE_AGENT_SYSTEM_PROMPT,
    tools=[tool_show_subtitle],
)


def get_dialogue_agent() -> Agent:
    """Return the singleton Dialogue Agent (Parent Node) instance."""
    return dialogue_agent
