# 客服 Agent 服务（FastAPI 长驻）

一个能 7×24 挂着跑的售后客服服务：多轮对话 + FAQ 检索 + 三个工具（查订单 / 申请退款 / 转人工），带限流、日志、指标、看门狗自动重启。

不是聊天 demo——它的验收标准是「接口能压、进程能自愈、每条对话都有记录」。

## 实测结果

| 指标 | 数值 | 怎么测的 |
|---|---|---|
| 端到端 P95 | **1286 ms** | `scripts/loadtest.py --n 40 --c 5` |
| 吞吐 | 5.83 req/s（并发 5） | 同上，40 条全 200，0 失败 |
| 多轮 + 工具 | 4 轮对话全通过 | `scripts/smoke_test.py`（查物流 → 申请退款 → 问时效 → 转人工） |
| 限流 | 第 21 次起返回 429 | 同一 session_id 连发 24 次 |
| 服务自愈 | 杀进程后 8 秒恢复 | `scripts/watchdog.ps1`，连续 2 次健康检查失败即重启 |
| token 成本 | FAQ 类 864 in / 18 out；带工具 1600-3000 in | `/metrics` |

## 架构

```
客户端 ──POST /chat──▶ FastAPI
                        │
                        ├─ 限流（同 session 60 秒 20 次）→ 超了直接 429
                        ├─ SessionStore   多轮历史只留 8 条，落盘 data/sessions.json
                        ├─ FAQIndex       TF-IDF 余弦检索 10 条售后政策，取 top3 注入提示词
                        ├─ llm.chat()     最多 4 轮工具调用；轮数用完自动转人工兜底
                        │    ├─ order_lookup      查订单 + 稳定物流轨迹（同单号结果一致）
                        │    ├─ create_refund     校验枚举原因 / 7 天退款期 / 重复申请
                        │    └─ handoff_human     建工单 HYYMMDDNNN，写 data/tickets.json
                        └─ 写 logs/app.jsonl      每条一行：q/a/hits/tools/耗时/token
```

工具参数一律在本地再校验一遍：模型只输出「调哪个工具、传什么参数」，读写文件和数据库的是本进程，工具内部的异常统一包成 `{"error": ...}` 回灌给模型，让它自己修参数或改口解释。

## 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/chat` | `{"session_id": "...", "message": "..."}` → `{answer, sources, tools, latency_ms}` |
| GET | `/health` | 存活探针，返回 faq 条数（看门狗用） |
| GET | `/metrics` | requests / errors / p50 / p95 / max / avg / tool_calls / tokens |
| GET | `/tickets` | 已转人工的工单列表 |

```bash
curl -X POST http://127.0.0.1:8099/chat \
  -H "Content-Type: application/json; charset=utf-8" \
  -d '{"session_id":"u1","message":"我的订单 SF1234567890 到哪了"}'
```

## 跑起来

```powershell
# 1 依赖（Python 3.11 venv）
D:\bangong\venv-w2\Scripts\pip.exe install -r requirements.txt

# 2 放 DeepSeek key（纯文本，无 BOM）
#   文件：key.txt，内容只有一行 sk-xxx

# 3 造 4 条示例订单（含一条超 7 天、一条已完成）
D:\bangong\venv-w2\Scripts\python.exe tools\seed_orders.py

# 4 起服务
D:\bangong\venv-w2\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8099

# 5 冒烟 / 压测
D:\bangong\venv-w2\Scripts\python.exe scripts\smoke_test.py
D:\bangong\venv-w2\Scripts\python.exe scripts\loadtest.py --n 40 --c 5

# 6 挂看门狗（每 5 分钟探一次 /health，连续 2 次失败重启）
powershell -ExecutionPolicy Bypass -File scripts\watchdog.ps1
```

> `scripts/watchdog.ps1` 必须存成 **UTF-8 带 BOM**，否则 Windows PowerShell 5.1 按 GBK 读会把中文判成语法错误。

## 换成真实渠道

这一版用本地 SQLite 和自造物流轨迹，接真实业务时只换三处，接口不用动：

1. **查物流** → 快递鸟 `/query` 接口：`tools.order_lookup` 里把 `_track()` 换成真实请求，返回字段对齐 `tracking`。
2. **建工单** → 公司工单系统（或飞书多维表格）写入：`tools.handoff_human` 尾部换成 API 调用。
3. **接微信客服** → 微信客服回调要求 5 秒内响应，所以不能在回调里同步跑模型：回调只做「验签 → 写入队列 → 立即返回空串」，另一个线程消费队列、调 `/chat`、用 `customerService/sendMsg` 把答案推回去。队列我留在这个仓库外，因为它是部署形态问题，不是逻辑问题。

## 已知局限

- **FAQ 只有 10 条**，TF-IDF 检索在口语改写上召回有限（问「钱什么时候回来」可能命中不到「退款多久到账」）。生产上应换成向量检索或混合召回。
- **会话存在文件里**，单进程才安全；多副本部署要换 Redis。
- **没有做鉴权**，`/chat` 谁都能调；上线前要加 token 或网关白名单。
- **转人工只是写文件**，没有真正推给坐席系统。
- 压测只到并发 5：本机单实例 + 每次调 DeepSeek，瓶颈在模型侧（单次 0.5-2.4 秒），不在服务侧。

## 目录

```
app/          config.py 配置与提示词 · kb.py FAQ 检索 · session.py 会话与限流
              tools.py 三个工具 · llm.py 模型与工具循环 · main.py HTTP 层
data/         faq.json 售后政策 · orders.db 示例订单 · tickets.json 工单 · sessions.json 会话
scripts/      smoke_test.py · loadtest.py · watchdog.ps1
logs/         app.jsonl 每轮对话 · watchdog.log 重启记录
tools/        seed_orders.py 造数据
```
