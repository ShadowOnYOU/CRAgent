#!/usr/bin/env python3
"""
Code Review Agent - 主入口
基于阿里云百炼 LLM 的代码评审智能体
"""
import os
import sys
import json
import argparse
from typing import Optional

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from models import PR, CodeChange, Context, ReviewResult, RiskLevel
from config.settings import config
from llm.client import LLMClient
from agents.tool_agent import ToolAgent
from agents.bug_agent import BugAgent
from reasoning.long_cot import LongCoTEngine
from judge.filter import ReviewFilter
from feedback.loop import FeedbackLoop
from ingestion.pr_parser import PRParser
from context_engine.checklist import ChecklistInjector


class CodeReviewAgent:
    """代码评审 Agent 主类"""
    
    def __init__(self, root_path: str = ".", use_long_cot: bool = True):
        """
        初始化代码评审 Agent
        
        Args:
            root_path: 代码根路径
            use_long_cot: 是否使用 Long CoT 推理
        """
        self.root_path = root_path
        self.use_long_cot = use_long_cot
        
        # 初始化各模块
        self.llm_client = LLMClient()
        self.tool_agent = ToolAgent(root_path)
        self.pr_parser = PRParser()
        self.review_filter = ReviewFilter(self.llm_client)
        self.feedback_loop = FeedbackLoop()
        # L1：Checklist 注入（最小实现）
        self.checklist_injector = ChecklistInjector(
            root_path=os.path.dirname(os.path.abspath(__file__)),
            checklist_path=getattr(config.review, "checklist_path", "./config/checklist.json"),
        )
        
        # 根据模式选择推理引擎
        if use_long_cot:
            self.reasoning_engine = LongCoTEngine(self.llm_client, self.tool_agent)
        else:
            self.bug_agent = BugAgent(self.llm_client, self.tool_agent)
    
    def review_pr(self, pr: PR, context: Optional[Context] = None,
                  enable_filter: bool = True) -> ReviewResult:
        """
        评审 PR
        
        Args:
            pr: PR 数据
            context: 上下文数据
            enable_filter: 是否启用过滤
            
        Returns:
            评审结果
        """
        print(f"开始评审 PR: {pr.title}")
        print(f"变更文件数：{len(pr.changes)}")

        # L1：注入自定义 Checklist（业务/工程规则）
        if getattr(config.review, "enable_checklist", True):
            context = self.checklist_injector.inject(context, pr=pr)
        
        # 执行推理
        if self.use_long_cot:
            result = self.reasoning_engine.reason(pr, context)
        else:
            result = self.bug_agent.review_with_tools(pr, context)
        
        print(f"\n推理完成，发现 {len(result.issues)} 个问题")
        
        # 过滤
        if enable_filter:
            print("正在过滤低价值问题...")
            result = self.review_filter.filter(
                result,
                min_severity=RiskLevel.LOW,
                pr=pr,
                root_path=self.root_path,
                strict_facts=True,
            )
            print(f"过滤后剩余 {len(result.issues)} 个问题")
        
        # 保存结果
        self.feedback_loop.save_review_result(result)
        
        return result
    
    def review_diff(
        self,
        diff_text: str,
        pr_title: str = "Untitled",
        pr_description: str = "",
        enable_filter: bool = True,
    ) -> ReviewResult:
        """
        直接评审 diff 文本
        
        Args:
            diff_text: Git diff 格式文本
            pr_title: PR 标题
            pr_description: PR 描述
            
        Returns:
            评审结果
        """
        # 解析 diff
        changes = self.pr_parser.parse_diff(diff_text)
        
        # 创建 PR 对象
        pr = PR(
            pr_id="diff_" + str(hash(diff_text))[:8],
            title=pr_title,
            description=pr_description,
            changes=changes
        )
        
        return self.review_pr(pr, enable_filter=enable_filter)
    
    def review_file_changes(self, file_path: str, old_content: str, 
                            new_content: str, pr_title: str = "") -> ReviewResult:
        """
        评审单个文件的变更
        
        Args:
            file_path: 文件路径
            old_content: 原内容
            new_content: 新内容
            pr_title: PR 标题
            
        Returns:
            评审结果
        """
        # 生成简单 diff
        diff = f"--- a/{file_path}\n+++ b/{file_path}\n"
        old_lines = old_content.split('\n')
        new_lines = new_content.split('\n')
        
        diff += f"@@ -1,{len(old_lines)} +1,{len(new_lines)} @@\n"
        
        for line in old_lines:
            diff += f"-{line}\n"
        for line in new_lines:
            diff += f"+{line}\n"
        
        return self.review_diff(diff, pr_title, file_path)
    
    def print_result(self, result: ReviewResult):
        """打印评审结果"""
        print("\n" + "=" * 60)
        print(f"评审结果：{result.summary}")
        print("=" * 60)
        
        if not result.issues:
            print("✅ 未发现明显问题")
            return
        
        # 按严重级别排序
        severity_order = {
            RiskLevel.CRITICAL: 0,
            RiskLevel.HIGH: 1,
            RiskLevel.MEDIUM: 2,
            RiskLevel.LOW: 3
        }
        sorted_issues = sorted(result.issues, 
                               key=lambda x: severity_order.get(x.severity, 4))
        
        for i, issue in enumerate(sorted_issues, 1):
            emoji = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(
                issue.severity.value, "⚪")
            
            print(f"\n{emoji} 问题 {i}: [{issue.severity.value}] {issue.issue_type}")
            print(f"   文件：{issue.file_path}:{issue.line_number}")
            print(f"   描述：{issue.message}")
            if issue.evidence:
                print(f"   证据：{issue.evidence[0] if issue.evidence else '无'}")
            if issue.suggestion:
                print(f"   建议：{issue.suggestion}")
        
        print("\n" + "=" * 60)
    
    def get_reasoning_trace(self) -> list:
        """获取推理轨迹"""
        if self.use_long_cot:
            return self.reasoning_engine.get_trace()
        return self.bug_agent.get_reasoning_trace()


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="Code Review Agent")
    parser.add_argument("--diff", "-d", help="Git diff 文件路径")
    parser.add_argument("--root", "-r", default=".", help="代码根路径")
    parser.add_argument("--title", "-t", default="Untitled", help="PR 标题")
    parser.add_argument("--simple", "-s", action="store_true", help="使用简单模式（不使用 Long CoT）")
    parser.add_argument("--no-filter", action="store_true", help="禁用结果过滤")
    parser.add_argument("--output", "-o", help="输出结果文件路径")
    
    args = parser.parse_args()

    def _resolve_root_path(root_path: str) -> str:
        root_path = str(root_path or ".").strip() or "."
        if os.path.isabs(root_path) and os.path.exists(root_path):
            return root_path
        if os.path.exists(root_path):
            return os.path.abspath(root_path)
        # 兼容在 agent-system/ 目录内运行：把相对路径按项目根目录尝试一次
        project_root = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
        candidate = os.path.join(project_root, root_path)
        if os.path.exists(candidate):
            return os.path.abspath(candidate)
        return os.path.abspath(root_path)

    def _resolve_diff_path(diff_path: str, resolved_root: str) -> str:
        diff_path = str(diff_path or "").strip()
        if not diff_path:
            return diff_path

        # 1) 原样（相对 cwd）
        if os.path.exists(diff_path):
            return os.path.abspath(diff_path)

        # 2) 绝对路径
        if os.path.isabs(diff_path):
            return diff_path

        project_root = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))

        # 3) 常见位置：<root>/pr_diffs/<name> 或 <root>/<name>
        if resolved_root and os.path.exists(resolved_root):
            for cand in (
                os.path.join(resolved_root, diff_path),
                os.path.join(resolved_root, "pr_diffs", diff_path),
                os.path.join(resolved_root, "tests", "pr_diffs", diff_path),
            ):
                if os.path.exists(cand):
                    return os.path.abspath(cand)

        # 4) 项目根相对路径
        for cand in (
            os.path.join(project_root, diff_path),
            os.path.join(project_root, "pr_diffs", diff_path),
        ):
            if os.path.exists(cand):
                return os.path.abspath(cand)

        return diff_path

    def _resolve_output_path(output_path: str) -> str:
        output_path = str(output_path or "").strip()
        if not output_path:
            return output_path
        if os.path.isabs(output_path):
            return output_path
        if os.path.exists(os.path.dirname(output_path) or "."):
            return os.path.abspath(output_path)

        project_root = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
        candidate = os.path.join(project_root, output_path)
        return os.path.abspath(candidate)
    
    # 检查 API Key
    if not os.getenv("DASHSCOPE_API_KEY"):
        print("❌ 错误：请设置 DASHSCOPE_API_KEY 环境变量")
        print("   export DASHSCOPE_API_KEY=your_api_key")
        sys.exit(1)
    
    resolved_root = _resolve_root_path(args.root)
    # 创建 Agent
    agent = CodeReviewAgent(root_path=resolved_root, use_long_cot=not args.simple)
    
    # 读取 diff
    if args.diff:
        diff_file = _resolve_diff_path(args.diff, resolved_root)
        with open(diff_file, 'r', encoding='utf-8') as f:
            diff_text = f.read()
        result = agent.review_diff(diff_text, args.title, enable_filter=not args.no_filter)
    else:
        # 演示模式：创建示例 PR
        print("未指定 diff 文件，进入演示模式...")
        pr = PR(
            pr_id="demo_001",
            title=args.title,
            description="演示 PR",
            changes=[
                CodeChange(
                    file_path="example.py",
                    diff="""--- a/example.py
+++ b/example.py
@@ -1,5 +1,7 @@
 def process_data(data):
-    result = data.get('result')
+    result = data['result']  # 直接访问，不检查是否存在
     return result.process()
+
+# TODO: 添加错误处理""",
                    line_start=1,
                    line_end=7
                )
            ]
        )
        result = agent.review_pr(pr, enable_filter=not args.no_filter)
    
    # 输出结果
    agent.print_result(result)
    
    # 保存到文件
    if args.output:
        output_file = _resolve_output_path(args.output)
        out_dir = os.path.dirname(output_file)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump({
                "summary": result.summary,
                "reasoning_trace": result.reasoning_trace,
                "run_trace": result.run_trace,
                "issues": [
                    {
                        "type": i.issue_type,
                        "severity": i.severity.value,
                        "message": i.message,
                        "file": i.file_path,
                        "line": i.line_number,
                        "evidence": i.evidence,
                        "suggestion": i.suggestion
                    }
                    for i in result.issues
                ]
            }, f, ensure_ascii=False, indent=2)
        print(f"\n结果已保存到：{output_file}")


if __name__ == "__main__":
    main()