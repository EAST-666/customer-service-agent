# -*- coding: utf-8 -*-
"""会话状态：多轮历史 + 待补槽位 + 限流，落盘可恢复"""
import json
import threading
import time
from collections import deque
from pathlib import Path

from .config import HISTORY_KEEP, RATE_LIMIT, RATE_WINDOW, SESSIONS_PATH


class SessionStore:
    def __init__(self, path: Path = SESSIONS_PATH):
        self.path = path
        self.lock = threading.Lock()
        self.data = {}
        self.hits = {}
        if path.exists():
            try:
                self.data = json.loads(path.read_text(encoding="utf-8-sig"))
            except Exception:
                self.data = {}

    # ---------- 会话 ----------
    def get(self, sid: str):
        with self.lock:
            s = self.data.get(sid)
            if s is None:
                s = {"history": [], "pending": None, "turns": 0, "created": time.time()}
                self.data[sid] = s
            return s

    def append(self, sid: str, role: str, content: str):
        with self.lock:
            s = self.data.setdefault(sid, {"history": [], "pending": None, "turns": 0, "created": time.time()})
            s["history"].append({"role": role, "content": content})
            s["history"] = s["history"][-HISTORY_KEEP:]
            if role == "user":
                s["turns"] = s.get("turns", 0) + 1

    def set_pending(self, sid: str, pending):
        with self.lock:
            self.data.setdefault(sid, {"history": [], "turns": 0})["pending"] = pending

    def save(self):
        with self.lock:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=1), encoding="utf-8")
            tmp.replace(self.path)

    # ---------- 限流 ----------
    def allow(self, sid: str) -> bool:
        now = time.time()
        with self.lock:
            q = self.hits.setdefault(sid, deque())
            while q and now - q[0] > RATE_WINDOW:
                q.popleft()
            if len(q) >= RATE_LIMIT:
                return False
            q.append(now)
            return True
