import time
from datetime import datetime

from config import Config
from data_structures import TestCase, DialogueTurn, RunResult
from agents.customer_agent import CustomerAgent
from agents.x7_agent import X7Agent
from agents.stop_agent import StopAgent
from agents.eval_agent import EvalAgent
from log_fetcher import LogFetcher


class DialogueRunner:
    """
    驱动一个完整测试用例的对话流程。

    这是整个框架的主编排器。
    """

    def __init__(self, config: Config):
        self.config = config
        self.log_fetcher = LogFetcher(config)

    def run(self, test_case: TestCase) -> RunResult:
        """
        完整流程如下（严格按顺序）：

        1. 记录 start_dt（ISO 格式）
        2. 初始化 CustomerAgent、X7Agent、StopAgent、EvalAgent
        3. 第 1 轮：
           - customer = CustomerAgent.get_first_question()（不调模型）
           - x7_reply = X7Agent.respond(customer)
           - stop, reason, detail = StopAgent.should_stop(conversation, 判停规则)
           - 记录 DialogueTurn
        4. 第 2 轮起：
           - customer = CustomerAgent.respond(上轮 x7_reply)
           - x7_reply = X7Agent.respond(customer)
           - stop, reason, detail = StopAgent.should_stop(...)
           - 记录 DialogueTurn
           - 如果 stop=True，退出循环
        5. 记录 end_dt
        6. node_chain = LogFetcher.fetch_session_nodes(x7.session_id, start_dt, end_dt)
        7. node_chain_text = LogFetcher.format_for_eval(node_chain)
        8. report = EvalAgent.evaluate(conversation, test_case, node_chain_text)
        9. 返回 RunResult

        注意：X7 有限流（60秒间隔），在 X7Agent.respond 后 sleep(config.x7_rate_limit_seconds)
        """
        start_dt = datetime.now().isoformat()

        # 初始化所有 Agent
        customer_agent = CustomerAgent(test_case, self.config)
        x7_agent = X7Agent(self.config)
        stop_agent = StopAgent(self.config)
        eval_agent = EvalAgent(self.config)

        conversation: list[DialogueTurn] = []
        stop_reason = ""
        round_num = 0

        while True:
            round_num += 1

            if round_num == 1:
                # 第 1 轮：首问不经过 CustomerAgent
                customer_input = customer_agent.get_first_question()
            else:
                # 第 2 轮起：CustomerAgent.respond() 会调 LLM 生成追问
                customer_input = customer_agent.respond(x7_reply)

            timestamp_customer = datetime.now().isoformat()

            # 发给 X7
            x7_reply = x7_agent.respond(customer_input)

            # X7 限流：每调用一次休息 rate_limit_seconds
            time.sleep(self.config.x7_rate_limit_seconds)

            timestamp_x7 = datetime.now().isoformat()

            # 判断是否停止
            stop, reason, detail = stop_agent.should_stop(conversation, test_case.判停规则)
            if stop:
                stop_reason = reason
                break

            # 记录本轮对话
            turn = DialogueTurn(
                round=round_num,
                customer=customer_input,
                x7=x7_reply,
                timestamp_customer=timestamp_customer,
                timestamp_x7=timestamp_x7,
                judge_stop=stop
            )
            conversation.append(turn)

        end_dt = datetime.now().isoformat()

        # 对话结束后拉取节点日志
        node_chain = self.log_fetcher.fetch_session_nodes(
            x7_agent.session_id, start_dt, end_dt
        )
        node_chain_text = self.log_fetcher.format_for_eval(node_chain)

        # 评分
        report = eval_agent.evaluate(conversation, test_case, node_chain_text)

        # 构造最终结果
        return RunResult(
            case_id=test_case.序号,
            conversation=conversation,
            stop_reason=stop_reason,
            node_chain=node_chain,
            node_chain_text=node_chain_text,
            report=report,
            start_dt=start_dt,
            end_dt=end_dt
        )