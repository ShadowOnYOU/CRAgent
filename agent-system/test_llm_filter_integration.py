#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""真实 LLM 的过滤器集成测试（会产生真实 API 调用）。

覆盖点：
- 调用 ReviewFilter.filter_with_llm() 的真实链路（LLM-as-Judge）
- strict_facts=True 时：先做事实校验（file/line/evidence 可复现），再交给 LLM 过滤

注意：
- 模型输出存在随机性，因此本脚本只做“稳定断言”（不强行要求 keep 具体编号）。
- 未设置 DASHSCOPE_API_KEY 时默认跳过（退出码 0），可用 --require-key 强制失败。

用法：
  export DASHSCOPE_API_KEY=your_api_key
  /opt/anaconda3/envs/cragent/bin/python agent-system/test_llm_filter_integration.py

可选：
  --require-key   没有 key 时退出码 1
  --model xxx     覆盖模型名
"""

import argparse
import os
import sys
import tempfile

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from llm.client import LLMClient
from judge.filter import ReviewFilter
from models import PR, CodeChange, ReviewResult, ReviewIssue, RiskLevel


def build_fixture(tmpdir: str) -> tuple[PR, ReviewResult]:
    file_path = "a.py"
    file_content = """def foo():
    x = 1
    return x
"""

    abs_file = os.path.join(tmpdir, file_path)
    with open(abs_file, "w", encoding="utf-8") as f:
        f.write(file_content)

    diff = """diff --git a/a.py b/a.py
index 0000000..1111111 100644
--- a/a.py
+++ b/a.py
@@ -0,0 +1,3 @@
+def foo():
+    x = 1
+    return x
"""

    pr = PR(
        pr_id="LLM-FILTER-001",
        title="llm filter integration",
        changes=[
            CodeChange(
                file_path=file_path,
                diff=diff,
                new_content=file_content,
                line_start=1,
                line_end=3,
            )
        ],
    )

    # 这里刻意混入几条“事实不成立”的 issue，验证 strict_facts 会先剔除/降级
    result = ReviewResult(
        pr_id=pr.pr_id,
        summary="fixture",
        issues=[
            ReviewIssue(
                issue_type="逻辑错误",
                severity=RiskLevel.MEDIUM,
                message="return 行可能有问题（示例）",
                file_path=file_path,
                line_number=3,
                evidence=["return x"],
                suggestion="检查返回值是否符合预期",
                confidence=0.9,
            ),
            ReviewIssue(
                issue_type="空指针",
                severity=RiskLevel.HIGH,
                message="引用了不存在的文件（应被剔除）",
                file_path="missing.py",
                line_number=1,
                evidence=["something"],
                confidence=0.9,
            ),
            ReviewIssue(
                issue_type="越界",
                severity=RiskLevel.HIGH,
                message="行号越界（应被剔除）",
                file_path=file_path,
                line_number=999,
                evidence=["return x"],
                confidence=0.9,
            ),
            ReviewIssue(
                issue_type="无证据",
                severity=RiskLevel.HIGH,
                message="没有证据（会被降到 0 置信度并被过滤）",
                file_path=file_path,
                line_number=2,
                evidence=[],
                confidence=0.9,
            ),
            ReviewIssue(
                issue_type="证据不可复现",
                severity=RiskLevel.HIGH,
                message="证据在文件/PR diff 中找不到（会被降级）",
                file_path=file_path,
                line_number=2,
                evidence=["definitely_not_in_file()"],
                confidence=0.9,
            ),
        ],
    )

    return pr, result


def assert_result_is_sane(filtered: ReviewResult, root_path: str) -> None:
    # 稳定断言：所有保留下来的 issues 必须满足事实约束
    for issue in filtered.issues:
        if os.path.isabs(issue.file_path) or issue.file_path.startswith("../"):
            raise AssertionError(f"返回结果包含不安全路径：{issue.file_path}")

        abs_file = os.path.join(root_path, issue.file_path)
        if not os.path.isfile(abs_file):
            raise AssertionError(f"返回结果包含不存在文件：{issue.file_path}")

        with open(abs_file, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.read().splitlines()

        if issue.line_number <= 0 or issue.line_number > len(lines):
            raise AssertionError(
                f"返回结果行号不合法：{issue.file_path}:{issue.line_number}（文件共 {len(lines)} 行）"
            )

        if not issue.evidence:
            raise AssertionError(f"返回结果包含无证据 issue：{issue.issue_type}")


def main() -> int:
    parser = argparse.ArgumentParser(description="真实 LLM 过滤器集成测试")
    parser.add_argument("--require-key", action="store_true", help="没有 API Key 时直接失败")
    parser.add_argument("--model", default=None, help="覆盖模型名（默认使用 config）")
    args = parser.parse_args()

    if not os.getenv("DASHSCOPE_API_KEY"):
        msg = "未设置 DASHSCOPE_API_KEY，跳过真实 LLM 过滤集成测试。"
        if args.require_key:
            print("❌ " + msg)
            return 1
        print("⚠️  " + msg)
        print("   export DASHSCOPE_API_KEY=your_api_key_here")
        return 0

    print("=" * 60)
    print("运行真实 LLM 过滤集成测试（会产生真实 API 调用）")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmpdir:
        pr, result = build_fixture(tmpdir)

        llm = LLMClient(model=args.model)
        f = ReviewFilter(llm_client=llm, root_path=tmpdir)

        filtered = f.filter_with_llm(
            result,
            pr=pr,
            root_path=tmpdir,
            strict_facts=True,
        )

        # 关键：无论 LLM keep/remove 怎么波动，最终结果都必须满足事实约束
        assert_result_is_sane(filtered, tmpdir)

        # 基本期望：至少不会把明显非法的 issue 保留下来
        # （如果 LLM 全部 remove，也允许；但不允许保留 missing.py/999 行等）
        for issue in filtered.issues:
            if issue.file_path == "missing.py":
                raise AssertionError("不应保留 missing.py")
            if issue.line_number == 999:
                raise AssertionError("不应保留越界行号")

        print(f"✅ 通过：返回 issues={len(filtered.issues)}，summary={filtered.summary!r}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
