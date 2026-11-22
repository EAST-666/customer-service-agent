# -*- coding: utf-8 -*-
"""并发压测：--n 总请求数 --c 并发数。只问 FAQ 类问题，避免每次都走工具链。"""
import argparse
import json
import statistics
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

BASE = "http://127.0.0.1:8099"
QUESTIONS = ["退款多久到账", "发什么快递", "怎么开发票", "会员有什么权益", "多久发货"]

lock = threading.Lock()
lat = []
codes = []


def one(i: int):
    sid = f"load-{i % 20}"
    body = json.dumps({"session_id": sid, "message": QUESTIONS[i % len(QUESTIONS)]}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(BASE + "/chat", data=body,
                                 headers={"Content-Type": "application/json; charset=utf-8"}, method="POST")
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            codes.append(r.status)
            r.read()
    except urllib.error.HTTPError as e:
        codes.append(e.code)
    except Exception:
        codes.append(0)
    with lock:
        lat.append(int((time.time() - t0) * 1000))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=40)
    ap.add_argument("--c", type=int, default=5)
    a = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=a.c) as pool:
        list(pool.map(one, range(a.n)))
    dur = time.time() - t0
    ok = sum(1 for c in codes if c == 200)
    lat_sorted = sorted(lat)

    def pct(p):
        return lat_sorted[min(len(lat_sorted) - 1, int(len(lat_sorted) * p))]

    print(f"请求 {a.n} 条 / 并发 {a.c} / 用时 {dur:.1f}s / 吞吐 {a.n/dur:.2f} req/s")
    print(f"成功 {ok} / 失败 {a.n-ok}（状态码分布 {dict((c, codes.count(c)) for c in set(codes))}）")
    print(f"P50 {pct(0.5)}ms / P95 {pct(0.95)}ms / 最大 {lat_sorted[-1]}ms / 均值 {int(statistics.mean(lat))}ms")


if __name__ == "__main__":
    main()
