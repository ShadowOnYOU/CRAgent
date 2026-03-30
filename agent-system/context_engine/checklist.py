from __future__ import annotations

import json
import os
from dataclasses import replace
from typing import List, Optional

from models import Context, PR


DEFAULT_CHECKLIST: List[str] = [
    "必须判空（避免 None/空指针 解引用）",
    "并发访问共享资源必须加锁或使用原子操作",
    "错误处理必须覆盖失败路径（不要静默吞错）",
]


def _parse_checklist_text(text: str) -> List[str]:
    items: List[str] = []
    for raw in (text or "").splitlines():
        s = raw.strip()
        if not s:
            continue
        if s.startswith("#"):
            continue
        # 支持常见的 markdown 列表
        if s.startswith("-"):
            s = s[1:].strip()
        if not s:
            continue
        items.append(s)

    # 去重（保序）
    seen = set()
    out: List[str] = []
    for it in items:
        key = it.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(it.strip())
    return out


def load_checklist(checklist_path: Optional[str]) -> List[str]:
    """加载 checklist。

    - .json: 期望为 JSON 数组（元素为字符串）
    - 其他: 按文本逐行解析（支持 '-' 列表）

    失败时返回 DEFAULT_CHECKLIST。
    """
    if not checklist_path:
        return DEFAULT_CHECKLIST.copy()

    try:
        with open(checklist_path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()

        if checklist_path.lower().endswith(".json"):
            data = json.loads(text)
            if isinstance(data, list):
                items = [str(x).strip() for x in data if str(x).strip()]
                return _parse_checklist_text("\n".join(items))

        items = _parse_checklist_text(text)
        return items if items else DEFAULT_CHECKLIST.copy()
    except Exception:
        return DEFAULT_CHECKLIST.copy()


class ChecklistInjector:
    """把 checklist 注入到 Context（L1 最小实现）。"""

    def __init__(
        self,
        root_path: str,
        checklist_path: str = "./config/checklist.json",
    ):
        self.root_path = root_path
        self.checklist_path = checklist_path

    def _resolve_path(self) -> str:
        # checklist 路径：
        # - 若为绝对路径：直接使用
        # - 若为相对路径：相对 agent-system 根目录（root_path）解析
        abs_root = os.path.abspath(self.root_path)
        p = (self.checklist_path or "").strip()
        if not p:
            p = "./config/checklist.json"
        if os.path.isabs(p):
            return os.path.abspath(p)
        return os.path.abspath(os.path.join(abs_root, p))

    def build(self, pr: Optional[PR] = None) -> List[str]:
        _ = pr  # 预留：未来可以按语言/目录/PR 元信息选择不同 checklist
        return load_checklist(self._resolve_path())

    def inject(self, context: Optional[Context], pr: Optional[PR] = None) -> Context:
        if context is None:
            context = Context()

        if context.checklist:
            return context

        checklist = self.build(pr=pr)
        return replace(context, checklist=checklist)
