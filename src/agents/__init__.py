"""
src/agents/__init__.py
======================
Public exports for the 2-Agent Multi-Agent NPC System.

Hierarchy:
  Dialogue Agent (Parent Node / Synthesiser)
    └── Context Agent (Child Node — Publisher of state + recommendations)

The Guidance Agent has been retired in favour of Unity NavMesh pathfinding.
"""

from .context_agent  import context_agent,  get_context_agent, set_context_runtime_snapshot
from .dialogue_agent import dialogue_agent, get_dialogue_agent

__all__ = [
    # Singleton instances
    "context_agent",
    "dialogue_agent",
    # Factory accessors
    "get_context_agent",
    "get_dialogue_agent",
    "set_context_runtime_snapshot",
]
