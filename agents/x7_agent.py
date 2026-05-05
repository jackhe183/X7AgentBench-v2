import uuid
import requests

from config import Config


class X7Agent:
    """
    X7 API 的 HTTP 封装。

    职责：把请求发过去、把回答拿回来，本身没有任何业务逻辑。
    每次实例化生成一个 UUID 作为 session_id，全程持久化，LogFetcher 依赖它。
    HTTP 失败时返回错误字符串而不是抛异常，这样对话 loop 可以继续处理。
    """

    def __init__(self, config: Config):
        self.session_id = str(uuid.uuid4())  # 全程唯一，LogFetcher 依赖它
        self.config = config

    def respond(self, user_input: str) -> str:
        """
        POST 到 X7 API。

        payload = {
            "empId": config.x7_emp_id,
            "question": user_input,
            "sessionId": self.session_id,
            "stream": False
        }

        成功：返回 response.json()["data"]["answer"] 或类似字段
        失败：返回 "[X7接口错误: {status_code} / {error_msg}]"（不抛异常）
        超时：返回 "[X7请求超时]"
        """
        payload = {
            "empId": self.config.x7_emp_id,
            "question": user_input,
            "sessionId": self.session_id,
            "stream": False
        }

        try:
            response = requests.post(
                self.config.x7_api_url,
                json=payload,
                timeout=self.config.x7_timeout
            )
            if response.status_code == 200:
                data = response.json()
                # 尝试多种可能的响应格式
                if data.get("success") is False:
                    error_msg = data.get("error", "unknown error")
                    return f"[X7接口错误: success=False / {error_msg}]"
                # 通用提取逻辑
                answer = (
                    data.get("data", {}).get("answer")
                    or data.get("answer")
                    or data.get("result")
                )
                if answer:
                    return str(answer)
                return f"[X7接口错误: 未找到answer字段 / {data}]"
            else:
                return f"[X7接口错误: {response.status_code} / {response.text[:200]}]"
        except requests.exceptions.Timeout:
            return "[X7请求超时]"
        except requests.exceptions.RequestException as e:
            return f"[X7接口错误: {type(e).__name__} / {str(e)[:100]}]"