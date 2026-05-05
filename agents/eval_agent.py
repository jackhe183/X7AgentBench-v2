import json

from openai import OpenAI

from config import Config
from data_structures import DialogueTurn, TestCase
from data_structures import format_list


class EvalAgent:
    """
    对整段对话进行最终评分。

    无记忆，每次独立评估，避免累积偏差。
    """

    def __init__(self, config: Config):
        self.config = config

    def evaluate(self, conversation: list[DialogueTurn],
                 test_case: TestCase,
                 node_chain_text: str) -> dict:
        """
        把完整对话格式化为文本塞进 user message，调用 LLM 打分。

        期望 LLM 输出纯 JSON（system prompt 强调，不要输出 markdown 代码块）：
        {{
          "总分": int,          # 0-10
          "对话质量分": int,    # 0-6，基于对话过程
          "工具调用分": int,    # 0-4，基于节点日志（无日志时给 4）
          "评语": str,
          "工具调用分析": str,  # 无日志时填"未获取到节点数据"
          "问题点": [str]       # 具体指出哪些地方有问题
        }}

        JSON 解析失败时返回 {{"总分": 0, "评语": "评分解析失败", "问题点": []}}
        """
        system_prompt = """你是一个专业的 AI 对话质量评估专家。

【评分维度】
- 对话质量分（0-6）：基于对话过程，考察回答是否准确、是否有帮助、是否解决了用户问题
- 工具调用分（0-4）：基于节点日志，考察是否路由到正确的子 Agent、工具是否成功返回、是否有幻觉

【评分标准】
- 总分 9-10：优秀，问题完全解决，有工具调用且成功
- 总分 6-8：及格，问题基本解决或有明显改进空间
- 总分 0-5：不及格，问题未解决或回答严重偏离

【特别说明】
- 无节点日志时，工具调用分默认给满分 4，因为无法判定
- "工具调用分析"字段：无日志时填"未获取到节点数据，工具调用维度不参与扣分"

【输出格式】
输出纯 JSON，不要 markdown 代码块，不要有任何其他内容：
{{"总分": int, "对话质量分": int, "工具调用分": int, "评语": str, "工具调用分析": str, "问题点": [str]}}
"""

        user_message = self._build_evaluation_prompt(conversation, test_case, node_chain_text)

        client = OpenAI(api_key=self.config.api_key, base_url=self.config.api_base_url)
        response = client.chat.completions.create(
            model=self.config.eval_model,
            temperature=self.config.eval_temperature,
            max_tokens=self.config.eval_max_tokens,
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
            # 确保字段完整
            return {
                "总分": result.get("总分", 0),
                "对话质量分": result.get("对话质量分", 0),
                "工具调用分": result.get("工具调用分", 4),  # 无日志默认 4
                "评语": result.get("评语", ""),
                "工具调用分析": result.get("工具调用分析", "未获取到节点数据"),
                "问题点": result.get("问题点", [])
            }
        except (json.JSONDecodeError, KeyError) as e:
            return {
                "总分": 0,
                "评语": f"评分解析失败: {str(e)}",
                "对话质量分": 0,
                "工具调用分": 4,
                "工具调用分析": "未获取到节点数据",
                "问题点": [f"LLM 输出解析失败: {raw_content[:200]}"]
            }

    def _build_evaluation_prompt(self, conversation: list[DialogueTurn],
                                  test_case: TestCase,
                                  node_chain_text: str) -> str:
        """构建完整的评估 prompt。"""
        lines = ["【测试用例信息】"]
        lines.append(f"序号：{test_case.序号}")
        lines.append(f"客户问题：{format_list(test_case.客户问题)}")
        lines.append(f"参考答案：{format_list(test_case.参考答案)}")
        lines.append(f"打分规则：{format_list(test_case.打分规则)}")
        lines.append("\n【对话过程】")
        for turn in conversation:
            lines.append(f"第 {turn.round} 轮：")
            lines.append(f"  用户：{turn.customer}")
            lines.append(f"  X7：{turn.x7}")
        lines.append("\n【节点调用链路】")
        lines.append(node_chain_text if node_chain_text else "（未获取到节点调用数据，工具调用维度不参与扣分）")
        return "\n".join(lines)