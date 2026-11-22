# -*- coding: utf-8 -*-
"""三个工具：查订单、申请退款、转人工。参数一律在本地再校验一遍。"""
import json
import random
import re
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path

from .config import ORDERS_DB, TICKETS_PATH

ORDER_ID_RE = re.compile(r"^(SF\d{10}|\d{8,14})$")
CARRIERS = ["顺丰速运", "中通快递", "圆通速递"]
CITIES = ["杭州转运中心", "上海转运中心", "南昌转运中心", "金华转运中心", "目的地派送站"]
REFUND_REASONS = {"质量问题", "未收到货", "发错货", "不想要了", "其他"}

# ---------- Schema ----------
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "order_lookup",
            "description": "查订单状态与物流轨迹。用户问到进度、发货、签收、退款状态时必须调用。",
            "parameters": {
                "type": "object",
                "properties": {"order_id": {"type": "string", "description": "订单号，SF 开头 12 位或纯数字 8-14 位"}},
                "required": ["order_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_refund",
            "description": "为订单提交退款申请。必须先查过订单，且用户明确同意退款。",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string"},
                    "reason": {"type": "string", "enum": sorted(REFUND_REASONS)},
                },
                "required": ["order_id", "reason"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "handoff_human",
            "description": "转人工坐席。投诉、要求赔偿、要求上级、情绪激烈、或工具连续失败时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {"type": "string", "description": "一句话说明为什么要转人工"},
                    "summary": {"type": "string", "description": "给坐席看的上下文摘要，含订单号和用户诉求"},
                },
                "required": ["reason", "summary"],
            },
        },
    },
]


def _conn():
    c = sqlite3.connect(ORDERS_DB)
    c.row_factory = sqlite3.Row
    return c


def _track(order_id: str, status: str):
    """按订单号生成稳定的物流轨迹（同一单号每次结果一致）"""
    rnd = random.Random(order_id)
    now = datetime.now()
    base = 2 if status in ("待发货", "已取消") else 5
    stops = []
    for i in range(min(base, 5)):
        t = now - timedelta(hours=(base - i) * rnd.randint(6, 20))
        stops.append({"time": t.strftime("%m-%d %H:%M"), "desc": rnd.choice(CITIES) + "：" + rnd.choice(
            ["已收件", "运输中", "已到达", "已发出", "派送中"])})
    return stops


def order_lookup(order_id: str):
    oid = (order_id or "").strip().upper()
    if not ORDER_ID_RE.match(oid):
        return {"error": "invalid_order_id", "message": "订单号格式不对，应为 SF 开头 12 位或 8-14 位数字"}
    with _conn() as c:
        row = c.execute("SELECT * FROM orders WHERE order_id = ?", (oid,)).fetchone()
    if row is None:
        return {"error": "not_found", "message": f"没有查到订单 {oid}"}
    data = dict(row)
    data["tracking"] = _track(oid, data["status"])
    return data


def create_refund(order_id: str, reason: str):
    oid = (order_id or "").strip().upper()
    if reason not in REFUND_REASONS:
        return {"error": "invalid_reason", "message": f"退款原因必须是：{'/'.join(sorted(REFUND_REASONS))}"}
    with _conn() as c:
        row = c.execute("SELECT * FROM orders WHERE order_id = ?", (oid,)).fetchone()
        if row is None:
            return {"error": "not_found", "message": f"没有查到订单 {oid}"}
        if row["status"] in ("已签收", "已完成") and (time.time() - row["created_ts"]) > 7 * 86400:
            return {"error": "refund_window_closed", "message": "该订单已超过 7 天无理由退款期，需要人工审核"}
        if row["refund_state"] == "处理中":
            return {"error": "duplicate", "message": "该订单已有退款申请在处理中"}
        refund_id = "R" + datetime.now().strftime("%y%m%d") + f"{random.randint(1000, 9999)}"
        c.execute("UPDATE orders SET refund_state = ? WHERE order_id = ?", ("处理中", oid))
        c.commit()
    return {"refund_id": refund_id, "status": "已受理", "eta": "1-3 个工作日原路退回"}


def handoff_human(reason: str, summary: str, session_id: str = ""):
    path = Path(TICKETS_PATH)
    items = []
    if path.exists():
        items = json.loads(path.read_text(encoding="utf-8-sig"))
    ticket_no = "H" + datetime.now().strftime("%y%m%d") + f"{len(items) + 1:03d}"
    items.append({
        "ticket_no": ticket_no, "session_id": session_id, "reason": reason,
        "summary": summary, "at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "status": "待接单",
    })
    path.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"ticket_no": ticket_no, "queue_position": len(items), "sla": "工作时间内 5 分钟响应"}


def execute(name: str, args: dict, session_id: str = ""):
    """分发 + 兜底：任何异常都包成 error 交回模型，不向上抛"""
    try:
        if name == "order_lookup":
            return order_lookup(args.get("order_id", ""))
        if name == "create_refund":
            return create_refund(args.get("order_id", ""), args.get("reason", ""))
        if name == "handoff_human":
            return handoff_human(args.get("reason", ""), args.get("summary", ""), session_id)
        return {"error": "unknown_tool", "message": f"没有这个工具：{name}"}
    except Exception as e:  # noqa: BLE001
        return {"error": "tool_exception", "message": f"{type(e).__name__}: {e}"}
