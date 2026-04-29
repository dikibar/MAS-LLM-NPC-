from enum import Enum
from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field
from datetime import datetime


class AgentRole(str, Enum):
    CONTEXT = "context_agent"
    GUIDANCE = "guidance_agent"
    DIALOGUE = "dialogue_agent"


class AgentMessage(BaseModel):
    """Represents a message in the system."""
    role: str
    content: str
    timestamp: datetime = Field(default_factory=datetime.now)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AgentTask(BaseModel):
    """Represents a task assigned to an agent."""
    task_id: str
    description: str
    assigned_to: Optional[AgentRole] = None
    status: str = "pending"
    result: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None


class VRWorldState(BaseModel):
    """Structured representation of the VR world at a point in time."""
    timestamp: str
    scene: str
    events: List[str]
    user_position: Dict[str, float]
    user_proximity: Optional[str] = None


class NavigationAction(BaseModel):
    """Represents a planned action from the Guidance Agent."""
    action_type: str  # MOVE_TO, INTERACT, PICK_UP, BLOCKED
    payload: Any
    timestamp: datetime = Field(default_factory=datetime.now)


class MessagePoolState(BaseModel):
    """The in-memory state shared across the hierarchy."""
    latest_context: Optional[str] = None  # The textual summary from ContextAgent
    latest_plan: Optional[str] = None     # The plan from GuidanceAgent
    latest_dialogue: Optional[Dict[str, str]] = None # The output from DialogueAgent
    history: List[AgentMessage] = []
