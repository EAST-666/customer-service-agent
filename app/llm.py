# -*- coding: utf-8 -*-
"""模型调用：一次对话里最多跑 MAX_TOOL_ROUNDS 轮工具，超了就兜底转人工"""
import json
import time
import urllib.error
import urllib.request

from .config import API_URL, KEY_FILE, MAX_TOKENS, MAX_TOOL_ROUNDS, MODEL, SYSTEM_PROMPT, TEMPERATURE
from .tools import TOOLS, execute


def load_key() -> str:
    if not KEY_FILE.exists():
        raise RuntimeError(f"缺少 key 文件：{KEY_FILE}")
    return KEY_FILE.read_text(encoding="utf-8-sig").strip()


def _post(messages, tools, key):
    body = {
        "model": MODEL,
        "messages": messages,
        "temperature": TEMPERATURE,
        "max_tokens": MAX_TOKENS,
        "tools": tools,
        "tool_choice": "auto",
    }
    req = urllib.request.Request(
        API_URL,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def chat(session_id: str, history: list, user_text: str, kb_hits: list):
    """history 是除本轮外的历史（role/content 列表），返回 (answer, tools_log, usage_ms)"""
    key = load_key()
    ctx = "\n".join(f"[{i+1}] {h['q']}\n{h['a']}" for i, h in enumerate(kb_hits)) or "（本轮没有检索到相关资料）"
    system = SYSTEM_PROMPT + f"\n\n【资料】\n{ctx}"

    messages = [{"role": "system", "content": system}] + history + [{"role": "user", "content": user_text}]
    tools_log = []
    t0 = time.time()

    for _ in range(MAX_TOOL_ROUNDS):
        resp = _post(messages, TOOLS, key)
        msg = resp["choices"][0]["message"]
        calls = msg.get("tool_calls") or []
        if not calls:
            text = (msg.get("content") or "").strip()
            usage = resp.get("usage", {})
            return text, tools_log, {
                "latency_ms": int((time.time() - t0) * 1000),
                "in_tokens": usage.get("prompt_tokens", 0),
                "out_tokens": usage.get("completion_tokens", 0),
            }

        messages.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": calls})
        for c in calls:
            name = c["function"]["name"]
            try:
                args = json.loads(c["function"].get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            result = execute(name, args, session_id)
            tools_log.append({"name": name, "args": args, "result": result})
            messages.append({
                "role": "tool", "tool_call_id": c["id"],
                "content": json.dumps(result, ensure_ascii=False),
            })

    # 轮数用完还没收敛：兜底转人工，不让模型继续绕
    ticket = execute("handoff_human", {
        "reason": "工具调用轮数超过上限，自动转人工",
        "summary": f"用户原话：{user_text}",
    }, session_id)
    return f"这件事我处理不了，已经帮你转人工（工单 {ticket['ticket_no']}）。", tools_log, {
        "latency_ms": int((time.time() - t0) * 1000), "in_tokens": 0, "out_tokens": 0,
    }
