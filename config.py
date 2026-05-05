import os
from dataclasses import dataclass


@dataclass
class Config:
    # ── LLM 模型配置 ──────────────────────────────────────────
    # 为什么三个 Agent 温度不同：
    # CustomerAgent 需要多样性（像真人），温度高
    # StopAgent 需要一致性（同样情况今天停、明天也停），温度低
    # EvalAgent 需要理解力但不能飘，温度居中
    customer_model: str = "qwen-plus"
    customer_temperature: float = 0.8
    customer_max_tokens: int = 1000

    stop_model: str = "qwen-plus"
    stop_temperature: float = 0.3
    stop_max_tokens: int = 500

    eval_model: str = "qwen-plus"
    eval_temperature: float = 0.5
    eval_max_tokens: int = 2000

    # ── Agent 记忆开关 ─────────────────────────────────────────
    # CustomerAgent 有记忆（需要记住上下文才能追问）
    # EvalAgent 无记忆（每次独立评分，避免偏差累积）
    customer_enable_memory: bool = True
    stop_enable_memory: bool = True
    eval_enable_memory: bool = False

    # ── X7 API 配置 ────────────────────────────────────────────
    x7_api_url: str = "https://x7-internal.example.com/api/chat"
    x7_emp_id: str = os.getenv("X7_EMP_ID", "test_user")
    x7_timeout: int = 90
    x7_rate_limit_seconds: int = 60    # X7 限流间隔，50个case约需1小时

    # ── LogFetcher 配置 ────────────────────────────────────────
    log_api_url: str = "https://x7-internal.example.com/api/logs"
    log_time_buffer_minutes: int = 2   # 查询时间窗口前后各扩 2 分钟

    # ── 对话控制 ───────────────────────────────────────────────
    max_rounds: int = 10               # 超过强制终止，模拟转人工
    stop_confidence_threshold: float = 0.8  # 低于此值的停止判断强制转为继续

    # ── 路径配置 ───────────────────────────────────────────────
    default_dataset_path: str = "datasets/example_dataset.json"
    output_dir: str = "outputs"

    # ── LLM API Key（从环境变量读） ────────────────────────────
    api_key: str = os.getenv("DASHSCOPE_API_KEY", "")
    api_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"