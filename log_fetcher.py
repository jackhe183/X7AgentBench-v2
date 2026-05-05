import requests
from typing import Optional

from config import Config


class LogFetcher:
    """
    X7 内部节点执行记录的拉取器。

    这是框架的灰盒探针，在对话全部结束后调用一次（不干扰对话时序）。
    日志系统有延迟，所以查询时间窗口会前后各扩展 2 分钟。
    """

    def __init__(self, config: Config):
        self.config = config

    def fetch_session_nodes(self, session_id: str,
                             start_time: str,
                             end_time: str) -> list[dict]:
        """
        查询时间窗口：start_time 前扩 2 分钟，end_time 后扩 2 分钟。
        POST 到日志接口，按 session_id 过滤。

        递归解析每个节点，提取字段：
        - type, name, status, rt（响应时间，毫秒）
        - input（超 300 字符截断，加 "...[已截断]"）
        - output（同上）
        - error（有则记录）
        - subNodes（递归处理）

        失败时返回 [] 不抛异常（日志拉不到不应该让整个测评崩溃）。
        """
        from datetime import datetime, timedelta

        # 计算扩展时间窗口
        buffer = timedelta(minutes=self.config.log_time_buffer_minutes)
        try:
            start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
            end_dt = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
        except ValueError:
            # 如果解析失败，尝试简单的时间格式
            try:
                start_dt = datetime.fromisoformat(start_time)
                end_dt = datetime.fromisoformat(end_time)
            except ValueError:
                return []

        expanded_start = (start_dt - buffer).isoformat()
        expanded_end = (end_dt + buffer).isoformat()

        payload = {
            "sessionId": session_id,
            "startTime": expanded_start,
            "endTime": expanded_end
        }

        try:
            response = requests.post(
                self.config.log_api_url,
                json=payload,
                timeout=30
            )
            if response.status_code == 200:
                data = response.json()
                nodes = data.get("data", {}).get("nodes", [])
                return self._parse_nodes(nodes)
            else:
                return []
        except Exception:
            # 任何异常都返回空列表，不让日志拉取失败影响测评流程
            return []

    def _parse_nodes(self, nodes: list[dict]) -> list[dict]:
        """递归解析节点列表。"""
        result = []
        for node in nodes:
            parsed = {
                "type": node.get("type", ""),
                "name": node.get("name", ""),
                "status": node.get("status", ""),
                "rt": node.get("rt", 0),
            }
            # 截断过长的 input/output
            input_text = node.get("input", "")
            if len(input_text) > 300:
                input_text = input_text[:300] + "...[已截断]"
            parsed["input"] = input_text

            output_text = node.get("output", "")
            if len(output_text) > 300:
                output_text = output_text[:300] + "...[已截断]"
            parsed["output"] = output_text

            if node.get("error"):
                parsed["error"] = node.get("error")

            # 递归处理子节点
            if node.get("subNodes"):
                parsed["subNodes"] = self._parse_nodes(node.get("subNodes"))

            result.append(parsed)
        return result

    def format_for_eval(self, nodes: list[dict]) -> str:
        """
        把节点列表格式化为 Markdown 文本，交给 EvalAgent 阅读。

        nodes 为空时返回固定字符串：
        "（未获取到节点调用数据，工具调用维度不参与扣分）"

        非空时格式示例：
        ## 节点调用链路
        - [SUCCESS] 意图识别 (rt: 234ms)
          - input: 我的机器访问公网域名不通
          - output: 意图=安全外联配置
        - [FAILED] SmartNAT查询工具 (rt: timeout)
          - error: 连接超时
        """
        if not nodes:
            return "（未获取到节点调用数据，工具调用维度不参与扣分）"

        lines = ["## 节点调用链路"]
        self._format_node_recursive(nodes, lines, indent=0)
        return "\n".join(lines)

    def _format_node_recursive(self, nodes: list[dict], lines: list, indent: int):
        """递归格式化节点到 lines 列表。"""
        for node in nodes:
            # 状态图标
            status = node.get("status", "").upper()
            if status == "SUCCESS" or status == "成功":
                status_icon = "SUCCESS"
            elif status == "FAILED" or status == "失败":
                status_icon = "FAILED"
            else:
                status_icon = status

            name = node.get("name", "unknown")
            rt = node.get("rt", 0)
            lines.append(f"{'  ' * indent}- [{status_icon}] {name} (rt: {rt}ms)")

            input_text = node.get("input", "")
            if input_text:
                lines.append(f"{'  ' * (indent+1)}- input: {input_text}")

            output_text = node.get("output", "")
            if output_text:
                lines.append(f"{'  ' * (indent+1)}- output: {output_text}")

            error = node.get("error", "")
            if error:
                lines.append(f"{'  ' * (indent+1)}- error: {error}")

            # 递归处理子节点
            sub_nodes = node.get("subNodes", [])
            if sub_nodes:
                self._format_node_recursive(sub_nodes, lines, indent + 1)