# X7AgentBench-v2

X7 智能客服对话质量测评框架。自动化驱动 X7 与模拟用户多轮对话，基于节点日志和对话内容双维度评分，输出 Markdown 测评报告，支持断点续传。

---

## 目录

- [项目结构](#项目结构)
- [快速开始](#快速开始)
- [核心架构](#核心架构)
- [四个 Agent 职责](#四个-agent-职责)
- [数据流完整时序](#数据流完整时序)
- [配置参数详解](#配置参数详解)
- [关键设计决策](#关键设计决策)
- [异常处理原则](#异常处理原则)
- [数据集格式](#数据集格式)
- [输出报告格式](#输出报告格式)
- [评分体系](#评分体系)
- [测试](#测试)
- [环境变量参考](#环境变量参考)

---

## 项目结构

```
X7AgentBench-v2/
├── agents/
│   ├── __init__.py
│   ├── customer_agent.py     # 模拟用户追问，首问不调模型
│   ├── x7_agent.py          # X7 API HTTP 封装，返回错误字符串不抛异常
│   ├── stop_agent.py        # 终止判断，置信度 < 0.8 强制转继续
│   └── eval_agent.py        # 最终评分，无记忆独立评估
├── tests/
│   ├── __init__.py
│   ├── test_stop_agent.py       # 4 个测试
│   ├── test_eval_agent.py       # 3 个测试
│   ├── test_dialogue_runner.py  # 4 个测试
│   └── test_report_generator.py # 4 个测试
├── data_structures.py    # TestCase、DialogueTurn、RunResult、format_list()
├── config.py             # Config dataclass，所有参数从环境变量读取
├── dialogue_runner.py    # 主编排器，驱动完整对话流程
├── log_fetcher.py        # 对话结束后拉取 X7 内部节点日志
├── report_generator.py   # Markdown 报告生成 + 断点续传
├── main.py               # CLI 入口
├── requirements.txt      # 依赖清单
├── pyproject.toml        # UV 项目配置
├── .env.example          # 环境变量模板（不提交 Git）
├── CLAUDE.md             # 给 Claude Code 的开发提示
└── SPEC.md               # 完整需求规格说明书
```

---

## 快速开始

```bash
# 1. 克隆后创建虚拟环境（不污染全局 Python）
python -m uv venv .venv
.venv/Scripts\activate    # Windows
# source .venv/bin/activate  # Linux / macOS

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置环境变量
cp .env.example .env
# 编辑 .env，填入真实凭证

# 4. 准备数据集（格式见下方）
# 5. 运行
python main.py --dataset datasets/my_dataset.json
```

---

## 核心架构

```
                    main.py（CLI 入口）
                         │
                         ▼
              ┌──────────────────────┐
              │    DialogueRunner     │  主编排器
              │    (dialogue_runner)  │
              └──────────┬───────────┘
                         │
       ┌─────────────────┼─────────────────┬──────────────────┐
       │                 │                 │                  │
       ▼                 ▼                 ▼                  ▼
┌────────────┐   ┌────────────┐   ┌─────────────┐   ┌─────────────┐
│ Customer   │   │    X7     │   │   Stop      │   │    Eval     │
│  Agent     │◄──│  Agent    │◄──│   Agent     │   │   Agent     │
│ 温度 0.8   │   │ HTTP封装  │   │ 温度 0.3    │   │  温度 0.5   │
│ 有记忆      │   │ 有session │   │ 有记忆      │   │ **无记忆**  │
└────────────┘   └─────┬──────┘   └──────┬──────┘   └──────┬──────┘
                       │                 │                  │
                       │   ┌─────────────┘                  │
                       │   │ 对话结束后调用                  │
                       ▼   ▼                                │
              ┌──────────────────┐                          │
              │   LogFetcher     │◄─────────────────────────┘
              │ (拉节点调用链路)  │         node_chain_text
              └──────────────────┘
                       │
                       ▼
              ┌──────────────────┐
              │  ReportGenerator │  写 Markdown 报告 + 断点续传
              └──────────────────┘
```

---

## 四个 Agent 职责

### CustomerAgent

- **温度 0.8**（高多样性，像真人）
- **有记忆**（需记住上下文才能追问）
- `get_first_question()` → 直接返回 `test_case.客户问题[0]`，**不调模型**。这是设计约束，保证测试锚点稳定。
- `respond(x7_reply)` → 追加 X7 回复到历史 → 调 LLM 生成追问 → 返回追问字符串

### X7Agent

- **无温度**（只是 HTTP 封装）
- 生成 **UUID session_id** 全程持久化，LogFetcher 靠它查日志
- `respond(user_input)` → POST 到 X7 API → 成功返回回答，失败返回错误字符串，**绝不抛异常**

### StopAgent

- **温度 0.3**（高一致性，今天停明天也停）
- **有记忆**（看整段对话走势）
- `should_stop(conversation, stop_rules)` → 返回 `(bool, reason, detail)`
- 判断优先级：
  1. `len(conversation) >= max_rounds` → 直接返回 `True`（**不调模型**）
  2. 调 LLM，输出 `{"should_stop": bool, "reason": str, "confidence": float}`
  3. `should_stop=True` 且 `confidence < 0.8` → **强制转 False**（置信度过滤）

### EvalAgent

- **温度 0.5**（理解力但不飘）
- **无记忆**（每次独立评分，消除累积偏差）
- `evaluate(conversation, test_case, node_chain_text)` → 返回评分 dict
- 有 `node_chain_text` → 评路由正确性、工具成功率、幻觉编造
- 无日志 → 工具调用分默认给 4 分（无法判定就不扣分）

---

## 数据流完整时序

```
1. main.py 加载数据集 → 按序号过滤已完成的 case（断点续传）

2. DialogueRunner.run(test_case) 开始：

   第1轮：
   ├─ CustomerAgent.get_first_question()  ← 直接从 test_case 拿，不调模型
   ├─ X7Agent.respond(首问)              → X7 回复
   ├─ time.sleep(x7_rate_limit_seconds)  ← X7 限流
   └─ StopAgent.should_stop(conversation, 判停规则)  ← 判停（此时 conversation=[]）

   第2轮起（循环）：
   ├─ CustomerAgent.respond(x7_reply)    ← 调 LLM 生成追问
   ├─ X7Agent.respond(customer_input)    → X7 回复
   ├─ time.sleep(x7_rate_limit_seconds)
   ├─ StopAgent.should_stop(conversation, 判停规则)
   └─ stop=True → 退出循环

3. 对话结束：
   ├─ LogFetcher.fetch_session_nodes(session_id, start_dt, end_dt)  → node_chain
   ├─ LogFetcher.format_for_eval(node_chain)                       → node_chain_text
   └─ EvalAgent.evaluate(conversation, test_case, node_chain_text) → report

4. ReportGenerator.generate_report(result, dataset_name)  → 写 .md 文件

5. main.py 打印汇总 → 保存 summary.json
```

---

## 配置参数详解

所有参数在 `config.py` 的 `Config` dataclass 中定义，从环境变量读取。

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `customer_model` | `"qwen-plus"` | CustomerAgent 调用的模型 |
| `customer_temperature` | `0.8` | 高温保证多样性，像真人 |
| `customer_max_tokens` | `1000` | |
| `stop_model` | `"qwen-plus"` | StopAgent 调用的模型 |
| `stop_temperature` | `0.3` | 低温保证一致性 |
| `stop_max_tokens` | `500` | |
| `eval_model` | `"qwen-plus"` | EvalAgent 调用的模型 |
| `eval_temperature` | `0.5` | 中温，理解力但不飘 |
| `eval_max_tokens` | `2000` | |
| `x7_api_url` | — | X7 API 地址，从 `X7_API_URL` 读 |
| `x7_emp_id` | `"test_user"` | 从 `X7_EMP_ID` 读 |
| `x7_timeout` | `90` | 秒 |
| `x7_rate_limit_seconds` | `60` | X7 限流，每调一次休息这么多秒 |
| `log_api_url` | — | 日志 API 地址，从 `LOG_API_URL` 读 |
| `log_time_buffer_minutes` | `2` | 查询时间窗口前后各扩 2 分钟 |
| `max_rounds` | `10` | 超过强制终止，模拟转人工 |
| `stop_confidence_threshold` | `0.8` | 低于此值停止判断强制转继续 |
| `default_dataset_path` | `"datasets/example_dataset.json"` | |
| `output_dir` | `"outputs"` | |
| `api_key` | — | 从 `DASHSCOPE_API_KEY` 读 |
| `api_base_url` | `"https://dashscope.aliyuncs.com/compatible-mode/v1"` | |

---

## 关键设计决策

| 决策 | 理由 |
|------|------|
| **首问不经 CustomerAgent** | 锚定测试起点，`客户问题[0]` 完全稳定，不被 LLM 改写 |
| **StopAgent 置信度阈值 0.8** | Hallucination 最危险形态：回答越有信心，越容易蒙过停止机制。置信度阈值是保险 |
| **LogFetcher 在对话结束后调用** | 实时拉干扰对话时序；日志系统本身有延迟，需要等 |
| **EvalAgent 无记忆** | 每次独立评分，消除累积偏差 |
| **断点续传扫描文件名** | 无需数据库，轻量，宕机重启安全 |
| **序号保持字符串格式** | 格式 `session_id_emp_id_yyyyMMdd`，int 转换会出错 |
| **所有 list 字段走 `format_list()`** | 单一入口，单条直接返回，多条加序号拼接，避免格式不一致 |
| **X7 失败返回错误字符串** | 不抛异常，对话 loop 继续，整个批量任务不因单个 case 中断 |

---

## 异常处理原则

| 场景 | 处理方式 | 不抛异常原因 |
|------|----------|-------------|
| Agent 内 LLM 调用失败 | 降级返回默认值 | 不让单个 Agent 导致整批任务中断 |
| X7 接口失败 | 返回错误字符串（如 `[X7接口错误: 500 / ...]`） | 对话 loop 继续 |
| LogFetcher 拉不到日志 | 返回 `[]` 或固定提示字符串 | 日志拉不到不影响测评，工具调用分默认满分 |

---

## 数据集格式

```json
{
  "序号": "session_emp_12345_20250126",
  "客户问题": [
    "无法访问外网",
    "DNS 也改过了还是不行",
    "好的谢谢"
  ],
  "客户信息": [
    "Windows 10 系统",
    "已连接网线",
    "IP: 192.168.1.100"
  ],
  "会话特征": [
    "描述问题简洁",
    "遇到技术术语会追问"
  ],
  "参考答案": [
    "检查 DNS 配置是否正确",
    "检查网关设置"
  ],
  "判停规则": [
    "用户明确说谢谢且无新问题则停止"
  ],
  "打分规则": [
    "准确解决给 9-10 分",
    "部分解决给 6-8 分",
    "未解决给 0-5 分"
  ],
  "标注信息": {
    "symptom": "无法上网",
    "product": "企业网络",
    "root_cause": "DNS 配置异常",
    "intelligent_answer_effectiveness": 8,
    "content_score": 8
  }
}
```

**关键约束**：`客户问题[0]` 是首问，直接发给 X7，不经 CustomerAgent。后续问题由 CustomerAgent 根据 X7 回复调 LLM 生成。

---

## 输出报告格式

每个 case 生成一份 Markdown 报告，路径：
```
outputs/{dataset_name}/{dataset_name}_{序号}.md
```

报告结构：

```markdown
# 测评报告：{序号}

## 基本信息
- 数据集：{dataset_name}
- 测试时间：{start_dt} ~ {end_dt}
- 对话轮数：{len(conversation)}
- 终止原因：{stop_reason}

## 评分结果
- **总分：{总分} / 10**
- 对话质量分：{对话质量分} / 6
- 工具调用分：{工具调用分} / 4
- 评语：{评语}
- 问题点：
  - {问题点1}
  - {问题点2}

## 对话过程
### 第 1 轮
**用户**：{customer}
**X7**：{x7}

### 第 2 轮
**用户**：{customer}
**X7**：{x7}

## 节点调用链路
## 节点调用链路
- [SUCCESS] 意图识别 (rt: 234ms)
  - input: 我的机器访问公网域名不通
  - output: 意图=安全外联配置
- [FAILED] SmartNAT查询工具 (rt: timeout)
  - error: 连接超时

## 标注信息存档（仅供分层分析，不参与评分）
- 序号：{序号}
- symptom: {标注信息.symptom}
- product: {标注信息.product}
- root_cause: {标注信息.root_cause}
```

---

## 评分体系

| 维度 | 分值 | 说明 |
|------|------|------|
| 对话质量分 | 0-6 | 基于对话过程，考察回答准确性、帮助度、问题解决度 |
| 工具调用分 | 0-4 | 基于节点日志，考察路由正确性、工具成功率、是否幻觉编造。无日志时默认 **4 分** |
| **总分** | **0-10** | 两项相加 |

| 分数段 | 等级 |
|--------|------|
| 9-10 | 优秀 |
| 6-8 | 及格 |
| 0-5 | 不及格 |

---

## 测试

所有外部调用（LLM / X7 API / 日志 API）全部 mock，无需真实凭证：

```bash
pytest tests/ -v
```

**总计 15 个测试，全部通过**：

| 文件 | 覆盖场景 |
|------|----------|
| `test_stop_agent.py` | 置信度阈值（0.9 通过 / 0.6 强制转继续）、超轮数旁路（直接返回 True 不调 LLM）、JSON 解析失败 |
| `test_eval_agent.py` | 有节点日志完整评分、无节点日志默认满分、JSON 解析失败降级到总分 0 |
| `test_dialogue_runner.py` | 3 轮内正常停止、达到 max_rounds 强制终止、X7 超时不崩溃（返回错误字符串）、LogFetcher 失败报告仍生成 |
| `test_report_generator.py` | 断点续传（扫描文件名跳过已完成）、序号保持字符串格式（不转 int）、输出目录不存在自动创建 |

---

## 环境变量参考

```bash
# 阿里云 DashScope API Key（调用 qwen-plus）
DASHSCOPE_API_KEY=sk-xxxxxxxxxxxxxxxx

# X7 被测系统
X7_EMP_ID=your_emp_id
X7_API_URL=https://x7-internal.example.com/api/chat

# 日志查询
LOG_API_URL=https://x7-internal.example.com/api/logs
```

完整配置见 `config.py` 的 `Config` dataclass。

---

## CLI 用法

```bash
# 使用默认数据集路径（config.default_dataset_path）
python main.py

# 指定数据集
python main.py --dataset datasets/my_dataset.json

# 只跑指定场景名
python main.py --dataset datasets/my_dataset.json --scene 公网出口
```

全部完成后打印汇总：
```
总数：50 | 成功：48 | 失败：2
平均分：7.42 / 10
分数分布：{'满分(9-10)': 12, '及格(6-8)': 28, '不及格(0-5)': 8}
失败 case：['session_emp_001_20250126', 'session_emp_002_20250126']
汇总已保存：outputs/my_dataset/summary.json
```