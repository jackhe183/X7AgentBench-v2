import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
import tempfile
import os

from config import Config
from data_structures import RunResult, DialogueTurn
from report_generator import ReportGenerator


class TestReportGenerator:
    """ReportGenerator 测试套件。"""

    @pytest.fixture
    def config(self):
        c = Config()
        c.output_dir = tempfile.mkdtemp()
        return c

    @pytest.fixture
    def report_gen(self, config):
        return ReportGenerator(config)

    @pytest.fixture
    def sample_result(self):
        start_dt = "2025-01-26T10:00:00"
        end_dt = "2025-01-26T10:05:00"
        return RunResult(
            case_id="test_001_session_emp01",
            conversation=[
                DialogueTurn(1, "问题", "回答", start_dt, end_dt, False),
            ],
            stop_reason="用户满意",
            node_chain=[],
            node_chain_text="（无节点数据）",
            report={
                "总分": 8,
                "对话质量分": 5,
                "工具调用分": 3,
                "评语": "测试评语",
                "工具调用分析": "无日志",
                "问题点": []
            },
            start_dt=start_dt,
            end_dt=end_dt
        )

    def test_checkpoint_skips_completed_cases(self, report_gen, config):
        """断点续传：已完成的 case 不重复运行"""
        dataset_name = "test_dataset"
        output_path = Path(config.output_dir) / dataset_name
        output_path.mkdir(parents=True, exist_ok=True)

        # 创建一些已完成的报告文件
        (output_path / "test_dataset_case_001.md").touch()
        (output_path / "test_dataset_case_002.md").touch()

        completed = report_gen.get_completed_case_ids(dataset_name)

        assert "case_001" in completed
        assert "case_002" in completed
        assert len(completed) == 2

    def test_case_id_stays_as_string_not_int(self, report_gen, config):
        """序号保持字符串格式（不转 int）"""
        dataset_name = "test_dataset"
        output_path = Path(config.output_dir) / dataset_name
        output_path.mkdir(parents=True, exist_ok=True)

        # 文件名包含下划线的序号
        (output_path / "test_dataset_session_emp_12345_20250126.md").touch()

        completed = report_gen.get_completed_case_ids(dataset_name)

        # 验证序号保持字符串格式，没有被转成 int
        assert "session_emp_12345_20250126" in completed
        # 如果错误地转成 int，"session_emp_12345_20250126" 会出错
        assert len(completed) == 1

    def test_output_directory_auto_creation(self, report_gen, config):
        """输出目录不存在时自动创建"""
        dataset_name = "new_dataset"
        output_path = Path(config.output_dir) / dataset_name

        # 确保目录不存在
        assert not output_path.exists()

        # generate_report 应该自动创建目录
        with patch('report_generator.RunResult') as MockResult:
            mock_result = MagicMock()
            mock_result.case_id = "case_001"
            mock_result.report = {"总分": 8}
            mock_result.conversation = []
            mock_result.start_dt = ""
            mock_result.end_dt = ""
            mock_result.stop_reason = ""
            mock_result.node_chain_text = ""

            # 直接调用报告生成
            report_gen.generate_report(mock_result, dataset_name)

        assert output_path.exists()

    def test_generate_report_creates_valid_markdown(self, report_gen, config, sample_result):
        """报告生成创建有效的 Markdown 文件"""
        dataset_name = "test_dataset"

        with patch('report_generator.RunResult') as MockResult:
            mock_result = MagicMock()
            mock_result.case_id = "case_001"
            mock_result.report = {
                "总分": 8,
                "对话质量分": 5,
                "工具调用分": 3,
                "评语": "测试评语",
                "工具调用分析": "无日志",
                "问题点": []
            }
            mock_result.conversation = [
                DialogueTurn(1, "问题", "回答", "2025-01-26T10:00:00", "2025-01-26T10:01:00", False),
            ]
            mock_result.start_dt = "2025-01-26T10:00:00"
            mock_result.end_dt = "2025-01-26T10:05:00"
            mock_result.stop_reason = "用户满意"
            mock_result.node_chain_text = "（无节点数据）"

            file_path = report_gen.generate_report(mock_result, dataset_name)

        assert Path(file_path).exists()
        content = Path(file_path).read_text(encoding="utf-8")
        assert "# 测评报告：" in content
        assert "总分：8 / 10" in content
        assert "test_dataset_case_001.md" in file_path