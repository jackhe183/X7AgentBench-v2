import pytest
from unittest.mock import MagicMock, patch

from config import Config
from data_structures import DialogueTurn
from agents.stop_agent import StopAgent


class TestStopAgent:
    """StopAgent 测试套件。"""

    @pytest.fixture
    def config(self):
        c = Config()
        c.stop_model = "qwen-plus"
        c.stop_temperature = 0.3
        c.stop_max_tokens = 500
        c.max_rounds = 10
        c.stop_confidence_threshold = 0.8
        c.api_key = "test-key"
        c.api_base_url = "https://test.example.com"
        return c

    @pytest.fixture
    def stop_agent(self, config):
        return StopAgent(config)

    def test_should_stop_with_high_confidence(self, stop_agent, config):
        """正常停止（confidence=0.9）→ 返回 True"""
        conversation = [
            DialogueTurn(1, "你好", "您好", "", "", False),
            DialogueTurn(2, "好的谢谢", "不客气", "", "", False),
        ]

        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content='{"should_stop": true, "reason": "用户说谢谢", "confidence": 0.9}'))]

        with patch('agents.stop_agent.OpenAI') as MockOpenAI:
            mock_client = MagicMock()
            MockOpenAI.return_value = mock_client
            mock_client.chat.completions.create.return_value = mock_response

            should_stop, reason, detail = stop_agent.should_stop(conversation, [])

        assert should_stop is True
        assert "置信度" not in reason  # 不是因为置信度不足

    def test_should_stop_with_low_confidence_forced_continue(self, stop_agent, config):
        """低置信度停止（confidence=0.6）→ 强制转为 False"""
        conversation = [
            DialogueTurn(1, "你好", "您好", "", "", False),
        ]

        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content='{"should_stop": true, "reason": "看起来解决了", "confidence": 0.6}'))]

        with patch('agents.stop_agent.OpenAI') as MockOpenAI:
            mock_client = MagicMock()
            MockOpenAI.return_value = mock_client
            mock_client.chat.completions.create.return_value = mock_response

            should_stop, reason, detail = stop_agent.should_stop(conversation, [])

        # 置信度 0.6 < 0.8，应该强制转为继续
        assert should_stop is False
        assert "置信度不足" in reason

    def test_max_rounds_exceeded_bypasses_llm(self, stop_agent, config):
        """超过 max_rounds → 直接返回 True，不调模型"""
        conversation = [
            DialogueTurn(i, f"问题{i}", f"回答{i}", "", "", False)
            for i in range(1, 11)  # 10 轮对话，达到 max_rounds
        ]

        with patch('agents.stop_agent.OpenAI') as MockOpenAI:
            mock_client = MagicMock()
            MockOpenAI.return_value = mock_client
            # 如果调用了 LLM，会返回正常的 response，但这里不应该调用

            should_stop, reason, detail = stop_agent.should_stop(conversation, [])

        assert should_stop is True
        assert "超过最大轮数" in reason
        # 验证 LLM 未被调用
        MockOpenAI.assert_not_called()

    def test_json_parse_failure_returns_false(self, stop_agent, config):
        """JSON 解析失败 → 返回 False"""
        conversation = [
            DialogueTurn(1, "你好", "您好", "", "", False),
        ]

        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content='这不是 JSON 格式的响应'))]

        with patch('agents.stop_agent.OpenAI') as MockOpenAI:
            mock_client = MagicMock()
            MockOpenAI.return_value = mock_client
            mock_client.chat.completions.create.return_value = mock_response

            should_stop, reason, detail = stop_agent.should_stop(conversation, [])

        assert should_stop is False
        assert "解析失败" in reason