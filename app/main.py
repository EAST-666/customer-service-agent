# -*- coding: utf-8 -*-
"""HTTP 服务：/chat /health /metrics /tickets"""
import json
import time
from collections import Counter
from datetime import datetime

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .config import LOG_PATH, TOP_K
from .kb import FAQIndex
from .llm import chat
from .session import SessionStore

app = FastAPI(title="客服 Agent 服务", version="1.0")
kb = FAQIndex()
sessions = SessionStore()

METRICS = {"requests": 0, "errors": 0, "latency": [], "tool_calls": Counter(), "tokens_in": 0, "tokens_out": 0}


class ChatIn(BaseModel):
    session_id: str = Field(min_length=1, max_length=64)
    message: str = Field(min_length=1, max_length=500)


def _log(row: dict):
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


@app.get("/health")
def health():
    return {"ok": True, "faq": len(kb.items), "ts": datetime.now().isoformat(timespec="seconds")}


@app.post("/chat")
def chat_endpoint(body: ChatIn):
    if not sessions.allow(body.session_id):
        raise HTTPException(status_code=429, detail="请求太频繁，请稍后再试")

    s = sessions.get(body.session_id)
    history = list(s["history"])
    hits = kb.search(body.message, TOP_K)
    METRICS["requests"] += 1
    started = time.time()

    try:
        answer, tools_log, meta = chat(body.session_id, history, body.message, hits)
    except Exception as e:  # noqa: BLE001
        METRICS["errors"] += 1
        _log({"ts": datetime.now().isoformat(timespec="seconds"), "sid": body.session_id,
              "q": body.message, "error": f"{type(e).__name__}: {e}"})
        raise HTTPException(status_code=500, detail=f"服务异常：{type(e).__name__}") from e

    sessions.append(body.session_id, "user", body.message)
    sessions.append(body.session_id, "assistant", answer)
    sessions.save()

    METRICS["latency"].append(meta["latency_ms"])
    METRICS["tokens_in"] += meta.get("in_tokens", 0)
    METRICS["tokens_out"] += meta.get("out_tokens", 0)
    for t in tools_log:
        METRICS["tool_calls"][t["name"]] += 1

    row = {
        "ts": datetime.now().isoformat(timespec="seconds"), "sid": body.session_id,
        "q": body.message, "a": answer, "hits": [h["id"] for h in hits],
        "tools": [t["name"] for t in tools_log], "latency_ms": meta["latency_ms"],
        "wall_ms": int((time.time() - started) * 1000),
        "in_tokens": meta.get("in_tokens", 0), "out_tokens": meta.get("out_tokens", 0),
    }
    _log(row)
    return {
        "answer": answer, "session_id": body.session_id,
        "sources": [{"id": h["id"], "q": h["q"]} for h in hits],
        "tools": [t["name"] for t in tools_log],
        "latency_ms": meta["latency_ms"],
    }


@app.get("/metrics")
def metrics():
    lat = sorted(METRICS["latency"])

    def pct(p):
        if not lat:
            return 0
        return lat[min(len(lat) - 1, int(len(lat) * p))]

    return {
        "requests": METRICS["requests"], "errors": METRICS["errors"],
        "p50_ms": pct(0.5), "p95_ms": pct(0.95), "max_ms": lat[-1] if lat else 0,
        "avg_ms": int(sum(lat) / len(lat)) if lat else 0,
        "tool_calls": dict(METRICS["tool_calls"]),
        "tokens_in": METRICS["tokens_in"], "tokens_out": METRICS["tokens_out"],
    }


@app.get("/tickets")
def tickets():
    path = LOG_PATH.parent.parent / "data" / "tickets.json"
    if not path.exists():
        return JSONResponse({"items": []})
    return {"items": json.loads(path.read_text(encoding="utf-8-sig"))}
