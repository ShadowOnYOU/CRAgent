"""
数据模型模块
定义核心数据结构
"""
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from enum import Enum


class RiskLevel(Enum):
    """风险等级"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class FeedbackStatus(Enum):
    """反馈状态"""
    ACCEPT = "accept"
    IGNORE = "ignore"
    REJECT = "reject"


@dataclass
class CodeChange:
    """代码变更"""
    file_path: str
    old_content: str = ""
    new_content: str = ""
    diff: str = ""
    line_start: int = 0
    line_end: int = 0


@dataclass
class PR:
    """Pull Request 数据模型"""
    pr_id: str
    title: str
    description: str = ""
    author: str = ""
    changes: List[CodeChange] = field(default_factory=list)
    jira_ticket: str = ""
    commit_history: List[Dict[str, Any]] = field(default_factory=list)
    target_branch: str = "main"
    source_branch: str = ""


@dataclass
class ReviewIssue:
    """评审问题"""
    issue_type: str
    severity: RiskLevel
    message: str
    file_path: str
    line_number: int = 0
    evidence: List[str] = field(default_factory=list)
    suggestion: str = ""
    confidence: float = 0.8


@dataclass
class ReviewResult:
    """评审结果"""
    pr_id: str
    issues: List[ReviewIssue] = field(default_factory=list)
    summary: str = ""
    reasoning_trace: List[str] = field(default_factory=list)
    run_trace: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class Context:
    """上下文数据"""
    code_context: str = ""
    docs_context: str = ""
    checklist: List[str] = field(default_factory=list)
    related_files: List[str] = field(default_factory=list)


@dataclass
class ToolResult:
    """工具执行结果"""
    tool_name: str
    success: bool
    result: Any = None
    error: str = ""