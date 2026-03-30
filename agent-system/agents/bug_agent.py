"""
缺陷识别 Agent
基于规则和推理识别代码中的潜在缺陷
"""
import json
from typing import List, Dict, Any, Optional

import sys
sys.path.insert(0, '.')

from models import ReviewIssue, RiskLevel, PR, CodeChange, Context, ReviewResult, normalize_evidence
from llm.client import LLMClient
from agents.tool_agent import ToolAgent


class BugAgent:
    """缺陷识别 Agent"""
    
    # 系统提示词
    SYSTEM_PROMPT = """你是一个专业的代码评审专家，专注于识别代码中的潜在缺陷。

你的任务是：
1. 分析代码变更（diff）
2. 识别潜在的缺陷和问题
3. 提供具体的修复建议

你需要关注的问题类型：
- 空指针/空值处理（NPE）
- 并发问题（竞态条件、死锁）
- 资源泄漏（文件、连接、内存）
- 边界条件处理
- 异常处理不当
- 逻辑错误
- 安全漏洞

请严格按照以下 JSON 格式输出评审结果：
{
    "issues": [
        {
            "issue_type": "问题类型",
            "severity": "critical|high|medium|low",
            "message": "问题描述",
            "line_number": 行号，
            "evidence": ["证据 1", "证据 2"],
            "suggestion": "修复建议"
        }
    ],
    "summary": "整体评审总结"
}

如果没有发现问题，输出：{"issues": [], "summary": "未发现明显问题"}"""

    def __init__(self, llm_client: LLMClient, tool_agent: Optional[ToolAgent] = None):
        """
        初始化缺陷识别 Agent
        
        Args:
            llm_client: LLM 客户端
            tool_agent: 工具调用 Agent（可选）
        """
        self.llm_client = llm_client
        self.tool_agent = tool_agent
        self.reasoning_trace: List[str] = []
    
    def review(self, pr: PR, context: Optional[Context] = None) -> ReviewResult:
        """
        评审 PR
        
        Args:
            pr: PR 数据
            context: 上下文数据
            
        Returns:
            评审结果
        """
        self.reasoning_trace = []
        
        # 构建评审请求
        user_prompt = self._build_review_prompt(pr, context)
        
        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt}
        ]
        
        self.reasoning_trace.append("=== 开始分析 PR ===")
        self.reasoning_trace.append(f"PR 标题：{pr.title}")
        self.reasoning_trace.append(f"变更文件数：{len(pr.changes)}")
        
        # 调用 LLM 进行评审
        response = self.llm_client.chat(messages)
        
        self.reasoning_trace.append("=== LLM 响应 ===")
        self.reasoning_trace.append(response[:500] + "..." if len(response) > 500 else response)
        
        # 解析响应
        result = self._parse_response(response, pr.pr_id)
        
        return result
    
    def review_with_tools(self, pr: PR, context: Optional[Context] = None) -> ReviewResult:
        """
        使用工具增强的评审（Long CoT 模式）
        
        Args:
            pr: PR 数据
            context: 上下文数据
            
        Returns:
            评审结果
        """
        if not self.tool_agent:
            return self.review(pr, context)
        
        self.reasoning_trace = []
        
        # Step 1: READ - 理解代码
        self.reasoning_trace.append("=== Step 1: READ - 理解代码 ===")
        read_prompt = self._build_read_prompt(pr)
        
        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": read_prompt}
        ]
        
        read_response = self.llm_client.chat(messages)
        self.reasoning_trace.append(read_response[:300])
        
        # Step 2: HYPOTHESIZE - 提出假设
        self.reasoning_trace.append("=== Step 2: HYPOTHESIZE - 提出假设 ===")
        hypotheses = self._extract_hypotheses(read_response)
        self.reasoning_trace.append(f"假设列表：{hypotheses}")
        
        # Step 3: VERIFY - 工具验证
        self.reasoning_trace.append("=== Step 3: VERIFY - 工具验证 ===")
        verification_results = self._verify_hypotheses(hypotheses, pr)
        
        # Step 4: CONCLUDE - 生成结论
        self.reasoning_trace.append("=== Step 4: CONCLUDE - 生成结论 ===")
        conclude_prompt = self._build_conclude_prompt(pr, hypotheses, verification_results)
        
        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": conclude_prompt}
        ]
        
        response = self.llm_client.chat(messages)
        result = self._parse_response(response, pr.pr_id)
        
        return result
    
    def _build_review_prompt(self, pr: PR, context: Optional[Context]) -> str:
        """构建评审提示词"""
        prompt = f"""请评审以下 PR：

## PR 信息
- 标题：{pr.title}
- 描述：{pr.description or '无'}
- 目标分支：{pr.target_branch}
- 源分支：{pr.source_branch}

## 代码变更
"""
        
        for i, change in enumerate(pr.changes):
            prompt += f"\n### 变更 {i+1}: {change.file_path}\n"
            prompt += f"```diff\n{change.diff}\n```\n"
        
        if context:
            if context.code_context:
                prompt += f"\n## 相关代码上下文\n{context.code_context[:2000]}\n"
            if context.checklist:
                prompt += f"\n## 检查清单\n{context.checklist}\n"
        
        prompt += "\n请输出评审结果（JSON 格式）："
        return prompt
    
    def _build_read_prompt(self, pr: PR) -> str:
        """构建 READ 阶段提示词"""
        prompt = f"""请分析以下 PR 的代码变更，识别关键变量、指针、状态和潜在的并发问题点。

## PR 信息
- 标题：{pr.title}
- 描述：{pr.description or '无'}

## 代码变更
"""
        
        for change in pr.changes:
            prompt += f"\n### {change.file_path}\n"
            prompt += f"```diff\n{change.diff}\n```\n"
        
        prompt += "\n请列出：\n1. 关键变量/指针\n2. 可能的并发访问点\n3. 需要验证的假设"
        return prompt
    
    def _extract_hypotheses(self, response: str) -> List[str]:
        """从响应中提取假设"""
        hypotheses = []
        
        # 简单提取：查找数字列表
        import re
        matches = re.findall(r'\d+\.\s*(.+?)(?:\n|$)', response)
        hypotheses = [m.strip() for m in matches if m.strip()]
        
        return hypotheses[:5]  # 限制数量
    
    def _verify_hypotheses(self, hypotheses: List[str], pr: PR) -> List[Dict[str, Any]]:
        """验证假设"""
        results = []
        
        for hypothesis in hypotheses:
            self.reasoning_trace.append(f"验证假设：{hypothesis}")
            
            # 尝试从假设中提取关键词进行搜索
            keywords = self._extract_keywords(hypothesis)
            
            for keyword in keywords[:2]:
                if self.tool_agent:
                    tool_result = self.tool_agent.execute_tool(
                        "code_search",
                        {"pattern": keyword}
                    )
                    
                    self.reasoning_trace.append(f"  搜索 '{keyword}': {len(tool_result.result) if tool_result.result else 0} 个结果")
                    
                    if tool_result.success and tool_result.result:
                        results.append({
                            "hypothesis": hypothesis,
                            "keyword": keyword,
                            "evidence": tool_result.result[:3]
                        })
                        break
        
        return results
    
    def _extract_keywords(self, hypothesis: str) -> List[str]:
        """从假设中提取关键词"""
        # 简单实现：提取英文单词和中文关键词
        import re
        
        # 提取英文单词
        english_words = re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_]*\b', hypothesis)
        
        # 提取中文（简单匹配）
        chinese_chars = re.findall(r'[\u4e00-\u9fff]+', hypothesis)
        
        return english_words[:3] + chinese_chars[:2]
    
    def _build_conclude_prompt(self, pr: PR, 
                                hypotheses: List[str],
                                verification_results: List[Dict[str, Any]]) -> str:
        """构建结论阶段提示词"""
        prompt = f"""基于以下分析，请生成最终的评审结果：

## PR 信息
- 标题：{pr.title}

## 提出的假设
"""
        
        for i, h in enumerate(hypotheses, 1):
            prompt += f"{i}. {h}\n"
        
        prompt += "\n## 验证结果\n"
        for vr in verification_results:
            prompt += f"- 假设：{vr['hypothesis']}\n"
            prompt += f"  证据：{vr['evidence']}\n"
        
        prompt += "\n请输出最终评审结果（JSON 格式）："
        return prompt
    
    def _parse_response(self, response: str, pr_id: str) -> ReviewResult:
        """解析 LLM 响应"""
        result = ReviewResult(pr_id=pr_id, reasoning_trace=self.reasoning_trace.copy())
        
        # 尝试解析 JSON
        json_data = self.llm_client.extract_json(response)
        
        if not json_data:
            # 解析失败，创建默认结果
            result.summary = "评审完成（解析响应失败）"
            return result
        
        # 解析 issues
        issues_data = json_data.get("issues", [])
        
        for issue_data in issues_data:
            try:
                severity = RiskLevel(issue_data.get("severity", "medium"))
            except ValueError:
                severity = RiskLevel.MEDIUM
            
            issue = ReviewIssue(
                issue_type=issue_data.get("issue_type", "unknown"),
                severity=severity,
                message=issue_data.get("message", ""),
                file_path=issue_data.get("file_path", ""),
                line_number=issue_data.get("line_number", 0),
                evidence=issue_data.get("evidence", []),
                suggestion=issue_data.get("suggestion", "")
            )
            result.issues.append(issue)
        
        result.summary = json_data.get("summary", "评审完成")
        return result
    
    def get_reasoning_trace(self) -> List[str]:
        """获取推理轨迹"""
        return self.reasoning_trace