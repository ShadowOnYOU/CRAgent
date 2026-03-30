#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
框架测试脚本 - 不依赖 API Key
测试各模块是否能正常工作
"""
import os
import sys
import tempfile

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_models():
    """测试数据模型"""
    print("=" * 50)
    print("测试数据模型模块...")
    
    from models import PR, CodeChange, ReviewIssue, ReviewResult, RiskLevel, FeedbackStatus
    
    # 创建测试数据
    change = CodeChange(
        file_path="test.py",
        old_content="def hello():\n    pass",
        new_content="def hello():\n    print('Hello')",
        diff="--- a/test.py\n+++ b/test.py\n@@ -1,2 +1,2 @@\n def hello():\n-    pass\n+    print('Hello')",
        line_start=1,
        line_end=2
    )
    
    pr = PR(
        pr_id="TEST-001",
        title="Test PR",
        description="This is a test PR",
        changes=[change]
    )
    
    issue = ReviewIssue(
        issue_type="代码优化",
        severity=RiskLevel.MEDIUM,
        message="这是一个测试问题",
        file_path="test.py",
        line_number=1,
        confidence=0.9
    )
    
    result = ReviewResult(
        pr_id="TEST-001",
        issues=[issue],
        summary="测试完成"
    )
    
    print(f"  ✅ PR 创建成功：{pr.title}")
    print(f"  ✅ CodeChange 创建成功：{change.file_path}")
    print(f"  ✅ ReviewIssue 创建成功：{issue.issue_type}")
    print(f"  ✅ ReviewResult 创建成功：{result.summary}")
    print(f"  ✅ RiskLevel: {RiskLevel.MEDIUM.value}")
    print(f"  ✅ FeedbackStatus: {FeedbackStatus.ACCEPT.value}")
    return True

def test_pr_parser():
    """测试 PR 解析器"""
    print("=" * 50)
    print("测试 PR 解析器模块...")
    
    from ingestion.pr_parser import PRParser
    
    parser = PRParser()
    
    diff = """--- a/test.py
+++ b/test.py
@@ -1,3 +1,4 @@
 def hello():
-    pass
+    name = "World"
+    print(f"Hello {name}")
"""
    
    changes = parser.parse_diff(diff)
    
    print(f"  ✅ 解析成功，发现 {len(changes)} 个文件变更")
    for change in changes:
        print(f"     - {change.file_path} (行 {change.line_start}-{change.line_end})")
    
    return True

def test_tools():
    """测试工具模块"""
    print("=" * 50)
    print("测试工具模块...")
    
    from tools.code_search import CodeSearch
    from tools.grep_tool import GrepTool
    from tools.ast_parser import ASTParser
    
    # 测试 CodeSearch
    search = CodeSearch(root_path=".")
    print(f"  ✅ CodeSearch 初始化成功，根路径：{search.root_path}")
    
    # 测试 GrepTool
    try:
        grep_tool = GrepTool(root_path=".")
        result = grep_tool.grep("def ", file_pattern="*.py", max_results=3)
        print(f"  ✅ GrepTool 执行成功，找到 {len(result)} 个结果")
    except Exception as e:
        print(f"  ⚠️  GrepTool 执行失败：{e}")
    
    # 测试 AST Parser
    ast_parser = ASTParser()
    code = "def hello():\n    return 'world'"
    try:
        tree = ast_parser.parse(code)
        print(f"  ✅ ASTParser 解析成功")
    except Exception as e:
        print(f"  ⚠️  ASTParser 解析失败：{e}")
    
    return True

def test_filter():
    """测试过滤器"""
    print("=" * 50)
    print("测试过滤器模块...")
    
    from judge.filter import ReviewFilter
    from models import ReviewResult, ReviewIssue, RiskLevel
    
    filter_obj = ReviewFilter()
    
    # 创建测试数据
    result = ReviewResult(
        pr_id="TEST-001",
        issues=[
            ReviewIssue(
                issue_type="空指针",
                severity=RiskLevel.HIGH,
                message="可能为空指针",
                file_path="test.py",
                line_number=1,
                confidence=0.9
            ),
            ReviewIssue(
                issue_type="风格问题",
                severity=RiskLevel.LOW,
                message="建议加注释",
                file_path="test.py",
                line_number=2,
                confidence=0.5
            )
        ],
        summary="测试过滤"
    )
    
    filtered = filter_obj.filter(result, min_severity=RiskLevel.MEDIUM)
    
    print(f"  ✅ 过滤前：{len(result.issues)} 个问题")
    print(f"  ✅ 过滤后：{len(filtered.issues)} 个问题")
    print(f"  ✅ 过滤结果：{filtered.summary}")
    
    return True

def test_feedback():
    """测试反馈模块"""
    print("=" * 50)
    print("测试反馈模块...")
    
    from feedback.loop import FeedbackLoop
    from models import FeedbackStatus
    
    feedback = FeedbackLoop(data_dir="./data/test_feedback")
    
    # 记录测试反馈
    feedback.accept("TEST-001", 0, "确实是问题")
    feedback.reject("TEST-001", 1, "误报")
    feedback.ignore("TEST-001", 2, "不重要")
    
    stats = feedback.get_stats()
    rate = feedback.get_acceptance_rate()
    
    print(f"  ✅ 反馈记录成功")
    print(f"  ✅ 统计：{stats}")
    print(f"  ✅ 采纳率：{rate:.2%}")
    
    return True

def test_simple_review():
    """测试简单评审（不使用 LLM）"""
    print("=" * 50)
    print("测试简单评审流程...")
    
    from models import PR, CodeChange, ReviewResult, ReviewIssue, RiskLevel
    from judge.filter import ReviewFilter
    from feedback.loop import FeedbackLoop
    from ingestion.pr_parser import PRParser
    
    # 创建 PR
    pr = PR(
        pr_id="SIMPLE-001",
        title="简单测试",
        description="不使用 LLM 的测试",
        changes=[
            CodeChange(
                file_path="test.py",
                diff="--- a/test.py\n+++ b/test.py\n@@ -1 +1 @@\n-def old(): pass\n+def new(): pass",
                line_start=1,
                line_end=1
            )
        ]
    )
    
    # 创建模拟结果
    result = ReviewResult(
        pr_id=pr.pr_id,
        issues=[
            ReviewIssue(
                issue_type="代码风格",
                severity=RiskLevel.LOW,
                message="函数定义建议换行",
                file_path="test.py",
                line_number=1,
                confidence=0.7,
                suggestion="建议将函数定义换行"
            )
        ],
        summary="简单评审完成",
        reasoning_trace=["步骤 1: 解析变更", "步骤 2: 识别问题", "步骤 3: 生成建议"]
    )
    
    # 过滤
    filter_obj = ReviewFilter()
    filtered = filter_obj.filter(result)
    
    # 保存
    feedback = FeedbackLoop(data_dir="./data/simple_feedback")
    feedback.save_review_result(filtered)
    
    print(f"  ✅ 评审流程完成")
    print(f"  ✅ 发现问题数：{len(filtered.issues)}")
    print(f"  ✅ 推理轨迹：{len(filtered.reasoning_trace)} 步")
    
    # 打印结果
    print("\n  评审结果:")
    print(f"    总结：{filtered.summary}")
    for i, issue in enumerate(filtered.issues, 1):
        print(f"    问题{i}: [{issue.severity.value}] {issue.message}")
    
    return True


def test_filter_fact_checks():
    """测试过滤器的事实校验（L3 强约束）"""
    print("=" * 50)
    print("测试过滤器事实校验...\n")

    from judge.filter import ReviewFilter
    from models import PR, CodeChange, ReviewResult, ReviewIssue, RiskLevel

    with tempfile.TemporaryDirectory() as tmpdir:
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
            pr_id="FACT-001",
            title="fact check",
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

        result = ReviewResult(
            pr_id=pr.pr_id,
            issues=[
                # ✅ 合法：能定位到文件/行号且证据可复现
                ReviewIssue(
                    issue_type="逻辑错误",
                    severity=RiskLevel.MEDIUM,
                    message="return 行可能有问题",
                    file_path=f"{os.path.basename(tmpdir)}/{file_path}",
                    line_number=3,
                    evidence=["return x"],
                    confidence=0.9,
                ),
                # ✅ 合法（路径归一化）：diff 常见 b/ 前缀
                ReviewIssue(
                    issue_type="一致性",
                    severity=RiskLevel.MEDIUM,
                    message="路径前缀应被归一化",
                    file_path="b/a.py",
                    line_number=1,
                    evidence=["def foo():"],
                    confidence=0.9,
                ),
                # ❌ 非法：文件不存在
                ReviewIssue(
                    issue_type="空指针",
                    severity=RiskLevel.HIGH,
                    message="引用了不存在的文件",
                    file_path="missing.py",
                    line_number=1,
                    evidence=["something"],
                    confidence=0.9,
                ),
                # ❌ 非法：行号越界
                ReviewIssue(
                    issue_type="越界",
                    severity=RiskLevel.HIGH,
                    message="行号越界",
                    file_path=file_path,
                    line_number=999,
                    evidence=["return x"],
                    confidence=0.9,
                ),
                # ❌ 非法：无证据
                ReviewIssue(
                    issue_type="竞态",
                    severity=RiskLevel.HIGH,
                    message="没有证据的结论",
                    file_path=file_path,
                    line_number=2,
                    evidence=[],
                    confidence=0.9,
                ),
                # ❌ 非法：证据不可复现
                ReviewIssue(
                    issue_type="资源泄漏",
                    severity=RiskLevel.HIGH,
                    message="证据在文件/PR diff 中找不到",
                    file_path=file_path,
                    line_number=2,
                    evidence=["definitely_not_in_file()"],
                    confidence=0.9,
                ),
            ],
            summary="fact test",
        )

        filter_obj = ReviewFilter(root_path=tmpdir)
        filtered = filter_obj.filter(
            result,
            min_severity=RiskLevel.LOW,
            min_confidence=0.5,
            pr=pr,
            root_path=tmpdir,
            strict_facts=True,
        )

        assert len(filtered.issues) == 2, f"期望保留 2 条，实际 {len(filtered.issues)} 条"
        kept = {(i.file_path, i.line_number) for i in filtered.issues}
        assert ("a.py", 3) in kept
        assert ("a.py", 1) in kept

    print("  ✅ 事实校验过滤通过：仅保留可定位且证据可复现的问题")
    return True


def test_l1_checklist_injection():
    """测试 L1 Checklist 注入（不依赖 API Key）"""
    print("=" * 50)
    print("测试 L1 Checklist 注入...\n")

    from context_engine.checklist import ChecklistInjector
    from models import Context

    agent_system_dir = os.path.dirname(os.path.abspath(__file__))

    injector = ChecklistInjector(
        root_path=agent_system_dir,
        checklist_path="./config/checklist.json",
    )

    ctx = injector.inject(None)
    assert ctx.checklist, "期望注入后 checklist 非空"

    # 不应覆盖已有 checklist
    original = Context(checklist=["已有规则"])
    ctx2 = injector.inject(original)
    assert ctx2.checklist == ["已有规则"], "不应覆盖已有 checklist"

    print(f"  ✅ Checklist 注入成功：{len(ctx.checklist)} 条规则")
    return True

def main():
    """主函数"""
    print("\n" + "=" * 60)
    print("Code Review Agent 框架测试")
    print("=" * 60 + "\n")
    
    tests = [
        ("数据模型", test_models),
        ("PR 解析器", test_pr_parser),
        ("工具模块", test_tools),
        ("过滤器", test_filter),
        ("过滤器事实校验", test_filter_fact_checks),
        ("L1 Checklist 注入", test_l1_checklist_injection),
        ("反馈模块", test_feedback),
        ("简单评审", test_simple_review),
    ]
    
    passed = 0
    failed = 0
    
    for name, test_func in tests:
        try:
            if test_func():
                passed += 1
        except Exception as e:
            print(f"  ❌ {name} 测试失败：{e}")
            import traceback
            traceback.print_exc()
            failed += 1
    
    print("\n" + "=" * 60)
    print(f"测试完成：{passed} 通过，{failed} 失败")
    print("=" * 60)
    
    if failed == 0:
        print("\n✅ 所有模块工作正常！")
        print("\n提示：要完整运行评审功能，需要配置 API Key:")
        print("  export DASHSCOPE_API_KEY=your_api_key_here")
        print("  然后运行：python main.py")
    else:
        print("\n❌ 部分模块存在问题，请检查错误信息")
    
    return failed == 0

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)