from dataclasses import dataclass, field
from typing import Optional


def format_list(items: list) -> str:
    """
    统一处理 list 字段：单条直接返回字符串，多条加序号拼接。
    这是框架里所有 list 字段的唯一处理入口，不能在其他地方重复实现。
    """
    if not items:
        return ""
    if len(items) == 1:
        return str(items[0])
    return "\n".join(f"{i+1}. {item}" for i, item in enumerate(items))


@dataclass
class TestCase:
    序号: str                          # 唯一标识，格式 session_id_emp_id_yyyyMMdd
    客户问题: list[str]                 # [0] 是首问，直接发给 X7，不经 CustomerAgent
    客户信息: list[str]                 # 注入 CustomerAgent 的追问背景
    会话特征: list[str]                 # 注入 CustomerAgent 的 system prompt
    参考答案: list[str]                 # 人工标注的理想回答，用于评分基准
    判停规则: list[str]                 # 为空时 StopAgent 用默认规则
    打分规则: list[str]                 # 三档打分标准
    标注信息: dict                      # 元数据，只写报告，不参与对话流程


@dataclass
class DialogueTurn:
    round: int
    customer: str                      # 用户这轮说的话
    x7: str                            # X7 这轮的回答
    timestamp_customer: str            # ISO 格式时间
    timestamp_x7: str
    judge_stop: bool                   # StopAgent 这轮的判断结果


@dataclass
class RunResult:
    case_id: str
    conversation: list[DialogueTurn]
    stop_reason: str
    node_chain: list[dict]             # LogFetcher 拉回来的原始节点数据
    node_chain_text: str               # 格式化后的 Markdown 文本
    report: dict                       # EvalAgent 输出的评分 JSON
    start_dt: str
    end_dt: str