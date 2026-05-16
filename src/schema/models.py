from enum import Enum
from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field, field_validator, model_validator
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
    culturalSites: List["CulturalSite"]

    @model_validator(mode="before")
    @classmethod
    def normalize_cultural_sites_input(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        if "culturalSites" in data and isinstance(data["culturalSites"], list):
            return data

        if "cultural_sites" in data and isinstance(data["cultural_sites"], list):
            data["culturalSites"] = data["cultural_sites"]
            return data

        if "culturalObject" in data and isinstance(data["culturalObject"], list):
            data["culturalSites"] = [
                {
                    "id": item.get("id") or item.get("name", ""),
                    "name": item.get("name", ""),
                    "cultural_position": item.get("cultural_position") or item.get("coordinate", ""),
                    "visited": item.get("visited", item.get("isObjectVisited", False)),
                }
                for item in data["culturalObject"]
            ]
            return data

        if "culturalObjects" in data and isinstance(data["culturalObjects"], list):
            data["culturalSites"] = [
                {
                    "id": item.get("id") or item.get("name", ""),
                    "name": item.get("name", ""),
                    "cultural_position": item.get("cultural_position") or item.get("coordinate", ""),
                    "visited": item.get("visited", item.get("isObjectVisited", False)),
                }
                for item in data["culturalObjects"]
            ]
            return data

        return data

    @field_validator("playerPosition")
    @classmethod
    def validate_player_position(cls, value: str) -> str:
        parts = [part.strip() for part in value.split(",")]
        if len(parts) != 3:
            raise ValueError("playerPosition must use the format 'x, y, z'.")

        try:
            [float(part) for part in parts]
        except ValueError as exc:
            raise ValueError("playerPosition must contain numeric x, y, z values.") from exc

        return ", ".join(parts)


class RecommendationSelectionRequest(BaseModel):
    """Request body for selecting one recommendation option."""
    simulationId: str
    selectedOption: str  # Selected cultural object name from recommendation_options

    @field_validator("simulationId", "selectedOption")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Field must not be empty.")
        return cleaned


class DialogueCycleRequest(BaseModel):
    """Request body for running the Dialogue Agent from a saved simulation session."""
    simulationId: str

    @field_validator("simulationId")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Field must not be empty.")
        return cleaned


# ---------------------------------------------------------------------------
# Cultural site data models
# ---------------------------------------------------------------------------
class CulturalSite(BaseModel):
    """Canonical cultural-site structure stored in the JSON registry."""
    id: str
    name: str
    cultural_position: str
    visited: bool = False

    @field_validator("id", "name", "cultural_position")
    @classmethod
    def validate_non_empty_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Field must not be empty.")
        return cleaned

    @field_validator("cultural_position")
    @classmethod
    def validate_coordinate_format(cls, value: str) -> str:
        parts = [part.strip() for part in value.split(",")]
        if len(parts) != 3:
            raise ValueError("cultural_position must use the format 'x, y, z'.")

        try:
            [float(part) for part in parts]
        except ValueError as exc:
            raise ValueError("cultural_position must contain numeric x, y, z values.") from exc

        return ", ".join(parts)


class CulturalSitesPayload(BaseModel):
    """Top-level JSON payload for the cultural site registry."""
    sites: List[CulturalSite]


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


class EnvironmentSnapshot(BaseModel):
    """Structured environment state returned by the Unity environment endpoint."""
    timestamp: str
    scene: str
    user_position: Dict[str, float]


class UserStatusSnapshot(BaseModel):
    """Structured user status returned by the Unity user endpoint."""
    player_position: str


class ContextAgentInput(BaseModel):
    """
    Structured runtime payload passed to the Context Agent.
    Separates raw system perception from precomputed recommendation candidates.
    """
    player_position: str
    environment: EnvironmentSnapshot
    user_status: UserStatusSnapshot
    cultural_sites: CulturalSitesPayload
    precomputed_recommendations: List[SiteRecommendation]


class ContextOutput(BaseModel):
    """
    Validated JSON output from the Context Agent.
    Stored in MessagePoolState.latest_context_json and passed directly
    to the Dialogue Agent and Unity NavMesh.
    """
    timestamp: str
    scene: str
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


class SimulationCycleResponse(BaseModel):
    """Structured result returned after one simulation cycle finishes."""
    simulation_id: str
    context: ContextOutput
    navmesh_ack: bool
    dialogue: DialogueOutput


class ContextCycleResponse(BaseModel):
    """Structured result returned after the Context Agent finishes."""
    simulation_id: str
    context: ContextOutput
    navmesh_ack: bool


class DialogueCycleResponse(BaseModel):
    """Structured result returned after the Dialogue Agent finishes."""
    simulation_id: str
    dialogue: DialogueOutput


class SimulationSessionState(BaseModel):
    """Per-simulation in-memory state used for validating follow-up actions."""
    simulation_id: str
    player_position: str
    cultural_sites: CulturalSitesPayload
    context: ContextOutput
    dialogue: Optional[DialogueOutput] = None


# ---------------------------------------------------------------------------
# Message Pool state (shared blackboard)
# ---------------------------------------------------------------------------
class MessagePoolState(BaseModel):
    """In-memory state shared across the agent hierarchy."""
    latest_context:  Optional[ContextOutput]  = None  # validated Context Agent output
    latest_dialogue: Optional[DialogueOutput] = None  # validated Dialogue Agent output
    history: List[AgentMessage] = []
