"""Lightweight in-process scheduler for skills and recurring jobs.

Persistence is handled by the caller (e.g. SkillsManager): this module only
keeps the runtime registry. Jobs are simple: ``every_seconds`` (recurring) or
``at_iso`` (one-shot at an ISO timestamp), running ``callback(name)`` on a
daemon thread loop.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class ScheduledJob:
    name: str
    callback: Callable[..., Any]
    args: Tuple[Any, ...] = field(default_factory=tuple)
    kwargs: Dict[str, Any] = field(default_factory=dict)
    every_seconds: Optional[int] = None
    at_ts: Optional[float] = None
    next_run: float = 0.0
    last_run: float = 0.0
    runs: int = 0
    enabled: bool = True
    metadata: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, object]:
        return {
            "name": self.name,
            "every_seconds": self.every_seconds,
            "at_ts": self.at_ts,
            "next_run": self.next_run,
            "last_run": self.last_run,
            "runs": self.runs,
            "enabled": self.enabled,
            "metadata": dict(self.metadata),
        }


class Scheduler:
    """Tiny scheduler — single tick thread, ~1Hz resolution."""

    def __init__(self) -> None:
        self._jobs: Dict[str, ScheduledJob] = {}
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="jarvis-scheduler")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def schedule(
        self,
        name: str,
        callback: Callable[..., Any],
        args: Optional[Tuple[Any, ...]] = None,
        kwargs: Optional[Dict[str, Any]] = None,
        every_seconds: Optional[int] = None,
        at_iso: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None,
    ) -> ScheduledJob:
        if not name:
            raise ValueError("scheduler: nome vuoto")
        if not every_seconds and not at_iso:
            raise ValueError("scheduler: indicare every_seconds o at_iso")
        now = time.time()
        at_ts: Optional[float] = None
        if at_iso:
            try:
                at_ts = datetime.fromisoformat(at_iso).timestamp()
            except ValueError as e:
                raise ValueError(f"scheduler: at_iso non valido ({e})") from e
        job = ScheduledJob(
            name=name,
            callback=callback,
            args=tuple(args or ()),
            kwargs=dict(kwargs or {}),
            every_seconds=int(every_seconds) if every_seconds else None,
            at_ts=at_ts,
            next_run=at_ts if at_ts else now + (int(every_seconds) if every_seconds else 0),
            metadata=dict(metadata or {}),
        )
        with self._lock:
            self._jobs[name] = job
        self.start()
        return job

    def cancel(self, name: str) -> bool:
        with self._lock:
            return self._jobs.pop(name, None) is not None

    def list_jobs(self) -> List[Dict[str, object]]:
        with self._lock:
            return [j.to_dict() for j in self._jobs.values()]

    def get(self, name: str) -> Optional[ScheduledJob]:
        with self._lock:
            return self._jobs.get(name)

    def _loop(self) -> None:
        while not self._stop.is_set():
            now = time.time()
            due: List[ScheduledJob] = []
            with self._lock:
                for job in list(self._jobs.values()):
                    if job.enabled and now >= job.next_run:
                        due.append(job)
            for job in due:
                try:
                    job.callback(*job.args, **job.kwargs)
                except Exception:
                    logger.debug("scheduler callback error", exc_info=True)
                with self._lock:
                    j = self._jobs.get(job.name)
                    if not j:
                        continue
                    j.last_run = now
                    j.runs += 1
                    if j.every_seconds:
                        j.next_run = now + j.every_seconds
                    else:
                        # one-shot: remove after run
                        self._jobs.pop(job.name, None)
            time.sleep(1.0)


_scheduler: Optional[Scheduler] = None
_lock = threading.Lock()


def get_scheduler() -> Scheduler:
    """Singleton accessor."""
    global _scheduler
    with _lock:
        if _scheduler is None:
            _scheduler = Scheduler()
        return _scheduler
