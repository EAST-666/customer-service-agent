# -*- coding: utf-8 -*-
"""冒烟测试：多轮 + 工具调用 + FAQ 检索。用法 python scripts/smoke_test.py"""
import json
import sys
import time
import urllib.request

BASE = "http://127.0.0.1:8099"


def ask(sid: str, msg: str):
    body = json.dumps({"session_id": sid, "message": msg}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        BASE + "/chat", data=body,
        headers={"Content-Type": "application/json; charset=utf-8"}, method="POST",
    )
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=90) as r:
        d = json.loads(r.read().decode("utf-8"))
    print("Q:", msg)
    print("A:", d["answer"])
    print(f"   工具={d['tools']} 资料={[s['id'] for s in d['sources']]} 模型={d['latency_ms']}ms 全程={int((time.time()-t0)*1000)}ms")
    print()
    return d


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sid = "demo-001"
    ask(sid, "我的订单 SF1234567890 到哪了")
    ask(sid, "那这个订单我要退款，质量问题")
    ask(sid, "退款多久能到账")
    ask(sid, "我要投诉，转人工")
