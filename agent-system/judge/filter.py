"""
评审过滤器
实现 LLM-as-Judge 过滤逻辑
"""
from typing import List, Optional, Set

import sys
sys.path.insert(0, '.')

from models import ReviewResult, ReviewIssue, RiskLevel
from llm.client import LLMClient


class ReviewFilter:
    """评审结果过滤器"""
    
    SYSTEM_PROMPT = """你是一个严格的代码评审法官。请评估以下评审意见的质量。

评估维度：
1. 技术正确性 - 问题是否真实存在
2. 可执行性 - 建议是否具体可操作
3. 表达质量 - 描述是否清晰

请过滤掉：
- 误报（问题不存在）
- 低价值建议（如"建议加注释"）
- 重复问题
- 纯风格问题（除非严重影响可读性）"""

    def __init__(self, llm_client: Optional[LLMClient] = None):
        """
        初始化过滤器
        
        Args:
            llm_client: LLM 客户端（可选，用于 LLM 过滤）
        """
        self.llm_client = llm_client
    
    def filter(self, result: ReviewResult, 
               min_severity: RiskLevel = RiskLevel.LOW,
               min_confidence: float = 0.5) -> ReviewResult:
        """
        过滤评审结果
        
        Args:
            result: 原始评审结果
            min_severity: 最小严重级别
            min_confidence: 最小置信度
            
        Returns:
            过滤后的结果
        """
        filtered = ReviewResult(
            pr_id=result.pr_id,
            summary=result.summary,
            reasoning_trace=result.reasoning_trace
        )
        
        # 严重级别映射
        severity_order = {
            RiskLevel.LOW: 0,
            RiskLevel.MEDIUM: 1,
            RiskLevel.HIGH: 2,
            RiskLevel.CRITICAL: 3
        }
        
        min_sev_value = severity_order.get(min_severity, 0)
        
        for issue in result.issues:
            # 检查严重级别
            issue_sev_value = severity_order.get(issue.severity, 0)
            if issue_sev_value < min_sev_value:
                continue
            
            # 检查置信度
            if issue.confidence < min_confidence:
                continue
            
            # 检查是否为低价值问题
            if self._is_low_value(issue):
                continue
            
            # 检查是否为重复问题
            if self._is_duplicate(issue, filtered.issues):
                continue
            
            filtered.issues.append(issue)
        
        # 更新总结
        if not filtered.issues:
            filtered.summary = "经过过滤，未发现需要关注的问题"
        else:
            filtered.summary = f"发现 {len(filtered.issues)} 个需要关注的问题"
        
        return filtered
    
    def filter_with_llm(self, result: ReviewResult) -> ReviewResult:
        """
        使用 LLM 进行智能过滤
        
        Args:
            result: 原始评审结果
            
        Returns:
            过滤后的结果
        """
        if not self.llm_client:
            return self.filter(result)
        
        # 构建评审意见列表
        issues_text = ""
        for i, issue in enumerate(result.issues, 1):
            issues_text += f"{i}. [{issue.severity.value}] {issue.issue_type}: {issue.message}\n"
            issues_text += f"   文件：{issue.file_path}:{issue.line_number}\n"
            issues_text += f"   证据：{issue.evidence}\n"
            issues_text += f"   建议：{issue.suggestion}\n\n"
        
        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": f"""请评估以下评审意见，保留高价值的问题：

{issues_text}

请输出 JSON 格式的评估结果：
{{
    "keep": [1, 2],  // 保留的问题编号
    "remove": [3],   // 移除的问题编号
    "reason": "移除原因说明"
}}"""}
        ]
        
        response = self.llm_client.chat(messages)
        json_data = self.llm_client.extract_json(response)
        
        if not json_data:
            # 解析失败，返回原始结果
            return result
        
        keep_indices = json_data.get("keep", [])
        
        filtered = ReviewResult(
            pr_id=result.pr_id,
            reasoning_trace=result.reasoning_trace
        )
        
        for i, issue in enumerate(result.issues, 1):
            if i in keep_indices:
                filtered.issues.append(issue)
        
        filtered.summary = f"经过 LLM 评估，保留 {len(filtered.issues)} 个高价值问题"
        return filtered
    
    def _is_low_value(self, issue: ReviewIssue) -> bool:
        """检查是否为低价值问题"""
        low_value_keywords = [
            "建议加注释",
            "建议添加注释",
            "命名不规范",
            "命名不好",
            "可以考虑",
            "最好加上",
            "建议优化",
            "代码风格",
            "格式问题"
        ]
        
        text = f"{issue.message} {issue.suggestion}".lower()
        
        for keyword in low_value_keywords:
            if keyword.lower() in text:
                return True
        
        return False
    
    def _is_duplicate(self, issue: ReviewIssue, 
                      existing_issues: List[ReviewIssue]) -> bool:
        """检查是否为重复问题"""
        # 简单去重：相同文件 + 相同问题类型
        for existing in existing_issues:
            if (existing.file_path == issue.file_path and 
                existing.issue_type == issue.issue_type):
                return True
        
        return False
    
    def deduplicate(self, issues: List[ReviewIssue]) -> List[ReviewIssue]:
        """
        去重
        
        Args:
            issues: 问题列表
            
        Returns:
            去重后的列表
        """
        seen: Set[str] = set()
        result = []
        
        for issue in issues:
            # 生成唯一标识
            key = f"{issue.file_path}:{issue.issue_type}:{issue.message[:50]}"
            
            if key not in seen:
                seen.add(key)
                result.append(issue)
        
        return result
    
    def sort_by_severity(self, issues: List[ReviewIssue]) -> List[ReviewIssue]:
        """
        按严重级别排序
        
        Args:
            issues: 问题列表
            
        Returns:
            排序后的列表
        """
        severity_order = {
            RiskLevel.CRITICAL: 0,
            RiskLevel.HIGH: 1,
            RiskLevel.MEDIUM: 2,
            RiskLevel.LOW: 3
        }
        
        return sorted(issues, key=lambda x: severity_order.get(x.severity, 4))