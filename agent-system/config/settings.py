"""
配置管理模块
"""
import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class LLMConfig:
    """LLM 配置"""
    api_key: str = os.getenv("DASHSCOPE_API_KEY", "")
    base_url: str = "https://coding.dashscope.aliyuncs.com/v1"
    model: str = "qwen3-coder-next"
    max_tokens: int = 4096
    temperature: float = 0.7


@dataclass
class VectorDBConfig:
    """向量数据库配置"""
    db_path: str = "./data/vector_db"
    embedding_model: str = "text-embedding-v2"


@dataclass
class ReviewConfig:
    """评审配置"""
    max_context_tokens: int = 8000
    min_confidence: float = 0.6
    enable_tool_augmented: bool = True
    enable_checklist: bool = True
    checklist_path: str = "./config/checklist.json"


@dataclass
class AppConfig:
    """应用配置"""
    llm: LLMConfig = None  # type: ignore
    vector_db: VectorDBConfig = None  # type: ignore
    review: ReviewConfig = None  # type: ignore
    
    def __post_init__(self):
        if self.llm is None:
            self.llm = LLMConfig()
        if self.vector_db is None:
            self.vector_db = VectorDBConfig()
        if self.review is None:
            self.review = ReviewConfig()


# 全局配置实例
config = AppConfig()