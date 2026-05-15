from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from typing import Any, Dict, List, Optional

import httpx

_ALLOWED_ACTIONS = {
    "navigate",
    "find_tab",
    "snapshot",
    "click",
    "fill",
    "evaluate",
    "list_tabs",
    "close_tab",
}
_STATUS_TTL = 45
_DEFAULT_MAX_CHARS = 2200


class WebBridgeConnector:
    def __init__(
        self,
        base_url: Optional[str] = None,
        session: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> None:
        self.base_url = (base_url or os.getenv("KIMI_WEBBRIDGE_URL") or "http://127.0.0.1:10086").rstrip("/")
        self.session = session or os.getenv("KIMI_WEBBRIDGE_SESSION") or "jarvis-kimi"
        self.timeout = timeout or float(os.getenv("KIMI_WEBBRIDGE_TIMEOUT", "8"))
        self._status_cache: Optional[Dict[str, Any]] = None
        self._status_ts = 0.0

    def status(self, *, force: bool = False) -> Dict[str, Any]:
        now = time.time()
        if not force and self._status_cache and (now - self._status_ts) < _STATUS_TTL:
            return {**self._status_cache, "cached": True}

        data: Dict[str, Any] = {}
        bin_path = shutil.which("kimi-webbridge") or os.path.expanduser(
            "~/.kimi-webbridge/bin/kimi-webbridge"
        )
        if os.path.exists(bin_path):
            try:
                proc = subprocess.run(
                    [bin_path, "status"],
                    capture_output=True,
                    text=True,
                    timeout=3,
                )
                if proc.returncode == 0 and proc.stdout.strip():
                    data = json.loads(proc.stdout)
            except Exception as e:
                data = {"error": str(e)}
        else:
            data = {"error": "kimi-webbridge binary not found"}

        out = {
            "ok": bool(data.get("running") and data.get("extension_connected")),
            "running": bool(data.get("running")),
            "extension_connected": bool(data.get("extension_connected")),
            "version": data.get("version", ""),
            "extension_version": data.get("extension_version", ""),
            "url": self.base_url,
            "session": self.session,
        }
        if data.get("error"):
            out["error"] = str(data["error"])
        self._status_cache = out
        self._status_ts = now
        return {**out, "cached": False}

    def is_available(self) -> bool:
        return bool(self.status().get("ok"))

    def command(
        self,
        action: str,
        args: Optional[Dict[str, Any]] = None,
        *,
        session: Optional[str] = None,
        max_chars: int = _DEFAULT_MAX_CHARS,
    ) -> Dict[str, Any]:
        action = action.strip()
        if action not in _ALLOWED_ACTIONS:
            return {"ok": False, "error": f"azione webbridge non permessa: {action}"}
        clean_args = self._sanitize_args(action, args or {})
        payload = {"action": action, "args": clean_args, "session": session or self.session}
        try:
            res = httpx.post(
                f"{self.base_url}/command",
                json=payload,
                timeout=self.timeout,
            )
            res.raise_for_status()
            raw = res.json()
        except Exception as e:
            return {"ok": False, "error": str(e), "action": action}
        return self._compact_response(raw, max_chars=max_chars)

    def snapshot_text(self, *, max_chars: int = _DEFAULT_MAX_CHARS) -> Dict[str, Any]:
        try:
            raw = self._post_command({"action": "snapshot", "args": {}, "session": self.session})
        except Exception as e:
            raw = {"ok": False, "error": str(e)}
        if not raw.get("ok"):
            err = str(raw.get("error", ""))
            if "has no tab" in err or "session" in err or "502" in err:
                try:
                    raw = self._post_command({"action": "snapshot", "args": {}})
                except Exception as e:
                    return {"ok": False, "error": str(e)}

        data = raw.get("data") or {}
        lines = [f"url:{data.get('url', '')}", f"title:{data.get('title', '')}"]
        tree_lines: List[str] = []
        self._walk_tree(data.get("tree"), tree_lines)
        seen = set()
        compact: List[str] = []
        for line in tree_lines:
            key = re.sub(r"\s+", " ", line).strip()
            if key and key not in seen:
                seen.add(key)
                compact.append(key)
        text = "\n".join(lines + compact)
        return {"ok": bool(raw.get("ok", True)), "text": self._trim(text, max_chars)}

    def _sanitize_args(self, action: str, args: Dict[str, Any]) -> Dict[str, Any]:
        if action == "navigate":
            url = str(args.get("url", "")).strip()
            if url and not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", url):
                url = "https://" + url
            return {
                "url": url,
                "newTab": bool(args.get("newTab", True)),
                "group_title": str(args.get("group_title", "JARVIS"))[:40],
            }
        if action == "fill":
            return {
                "selector": str(args.get("selector", ""))[:120],
                "value": str(args.get("value", ""))[:1200],
            }
        if action == "click":
            return {"selector": str(args.get("selector", ""))[:120]}
        if action == "find_tab":
            return {
                "url": str(args.get("url", ""))[:300],
                "active": bool(args.get("active", False)),
            }
        if action == "evaluate":
            code = str(args.get("code", ""))[:900]
            return {"code": code}
        return args

    def _post_command(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        res = httpx.post(
            f"{self.base_url}/command",
            json=payload,
            timeout=self.timeout,
        )
        res.raise_for_status()
        return res.json()

    def _compact_response(self, raw: Any, *, max_chars: int) -> Dict[str, Any]:
        if isinstance(raw, dict) and "data" in raw:
            data = raw.get("data")
            if isinstance(data, dict) and "tree" in data:
                snap = self.snapshot_text(max_chars=max_chars)
                return {"ok": bool(raw.get("ok", True)), "data": snap.get("text", "")}
            return {
                "ok": bool(raw.get("ok", True)),
                "data": self._compact_any(data, max_chars=max_chars),
            }
        return {"ok": True, "data": self._compact_any(raw, max_chars=max_chars)}

    def _compact_any(self, value: Any, *, max_chars: int) -> Any:
        if isinstance(value, str):
            return self._trim(value, max_chars)
        if isinstance(value, (int, float, bool)) or value is None:
            return value
        if isinstance(value, list):
            return [self._compact_any(v, max_chars=max_chars // 2) for v in value[:8]]
        if isinstance(value, dict):
            out: Dict[str, Any] = {}
            for k, v in list(value.items())[:16]:
                if k in {"data", "screenshot", "base64"} and isinstance(v, str) and len(v) > 200:
                    out[k] = f"<{len(v)} chars omessi>"
                else:
                    out[str(k)] = self._compact_any(v, max_chars=max_chars // 2)
            return out
        return self._trim(str(value), max_chars)

    def _walk_tree(self, node: Any, lines: List[str]) -> None:
        if isinstance(node, list):
            for item in node:
                self._walk_tree(item, lines)
            return
        if not isinstance(node, dict):
            return
        role = str(node.get("role") or "")
        name = str(node.get("name") or "").strip()
        ref = str(node.get("ref") or "").strip()
        if role and role != "InlineTextBox" and (name or ref):
            head = role
            if ref:
                head += f" {ref}"
            if name:
                head += f": {name}"
            lines.append(head[:220])
        for child in node.get("children") or []:
            self._walk_tree(child, lines)

    @staticmethod
    def _trim(text: str, max_chars: int) -> str:
        text = re.sub(r"\s+", " ", text.replace("\x00", " ")).strip()
        if len(text) <= max_chars:
            return text
        return text[: max_chars - 14].rstrip() + " …[troncato]"


_webbridge: Optional[WebBridgeConnector] = None


def get_webbridge() -> WebBridgeConnector:
    global _webbridge
    if _webbridge is None:
        _webbridge = WebBridgeConnector()
    return _webbridge
