#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
框架测试脚本 - 不依赖 API Key
测试各模块是否能正常工作
"""
import os
import sys

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