"""自定义异常类型"""


class PipelineError(Exception):
    """管线处理异常"""
    pass


class ASRError(PipelineError):
    """ASR 引擎异常"""
    pass


class NMTError(PipelineError):
    """翻译引擎异常。

    Attributes:
        status_code: 上游 HTTP 状态码（如有），用于判断是否值得重试。
    """

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class ContextError(PipelineError):
    """上下文管理异常"""
    pass