"""
LLM 服务模块
封装阿里云百炼 API 调用
"""
from .client import LLMClient

__all__ = ["LLMClient"]