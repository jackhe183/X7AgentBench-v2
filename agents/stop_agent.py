from typing import Optional
import json

from openai import OpenAI

from config import Config
from data_structures import DialogueTurn, TestCase
from data_structures import format_list


DEFAULT_STOP_RULES = [
    '用户明确说"谢谢"且无新问题',
    '用户要求转人工',
    'X7 明确无法处理当前问题',
]


class StopAgent:
    """
    判断对话是否应该终止。

    需要记忆，因为它要看整段对话的走势。
    置信度阈值是一道保险——不只要说"停"，要确信地说"停"。
    """

    def __init__(self, config: Config):
        self.config = config
        self._history: list[dict] = []

    def should_stop(self, conversation: list[DialogueTurn],
                    stop_rules: list[str]) -> tuple[bool, str, str]:
        """
        返回 (should_stop: bool, reason: str, detail: str) 三元组。

        判断逻辑（按优先级）：
        1. 如果 len(conversation) >= config.max_rounds：直接返回 (True, "超过最大轮数", "")，不调模型
        2. 调用 LLM，要求输出纯 JSON：
           {{"should_stop": bool, "reason": str, "confidence": float}}
        3. 如果 should_stop=True 且 confidence < 0.8：强制改为 (False, "置信度不足", detail)
        4. JSON 解析失败：保守返回 (False, "解析失败", "")

        system prompt 里注入判停规则和默认规则。
        """
        # 规则1：超过最大轮数，直接终止，不调模型
        if len(conversation) >= self.config.max_rounds:
            return (True, "超过最大轮数", "")

        # 构建 system prompt
        rules_text = format_list(stop_rules) if stop_rules else format_list(DEFAULT_STOP_RULES)
        system_prompt = f"""你是一个对话终止判断专家。

【判停规则】
{rules_text}

【判断要求】
- 用户说"好的谢谢"意味着问题已解决，应该停止
- 用户说"转人工"意味着需要人工介入，应该停止
- X7 明确说"无法处理"意味着需要升级，应该停止
- 仅泛泛地说"好的"但没有明确解决不要停止
- 每次判断必须输出置信度，低于 0.8 的判断会被强制转为继续

【输出格式】
输出纯 JSON，不要 markdown 代码块：
{{"should_stop": bool, "reason": str, "confidence": float}}

confidence 范围 0-1，表示你对这个判断的确信程度。
"""

        # 构建用户消息：把对话历史传进去
        user_message = self._build_conversation_text(conversation)

        # 调用 LLM
        client = OpenAI(api_key=self.config.api_key, base_url=self.config.api_base_url)
        response = client.chat.completions.create(
            model=self.config.stop_model,
            temperature=self.config.stop_temperature,
            max_tokens=self.config.stop_max_tokens,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ]
        )

        raw_content = response.choices[0].message.content.strip()

        # 尝试解析 JSON
        try:
            # 去掉可能的 markdown 代码块
            if raw_content.startswith("```"):
                raw_content = raw_content.split("```")[1]
                raw_content = raw_content.lstrip("json\n")
            result = json.loads(raw_content)
            should_stop = result.get("should_stop", False)
            reason = result.get("reason", "")
            confidence = result.get("confidence", 0.0)

            # 规则3：置信度低于阈值，强制转为继续
            if should_stop and confidence < self.config.stop_confidence_threshold:
                return (False, "置信度不足", f"confidence={confidence} < {self.config.stop_confidence_threshold}")

            return (should_stop, reason, f"confidence={confidence}")
        except (json.JSONDecodeError, KeyError) as e:
            return (False, "解析失败", str(e))

    def _build_conversation_text(self, conversation: list[DialogueTurn]) -> str:
        """把对话历史格式化成文本发给 LLM。"""
        lines = []
        for turn in conversation:
            lines.append(f"用户：{turn.customer}")
            lines.append(f"X7：{turn.x7}")
        return "\n".join(lines)