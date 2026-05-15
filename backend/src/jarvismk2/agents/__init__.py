"""Agent layer.

Three styles, all share :class:`AgentResponse`:

* :class:`SimpleAgent` — single LLM call with persona + brain context.
* :class:`Orchestrator` — picks the right path (skill / agent / engine) per
  user request.  This is the main entry point used by the CLI/server.
* :class:`Swarm` — CrewAI-based Architect → Developer → Reviewer pipeline
  (loaded lazily; CrewAI is an optional dep).
"""

from jarvismk2.agents.orchestrator import Orchestrator, get_orchestrator
from jarvismk2.agents.simple import SimpleAgent
from jarvismk2.agents.swarm import Swarm

__all__ = ["Orchestrator", "SimpleAgent", "Swarm", "get_orchestrator"]
