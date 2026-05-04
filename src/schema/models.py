from enum import Enum
from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field
from datetime import datetime


# ---------------------------------------------------------------------------
# Agent roles (2-agent system)
# ---------------------------------------------------------------------------
class AgentRole(str, Enum):
    CONTEXT  = "context_agent"
    DIALOGUE = "dialogue_agent"


# ---------------------------------------------------------------------------
# API Request body models (POST /run-simulation)
# ---------------------------------------------------------------------------
class SimulationRequest(BaseModel):
    """Request body for POST /run-simulation."""
    playerPosition: str  # Player world-space position e.g. "12.0, 0.0, 35.0"


class RecommendationSelectionRequest(BaseModel):
    """Request body for selecting one recommendation option."""
    selectedOption: str  # Selected cultural object name from recommendation_options


# ---------------------------------------------------------------------------
# Message Pool internals
# ---------------------------------------------------------------------------
class AgentMessage(BaseModel):
    """A single timestamped entry in the Message Pool history."""
    role: str
    content: str
    timestamp: datetime = Field(default_factory=datetime.now)
    metadata: Dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Context Agent — structured JSON output schema
# ---------------------------------------------------------------------------
class SiteRecommendation(BaseModel):
    """One cultural site recommendation produced by the Context Agent."""
    rank: int                   # 1 = primary (NavMesh target), 2, 3 = alternatives
    id: str                     # Unity GameObject ID  e.g. "Cultural_Site_Altar"
    name: str                   # Human-readable display name
    cultural_position: str      # World-space coordinate string e.g. "14.62413, 1.37554, 18.67057"


class ContextOutput(BaseModel):
    """
    Validated JSON output from the Context Agent.
    Stored in MessagePoolState.latest_context_json and passed directly
    to the Dialogue Agent and Unity NavMesh.
    """
    timestamp: str
    scene: str
    events: List[str]
    user_action: str
    recommendations: List[SiteRecommendation]  # ordered by rank ascending
    nav_target: str                            # ID of rank-1 site


# ---------------------------------------------------------------------------
# Dialogue Agent — structured JSON output schema
# ---------------------------------------------------------------------------
class DialogueOutput(BaseModel):
    """
    Validated JSON output from the Dialogue Agent.
    spoken_output     → sent to TTS / avatar lip-sync
    subtitle_output   → sent to Unity HUD via show_subtitle tool
    recommendation_dialogue → short descriptive recommendation for the UI
    recommendation_options  → 2-3 cultural-object buttons for player selection
    """
    spoken_output: str              # 2–4 sentences, in-character NPC speech
    subtitle_output: str            # ≤ 15 words, condensed for HUD display
    recommendation_dialogue: str    # Short UI-ready recommendation summary
    recommendation_options: List[str]  # 2-3 selectable cultural object names


class RecommendationSelectionResponse(BaseModel):
    """Response after the player selects a recommendation option."""
    selected_option: str
    selected_site_id: str
    navmesh_ack: bool
    spoken_output: str
    subtitle_output: str


# ---------------------------------------------------------------------------
# Message Pool state (shared blackboard)
# ---------------------------------------------------------------------------
class MessagePoolState(BaseModel):
    """In-memory state shared across the agent hierarchy."""
    latest_context:  Optional[ContextOutput]  = None  # validated Context Agent output
    latest_dialogue: Optional[DialogueOutput] = None  # validated Dialogue Agent output
    history: List[AgentMessage] = []
