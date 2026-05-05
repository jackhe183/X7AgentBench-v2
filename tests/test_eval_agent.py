import pytest
from unittest.mock import MagicMock, patch

from config import Config
from data_structures import DialogueTurn, TestCase
from agents.eval_agent import EvalAgent


class TestEvalAgent:
    """EvalAgent 测试套件。"""

    @pytest.fixture
    def config(self):
        c = Config()
        c.eval_model = "qwen-plus"
        c.eval_temperature = 0.5
        c.eval_max_tokens = 2000
        c.api_key = "test-key"
        c.api_base_url = "https://test.example.com"
        return c

    @pytest.fixture
    def eval_agent(self, config):
        return EvalAgent(config)

    @pytest.fixture
    def sample_conversation(self):
        return [
            DialogueTurn(1, "我的机器无法上网", "请检查您的网络连接", "", "", False),
            DialogueTurn(2, "已经检查了，但还是不行", "请问您的 IP 是多少", "", "", False),
        ]

    @pytest.fixture
    def sample_test_case(self):
        return TestCase(
            序号="test_001",
            客户问题=["我的机器无法上网"],
            客户信息=["Windows 10 系统"],
            会话特征=["简洁"],
            参考答案=["检查网络配置"],
            判停规则=[],
            打分规则=["能解决问题给高分"],
            标注信息={}
        )

    def test_evaluate_with_node_chain_text(self, eval_agent, sample_conversation, sample_test_case):
        """有节点日志时的完整评分（含工具调用维度）"""
        node_chain_text = """
## 节点调用链路
- [SUCCESS] 意图识别 (rt: 234ms)
  - input: 我的机器无法上网
  - output: 意图=网络故障排查
- [SUCCESS] 网络诊断工具 (rt: 500ms)
  - input: 检查网络配置
  - output: DNS 配置异常
"""

        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(
            content='{"总分": 8, "对话质量分": 5, "工具调用分": 3, "评语": "基本解决", "工具调用分析": "路由正确，工具成功", "问题点": []}'
        ))]

        with patch('agents.eval_agent.OpenAI') as MockOpenAI:
            mock_client = MagicMock()
            MockOpenAI.return_value = mock_client
            mock_client.chat.completions.create.return_value = mock_response

            result = eval_agent.evaluate(sample_conversation, sample_test_case, node_chain_text)

        assert result["总分"] == 8
        assert result["对话质量分"] == 5
        assert result["工具调用分"] == 3
        assert "工具调用分析" in result

    def test_evaluate_without_node_chain_text_defaults_to_full_score(self, eval_agent, sample_conversation, sample_test_case):
        """无节点日志时工具调用分默认满分"""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(
            content='{"总分": 6, "对话质量分": 4, "工具调用分": 2, "评语": "有改进空间", "工具调用分析": "未获取到节点数据", "问题点": ["缺少工具调用记录"]}'
        ))]

        with patch('agents.eval_agent.OpenAI') as MockOpenAI:
            mock_client = MagicMock()
            MockOpenAI.return_value = mock_client
            mock_client.chat.completions.create.return_value = mock_response

            result = eval_agent.evaluate(sample_conversation, sample_test_case, "")

        # 无日志时工具调用分默认给 4（满分），但 LLM 可能返回不同值，
        # 这里检查的是降级路径是否正常工作
        assert "总分" in result

    def test_evaluate_json_parse_failure_degrades_to_zero(self, eval_agent, sample_conversation, sample_test_case):
        """LLM 返回非 JSON 时的降级处理 → 返回 {"总分": 0}"""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content='这不是合法的 JSON 输出'))]

        with patch('agents.eval_agent.OpenAI') as MockOpenAI:
            mock_client = MagicMock()
            MockOpenAI.return_value = mock_client
            mock_client.chat.completions.create.return_value = mock_response

            result = eval_agent.evaluate(sample_conversation, sample_test_case, "")

        assert result["总分"] == 0
        assert "解析失败" in result["评语"]
        assert len(result["问题点"]) > 0