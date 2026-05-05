# X7 Agent Benchmark Framework Specification

## 1. Project Overview

**Project Name:** X7AgentBench
**Type:** Python CLI testing framework
**Core Functionality:** Benchmark X7 agent conversations against labeled test cases, with automated scoring and report generation
**Target Users:** Network operations engineers evaluating X7 agent performance

## 2. Architecture

```
├── agents/
│   ├── customer_agent.py   # Simulates user follow-up questions
│   ├── x7_agent.py         # HTTP wrapper for X7 API
│   ├── stop_agent.py       # Determines when to end conversation
│   └── eval_agent.py       # Scores conversation quality
├── data_structures.py       # TestCase, DialogueTurn, RunResult dataclasses
├── config.py                # All configuration via dataclass + env vars
├── dialogue_runner.py      # Main orchestration loop
├── log_fetcher.py          # Fetches node execution logs post-conversation
├── report_generator.py      # Generates markdown reports with checkpoint support
├── main.py                  # CLI entry point
├── tests/                   # pytest unit tests (mock all external calls)
├── CLAUDE.md               # Developer guidance
├── .env.example             # Environment variable template
└── requirements.txt        # Dependencies
```

## 3. Key Design Decisions

| Decision | Reason |
|----------|--------|
| First question bypasses CustomerAgent | Anchor test baseline, ensure reproducibility |
| StopAgent confidence threshold 0.8 | Prevent hallucination from bypassing stop |
| LogFetcher called after conversation ends | Avoid disrupting conversation timing |
| EvalAgent stateless (no memory) | Independent scoring, no bias accumulation |
| Checkpoint by scanning existing files | No database needed, crash-safe |
| Case IDs stay as strings | Format `session_id_emp_id_yyyyMMdd`, int conversion breaks |
| All list fields via `format_list()` | Single processing entry, consistent formatting |

## 4. Configuration (config.py)

All variables via `Config` dataclass with env var fallback:
- LLM model/temperature/max_tokens per agent (CustomerAgent: 0.8 temp, StopAgent: 0.3, EvalAgent: 0.5)
- X7 API URL and credentials
- LogFetcher time buffer (2 minutes)
- Max conversation rounds (10)
- Stop confidence threshold (0.8)

## 5. Data Structures

### TestCase
- `序号`: str (format: `session_id_emp_id_yyyyMMdd`)
- `客户问题`: list[str] — [0] is first question, sent directly to X7
- `客户信息`: list[str] — background for CustomerAgent
- `会话特征`: list[str] — system prompt injection
- `参考答案`: list[str] — human-labeled ideal answers
- `判停规则`: list[str] — empty uses default rules
- `打分规则`: list[str] — three-tier scoring criteria
- `标注信息`: dict — metadata for reporting only

### DialogueTurn
- `round`: int
- `customer`: str
- `x7`: str
- `timestamp_customer`: str (ISO format)
- `timestamp_x7`: str
- `judge_stop`: bool

### RunResult
- `case_id`: str
- `conversation`: list[DialogueTurn]
- `stop_reason`: str
- `node_chain`: list[dict]
- `node_chain_text`: str (Markdown)
- `report`: dict
- `start_dt`: str
- `end_dt`: str

## 6. Agent Specifications

### CustomerAgent
- System prompt:扮演普通网络用户, not tech expert, only answer from injected background
- `get_first_question()`: returns `test_case.客户问题[0]` directly (no LLM call)
- `respond(x7_reply)`: appends x7_reply to history, calls LLM for follow-up question, returns question string

### X7Agent
- Generates UUID `session_id` on init (persisted for LogFetcher)
- `respond(user_input)`: POST to X7 API, return answer or error string (never raise)

### StopAgent
- Has memory (needs conversation context)
- `should_stop(conversation, stop_rules)`: returns `(bool, reason, detail)`
- Logic: if `len(conversation) >= max_rounds` → return True immediately (no LLM)
- Else call LLM for JSON: `{"should_stop": bool, "reason": str, "confidence": float}`
- If `should_stop=True` and `confidence < 0.8` → override to False
- JSON parse failure → return False

### EvalAgent
- Stateless (no memory)
- `evaluate(conversation, test_case, node_chain_text)`: returns dict
- With node_chain_text: evaluates routing, tool success, hallucination
- Without: notes "工具调用维度未获取到日志，默认满分" in report

## 7. LogFetcher

- Called after conversation ends (not during)
- Query window: start_time ± 2 minutes buffer
- Recursively parses nodes: type, name, status, rt, input (truncated 300 chars), output, error, subNodes
- Failures return `[]` (never raise)

## 8. ReportGenerator

- Output path: `{output_dir}/{dataset_name}/{dataset_name}_{序号}.md`
- Checkpoint: scan existing files, extract case IDs, skip completed
- Markdown structure per spec

## 9. Dependencies

```
openai>=1.0.0
requests>=2.31.0
python-dotenv>=1.0.0
pytest>=7.0.0
pytest-mock>=3.0.0
```

## 10. Verification

- All 4 agent modules load without import errors
- `pytest tests/` passes with mocked HTTP/LLM calls
- CLI: `python main.py --help` shows usage
- Checkpoint: re-running skips already-completed cases