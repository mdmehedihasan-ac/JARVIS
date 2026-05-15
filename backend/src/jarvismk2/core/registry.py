"""Generic plugin registry used by engines, agents, channels, connectors.

Inspired by OpenJarvis's ``Registry`` pattern but trimmed down.  Each subsystem
gets its own :class:`Registry` instance so namespaces don't collide.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Generic, Iterator, List, TypeVar

T = TypeVar("T")


class Registry(Generic[T]):
    """Minimal name-based registry.

    Usage::

        AgentRegistry: Registry[type] = Registry("agents")

        @AgentRegistry.register("simple")
        class SimpleAgent: ...

        cls = AgentRegistry.get("simple")
    """

    def __init__(self, kind: str) -> None:
        self.kind = kind
        self._items: Dict[str, T] = {}

    def register(self, name: str) -> Callable[[T], T]:
        def decorator(obj: T) -> T:
            if name in self._items:
                raise ValueError(f"{self.kind}: '{name}' already registered")
            self._items[name] = obj
            return obj

        return decorator

    def register_obj(self, name: str, obj: T) -> None:
        """Imperative registration (when not using the decorator)."""
        self._items[name] = obj

    def get(self, name: str) -> T:
        if name not in self._items:
            raise KeyError(
                f"{self.kind}: '{name}' not found. Available: {list(self._items)}"
            )
        return self._items[name]

    def get_or_none(self, name: str) -> Any:
        return self._items.get(name)

    def names(self) -> List[str]:
        return list(self._items.keys())

    def __iter__(self) -> Iterator[str]:
        return iter(self._items)

    def __contains__(self, name: str) -> bool:
        return name in self._items

    def __len__(self) -> int:
        return len(self._items)
