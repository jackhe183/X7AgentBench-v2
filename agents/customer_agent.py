from typing import Optional

from openai import OpenAI

from config import Config
from data_structures import TestCase, DialogueTurn
from data_structures import format_list


class CustomerAgent:
    """
    模拟真实用户的追问行为。

    它不是全知全能的，只是一个普通用户，只能从被注入的"客户信息"里取信息被动回答。
    首问不经过它（直接发给 X7），保证测试起点稳定可复现。
    """

    def __init__(self, test_case: TestCase, config: Config):
        """
        初始化时构建完整 system prompt 并将首问注入 history。
        history 格式遵循 OpenAI 兼容接口：[{"role": ..., "content": ...}]
        """
        self.test_case = test_case
        self.config = config
        self._history: list[dict] = [
            {"role": "system", "content": self._build_system_prompt()}
        ]

        # 注入首问（直接来自测试数据，不经过 LLM 改写）
        first_q = test_case.客户问题[0]
        self._history.append({"role": "user", "content": first_q})

    def _build_system_prompt(self) -> str:
        """构建 system prompt，注入客户信息和会话特征。"""
        return f"""你是一个普通的网络产品用户，不是网络专家。你遇到了一个问题需要找客服解决。

【你的问题背景】
{format_list(self.test_case.客户信息)}

【你的会话特点】
{format_list(self.test_case.会话特征)}

【行为约束】
- 你不主动提供信息，只有当客服询问时才从你的背景信息里取内容回答
- 每次只问或回答一个问题，不超过 20 个字
- 当你的问题被完整解决时，回复"好的谢谢"并停止追问
- 你不懂技术术语，如果客服用了你不理解的术语，要求对方解释
- 不要暴露你知道"参考答案"，你只是一个普通用户"""

    def get_first_question(self) -> str:
        """
        直接返回 test_case.客户问题[0]，不调用模型。
        这是设计上的关键约束，不能改成调用 LLM。
        """
        return self.test_case.客户问题[0]

    def respond(self, x7_reply: str) -> str:
        """
        1. 将 x7_reply 追加为 {{"role": "assistant", "content": x7_reply}}
        2. 调用 LLM 生成追问
        3. 将追问追加为 {{"role": "user", "content": 追问}}
        4. 返回追问字符串
        """
        # 追加 X7 的回复到历史
        self._history.append({"role": "assistant", "content": x7_reply})

        # 调用 LLM 生成追问
        client = OpenAI(api_key=self.config.api_key, base_url=self.config.api_base_url)
        response = client.chat.completions.create(
            model=self.config.customer_model,
            temperature=self.config.customer_temperature,
            max_tokens=self.config.customer_max_tokens,
            messages=self._history
        )
        follow_up = response.choices[0].message.content.strip()

        # 追加到历史
        self._history.append({"role": "user", "content": follow_up})

        return follow_up

    @property
    def history(self) -> list[dict]:
        """返回对话历史（供调试用）。"""
        return self._history.copy()