# -*- coding: utf-8 -*-
"""建 orders.db 并塞 4 条示例订单（可重复执行，先删旧表）"""
import sqlite3
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "orders.db"

ORDERS = [
    # order_id, 状态, 承运商, 运单号, 金额, 创建于几天前, 退款状态
    ("SF1234567890", "运输中", "顺丰速运", "SF1234567890", 199.0, 1, "无"),
    ("SF9876543210", "已签收", "中通快递", "ZT7788990011", 89.9, 3, "无"),
    ("202401150001", "待发货", "圆通速递", "-", 45.5, 0, "无"),
    ("SF5555666677", "已完成", "顺丰速运", "SF5555666677", 129.0, 20, "无"),
]


def main():
    DB.parent.mkdir(parents=True, exist_ok=True)
    now = time.time()
    with sqlite3.connect(DB) as c:
        c.execute("DROP TABLE IF EXISTS orders")
        c.execute("""
            CREATE TABLE orders (
                order_id TEXT PRIMARY KEY,
                status TEXT, carrier TEXT, tracking_no TEXT,
                amount REAL, created_ts REAL, refund_state TEXT
            )""")
        c.executemany(
            "INSERT INTO orders VALUES (?,?,?,?,?,?,?)",
            [(oid, st, ca, tn, amt, now - days * 86400, rs) for oid, st, ca, tn, amt, days, rs in ORDERS],
        )
        c.commit()
        n = c.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    print(f"orders.db 就绪：{DB}（{n} 条订单）")
    for oid, *_ in ORDERS:
        print(" ", oid)


if __name__ == "__main__":
    main()
