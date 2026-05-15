"""Skills — named sequences of tool calls with auto-match.

A *skill* is a tiny imperative program: a list of ``{tool, args}`` dicts that
can be executed in order.  Skills can be:

* hand-crafted (the four defaults: ``routine_mattutina``, ``pausa_pranzo``,
  ``fine_lavoro``, ``modalita_focus``);
* matched against user input via :meth:`SkillsManager.match`.
"""

from jarvismk2.skills.manager import SkillsManager, get_skills_manager

__all__ = ["SkillsManager", "get_skills_manager"]
