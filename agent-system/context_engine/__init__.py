"""L1 Context Engine (minimal).

当前仅实现 Checklist 注入：从配置文件加载业务/工程规则，注入到 Context.checklist。
"""

from .checklist import ChecklistInjector

__all__ = ["ChecklistInjector"]
