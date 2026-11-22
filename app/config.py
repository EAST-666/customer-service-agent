# -*- coding: utf-8 -*-
"""配置：路径、模型、限流、轮数等"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
LOGS = ROOT / "logs"
LOGS.mkdir(exist_ok=True)

FAQ_PATH = DATA / "faq.json"
ORDERS_DB = DATA / "orders.db"
TICKETS_PATH = DATA / "tickets.json"
SESSIONS_PATH = DATA / "sessions.json"
LOG_PATH = LOGS / "app.jsonl"

KEY_FILE = Path(os.getenv("CS_KEY_FILE", str(ROOT / "key.txt")))
API_URL = os.getenv("CS_API_URL", "https://api.deepseek.com/chat/completions")
MODEL = os.getenv("CS_MODEL", "deepseek-chat")
TEMPERATURE = float(os.getenv("CS_TEMPERATURE", "0.2"))
MAX_TOKENS = int(os.getenv("CS_MAX_TOKENS", "500"))

# 多轮：保留最近 8 条消息（4 轮）
HISTORY_KEEP = int(os.getenv("CS_HISTORY_KEEP", "8"))
# 同一轮里最多让模型调用几次工具
MAX_TOOL_ROUNDS = int(os.getenv("CS_MAX_TOOL_ROUNDS", "4"))
# 单会话限流：60 秒内最多 20 次
RATE_LIMIT = int(os.getenv("CS_RATE_LIMIT", "20"))
RATE_WINDOW = int(os.getenv("CS_RATE_WINDOW", "60"))

TOP_K = int(os.getenv("CS_TOP_K", "3"))

SYSTEM_PROMPT = """你是一名企业在线客服，服务对象是下单用户。
你的知识只来自下面提供的【资料】和工具返回结果。

规则：
1. 资料里没有的内容，直接说「这个我不太确定」，不要编造政策、时效、金额。
2. 涉及订单进度、物流、退款状态，必须先调 order_lookup，不要凭用户说的单号推测结果。
3. 需要用户提供信息时，一次只问一件事。
4. 判断需要人工介入（投诉、赔付、要求上级、情绪激烈、工具连续失败），调用 handoff_human。
5. 回答控制在 120 字以内，短句，不要客套话，不要输出 markdown 和代码块。
6. 不要叫用户「亲」，不要用感叹号。
"""
