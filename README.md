# X7AgentBench-v2

X7 智能客服对话质量测评框架。自动化驱动 X7 与模拟用户多轮对话，基于节点日志和对话内容双维度评分，输出 Markdown 测评报告，支持断点续传。

---

## 核心架构

```
┌─────────────────────────────────────────────────────────────────┐
│                         main.py                                  │
│                   (CLI 入口 / 批量编排)                          │
└──────────────┬───────────────────────────────────┬───────────────┘
               │                                   │
               ▼                                   ▼
┌──────────────────────────┐         ┌────────────────────────────┐
│      DialogueRunner       │         │      ReportGenerator       │
│      (主编排器)            │         │   (报告生成 + 断点续传)    │
│                          │         └────────────────────────────┘
│  ┌─────────────────────┐ │                    ▲
│  │  CustomerAgent      │ │◄── 用户追问模拟   │
│  │  温度 0.8 · 有记忆   │ │                    │
│  └─────────────────────┘ │                    │
│               ▲          │                    │
│               │ 第1轮直接 │                    │
│  ┌────────────┴─────────┐│    ┌────────────────────────────┐
│  │       X7Agent         ││    │        LogFetcher          │
│  │  HTTP 封装 · UUID会话 ││    │  (对话结束后拉节点日志)    │
│  └───────────────────────┘│    └────────────────────────────┘
│               ▲          │
│               │          │
│  ┌────────────┴─────────┐│
│  │      StopAgent       │◄── 终止判断 (置信度阈值 0.8)
│  │  温度 0.3 · 有记忆   │
│  └──────────────────────┘
│               ▲
│               │ 对话全部结束后
│  ┌────────────┴──────────┐
│  │      EvalAgent        │◄── 最终评分 (无记忆 · 独立评分)
│  │  温度 0.5             │
│  └───────────────────────┘
```

---

## 四个 Agent 职责

| Agent | 温度 | 记忆 | 职责边界 |
|-------|------|------|----------|
| **CustomerAgent** | 0.8 | 有 | 模拟用户追问。首问 `get_first_question()` **不调模型**，直接返回测试数据，保证测试锚点稳定。后续 `respond(x7_reply)` 才调 LLM 生成追问。 |
| **X7Agent** | — | — | X7 API 的 HTTP 封装，零业务逻辑。`session_id` 用 UUID 生成并全程持久化，供 LogFetcher 查询。失败返回错误字符串，**不抛异常**，对话 loop 继续。 |
| **StopAgent** | 0.3 | 有 | 判断是否终止对话。优先规则：`len(conversation) >= max_rounds` 直接返回 True（不调模型）。LLM 判断时 `confidence < 0.8` 强制转继续，防止幻觉绕过停止机制。 |
| **EvalAgent** | 0.5 | **无** | 最终评分。每次独立评估，无记忆累积。有 `node_chain_text` 时评路由正确性、工具成功率、是否幻觉编造；无日志时工具调用分默认给满分 4（无法判定就不扣分）。 |

---

## 关键设计决策

| 决策 | 理由 |
|------|------|
| **首问不经 CustomerAgent** | 锚定测试起点，保证每次对话第一句话完全稳定可复现，不被 LLM 改写 |
| **StopAgent 置信度阈值 0.8** | Hallucination 最危险的形态是回答得越有信心，越容易蒙过停止机制。置信度是一道保险 |
| **LogFetcher 在对话结束后调用** | 实时拉会干扰对话时序，日志系统本身有延迟 |
| **EvalAgent 无记忆** | 每次独立评分，消除累积偏差 |
| **断点续传扫描文件名** | 无需数据库，轻量，宕机重启安全。序号保持字符串格式（`session_id_emp_id_yyyyMMdd`），int 转换会出错 |
| **所有 list 字段走 `format_list()`** | 单一入口处理，多条加序号拼接，单条直接返回字符串，避免多处格式不一致 |

---

## 安装

```bash
# 克隆后创建虚拟环境（不污染全局）
python -m uv venv .venv
.venv/Scripts/activate  # Windows
# source .venv/bin/activate  # Linux/Mac

# 安装依赖
pip install -r requirements.txt
```

## 配置

复制 `.env.example` 为 `.env`，填入真实值：

```bash
DASHSCOPE_API_KEY=sk-xxxxxxxxxxxxxxxx   # 阿里云 DashScope API Key
X7_EMP_ID=your_emp_id
X7_API_URL=https://x7-internal.example.com/api/chat
LOG_API_URL=https://x7-internal.example.com/api/logs
```

## 使用

```bash
# 使用默认数据集
python main.py

# 指定数据集文件
python main.py --dataset datasets/my_dataset.json

# 只跑指定场景
python main.py --dataset datasets/my_dataset.json --scene 公网出口
```

输出结构：
```
outputs/
└── {dataset_name}/
    ├── {dataset_name}_case001.md    # 每 case 一份报告
    ├── {dataset_name}_case002.md
    └── summary.json                  # 批次汇总
```

## 评分体系

| 维度 | 分值 | 说明 |
|------|------|------|
| 对话质量分 | 0-6 | 回答准确性、帮助度、问题解决度 |
| 工具调用分 | 0-4 | 路由正确性、工具成功率、幻觉检测（无日志时默认 4 分） |
| **总分** | **0-10** | 两项相加 |

| 分数段 | 等级 |
|--------|------|
| 9-10 | 优秀 |
| 6-8 | 及格 |
| 0-5 | 不及格 |

---

## 测试

所有外部调用（LLM / X7 API / 日志 API）全部 mock，无需真实凭证即可运行：

```bash
pytest tests/ -v
```

覆盖场景：
- `test_stop_agent.py` — 置信度阈值、超轮数旁路、JSON 解析失败
- `test_eval_agent.py` — 有/无节点日志的评分、降级处理
- `test_dialogue_runner.py` — 正常停止、强制终止、X7 超时不崩溃、LogFetcher 失败报告仍生成
- `test_report_generator.py` — 断点续传、序号字符串格式、目录自动创建

---

## 数据集格式

```json
{
  "序号": "session_emp_12345_20250126",
  "客户问题": ["无法访问外网", "DNS 也改过了"],
  "客户信息": ["Windows 10", "已连接网线"],
  "会话特征": ["描述问题简洁"],
  "参考答案": ["检查 DNS 配置"],
  "判停规则": [],
  "打分规则": ["准确解决给高分"],
  "标注信息": {
    "symptom": "无法上网",
    "root_cause": "DNS配置异常"
  }
}
```

`客户问题[0]` 为首问，直接发给 X7，不经 CustomerAgent。