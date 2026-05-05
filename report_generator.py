import os
import re
from pathlib import Path

from data_structures import RunResult


class ReportGenerator:
    """
    将每个测试用例的结果保存为 Markdown 文件，并实现断点续传。

    断点续传的原理：扫描输出目录里已有的文件，提取文件名里的序号，跳过已完成的 case。
    序号全程保持字符串格式，不转 int（序号含下划线，int 转换会出错）。
    """

    def __init__(self, config):
        self.config = config

    def get_completed_case_ids(self, dataset_name: str) -> set[str]:
        """
        扫描输出目录，提取已完成的 case ID 集合（用于断点续传）。
        """
        output_path = Path(self.config.output_dir) / dataset_name
        if not output_path.exists():
            return set()

        completed = set()
        prefix = f"{dataset_name}_"
        suffix = ".md"

        for file in output_path.iterdir():
            if file.suffix == suffix and file.name.startswith(prefix):
                # 提取序号部分：{dataset_name}_{序号}.md
                case_id = file.name[len(prefix):-len(suffix)]
                completed.add(case_id)

        return completed

    def generate_report(self, result: RunResult, dataset_name: str) -> str:
        """
        生成 Markdown 格式的测评报告并保存到文件。

        返回保存的文件路径。
        """
        # 确保输出目录存在
        output_path = Path(self.config.output_dir) / dataset_name
        output_path.mkdir(parents=True, exist_ok=True)

        # 文件名：{dataset_name}_{序号}.md
        filename = f"{dataset_name}_{result.case_id}.md"
        file_path = output_path / filename

        # 格式化对话过程
        conversation_lines = []
        for turn in result.conversation:
            conversation_lines.append(f"### 第 {turn.round} 轮")
            conversation_lines.append(f"**用户**：{turn.customer}")
            conversation_lines.append(f"**X7**：{turn.x7}")
            conversation_lines.append("")

        conversation_text = "\n".join(conversation_lines)

        # 格式化问题点
        problem_points = result.report.get("问题点", [])
        if problem_points:
            problem_points_text = "\n".join(f"- {p}" for p in problem_points)
        else:
            problem_points_text = "无"

        # 标注信息
        annotation = result.case_id  # 序号
        # 从 case_id 解析标注信息（如果有的话）
        # 这里只是示例，实际上标注信息应该从 RunResult 里取
        # 但 RunResult 里没有完整存储 test_case，我们只存了 case_id

        # 构建 Markdown
        markdown = f"""# 测评报告：{result.case_id}

## 基本信息
- 数据集：{dataset_name}
- 测试时间：{result.start_dt} ~ {result.end_dt}
- 对话轮数：{len(result.conversation)}
- 终止原因：{result.stop_reason}

## 评分结果
- **总分：{result.report.get("总分", 0)} / 10**
- 对话质量分：{result.report.get("对话质量分", 0)} / 6
- 工具调用分：{result.report.get("工具调用分", 0)} / 4
- 评语：{result.report.get("评语", "")}
- 问题点：
{problem_points_text}

## 对话过程
{conversation_text}

## 节点调用链路
{result.node_chain_text}

## 标注信息存档（仅供分层分析，不参与评分）
- 序号：{result.case_id}
"""

        # 写入文件
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(markdown)

        return str(file_path)