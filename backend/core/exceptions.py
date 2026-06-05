"""自定义异常类型"""


class PipelineError(Exception):
    """管线处理异常"""
    pass


class ASRError(PipelineError):
    """ASR 引擎异常"""
    pass


class NMTError(PipelineError):
    """翻译引擎异常"""
    pass


class ContextError(PipelineError):
    """上下文管理异常"""
    pass