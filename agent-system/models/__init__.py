"""数据模型模块

定义核心数据结构。

说明：
- 为了提升 L3 strict_facts 的可复现性，本模块支持：
    - diff 多 hunk 元信息与 new_line -> diff_line 映射（用于定位到具体 hunk/行）
    - 结构化 evidence（file/line/range/snippet/hash）
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


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
    # 解析 diff 得到的 hunk 元信息（可选；旧数据不会带）
    diff_hunks: List[Dict[str, Any]] = field(default_factory=list)
    # new-file 行号 -> diff 内行号（1-based，相对本文件 diff block）
    new_line_to_diff_line: Dict[int, int] = field(default_factory=dict)


@dataclass
class EvidenceItem:
    """结构化证据：用于复盘与强校验。"""

    file_path: str = ""
    line_start: int = 0
    line_end: int = 0
    snippet: str = ""
    hash: str = ""
    # 可选：若能从 diff 映射定位到 diff 行号，则写入（便于定位具体 hunk/行）
    diff_line: int = 0


def _sha256_hex(text: str) -> str:
    b = (text or "").encode("utf-8", errors="ignore")
    return hashlib.sha256(b).hexdigest()


def normalize_evidence(
    raw_evidence: Any,
    *,
    default_file_path: str = "",
    default_line_number: int = 0,
) -> List[Dict[str, Any]]:
    """把 evidence 统一为结构化列表（dict 形态，便于 JSON 序列化）。

    兼容输入：
    - List[str]
    - List[dict]（字段不全也会补齐 hash）
    - None/其他：返回空列表
    """
    if not raw_evidence:
        return []

    if not isinstance(raw_evidence, list):
        return []

    out: List[Dict[str, Any]] = []
    for item in raw_evidence:
        if isinstance(item, str):
            snippet = item
            ev = EvidenceItem(
                file_path=default_file_path or "",
                line_start=int(default_line_number or 0),
                line_end=int(default_line_number or 0),
                snippet=snippet,
                hash=_sha256_hex((snippet or "").strip()),
                diff_line=0,
            )
            out.append(ev.__dict__)
            continue

        if isinstance(item, dict):
            snippet = str(item.get("snippet") or item.get("content") or "")
            file_path = str(item.get("file_path") or item.get("file") or default_file_path or "")
            line_start = item.get("line_start")
            line_end = item.get("line_end")
            # 兼容旧字段：line_number
            if (line_start is None or line_start == 0) and item.get("line_number"):
                line_start = item.get("line_number")
            if (line_end is None or line_end == 0) and line_start:
                line_end = line_start
            try:
                line_start_i = int(line_start or 0)
            except Exception:
                line_start_i = 0
            try:
                line_end_i = int(line_end or 0)
            except Exception:
                line_end_i = line_start_i

            diff_line = item.get("diff_line")
            try:
                diff_line_i = int(diff_line or 0)
            except Exception:
                diff_line_i = 0

            h = str(item.get("hash") or "")
            if not h:
                h = _sha256_hex((snippet or "").strip())

            ev = EvidenceItem(
                file_path=file_path,
                line_start=line_start_i,
                line_end=line_end_i,
                snippet=snippet,
                hash=h,
                diff_line=diff_line_i,
            )
            out.append(ev.__dict__)
            continue

        # 兜底：非预期类型转字符串
        snippet = str(item)
        ev = EvidenceItem(
            file_path=default_file_path or "",
            line_start=int(default_line_number or 0),
            line_end=int(default_line_number or 0),
            snippet=snippet,
            hash=_sha256_hex((snippet or "").strip()),
            diff_line=0,
        )
        out.append(ev.__dict__)

    return out


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
    # 结构化证据（推荐）：List[EvidenceItem(dict)]；兼容历史 List[str]
    evidence: List[Any] = field(default_factory=list)
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