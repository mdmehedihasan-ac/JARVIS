"""Brain subsystem.

Two complementary memory systems live here:

* :class:`Cervello` — the **cognitive** brain.  Six functional lobes containing
  named *neurons* (small declarative knowledge fragments) with Hebbian
  reinforcement, time decay, and an Obsidian sync hook.  Lends itself to a
  force-directed graph in the UI.
* :class:`EpisodicMemory` — the **episodic** brain.  Append-only log of every
  user/assistant interaction, optionally vectorized for semantic retrieval.

The :class:`LearningOrchestrator` is the *meta-brain*: it observes outcomes
and updates routing weights, prompt stats, behavioural patterns, and acquires
new skills when an action fails.
"""

from jarvismk2.brain.cervello import Cervello, Lobo, Neurone, get_cervello
from jarvismk2.brain.episodic import EpisodicMemory, get_episodic
from jarvismk2.brain.learning import LearningMemory, LearningOrchestrator

__all__ = [
    "Cervello",
    "EpisodicMemory",
    "LearningMemory",
    "LearningOrchestrator",
    "Lobo",
    "Neurone",
    "get_cervello",
    "get_episodic",
]
