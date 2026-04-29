"""
src/agents/__init__.py
======================
Public exports for the Multi-Agent Unified Framework.

Hierarchy:
  Dialogue Agent (Parent Node)
    ├── Context Agent  (Child Node)
    └── Guidance Agent (Child Node)
"""

from .context_agent  import context_agent,  get_context_agent
from .guidance_agent import guidance_agent, get_guidance_agent
from .dialogue_agent import dialogue_agent, get_dialogue_agent

__all__ = [
    # Singleton instances
    "context_agent",
    "guidance_agent",
    "dialogue_agent",
    # Factory accessors
    "get_context_agent",
    "get_guidance_agent",
    "get_dialogue_agent",
]
