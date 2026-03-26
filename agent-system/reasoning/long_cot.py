"""
Long CoT 推理引擎
实现 READ -> HYPOTHESIZE -> VERIFY -> CONCLUDE 推理循环
"""
import json
from typing import List, Dict, Any, Optional, Tuple

import sys
sys.path.insert(0, '.')

from models import PR, Context, ReviewResult, ReviewIssue, RiskLevel
from llm.client import LLMClient
from agents.tool_agent import ToolAgent


class LongCoTEngine:
    """Long CoT 推理引擎"""
    
    # 各阶段的系统提示词
    READ_SYSTEM = """你是一个代码分析专家。请仔细阅读代码变更，识别：
1. 关键变量、指针、数据结构
2. 并发相关的代码（线程、锁、共享资源）
3. 资源管理（分配/释放）
4. 错误处理逻辑
5. 边界条件处理

请结构化输出分析结果。"""

    HYPOTHESIZE_SYSTEM = """基于代码分析，提出可能的缺陷假设。
关注以下类型的问题：
- 空指针/空值解引用
- 竞态条件/数据竞争
- 资源泄漏
- 缓冲区溢出
- 逻辑错误

每个假设应该是可验证的。"""

    VERIFY_SYSTEM = """你是一个验证专家。请设计验证步骤来确认或推翻每个假设。
使用可用的工具收集证据。"""

    CONCLUDE_SYSTEM = """基于所有验证结果，生成最终的评审结论。
只报告有充分证据支持的问题。"""

    def __init__(self, llm_client: LLMClient, tool_agent: ToolAgent, max_iterations: int = 3):
        """
        初始化推理引擎
        
        Args:
            llm_client: LLM 客户端
            tool_agent: 工具 Agent
            max_iterations: 最大迭代次数
        """
        self.llm_client = llm_client
        self.tool_agent = tool_agent
        self.max_iterations = max_iterations
        self.trace: List[str] = []

    def reason(self, pr: PR, context: Optional[Context] = None) -> ReviewResult:
        """
        执行完整推理流程
        
        Args:
            pr: PR 数据
            context: 上下文数据
            
        Returns:
            评审结果
        """
        self.trace = []
        
        # Step 1: READ
        self.trace.append("=" * 50)
        self.trace.append("Step 1: READ - 理解代码")
        self.trace.append("=" * 50)
        
        read_result = self._read(pr)
        self.trace.append(f"READ 结果：{json.dumps(read_result, ensure_ascii=False)[:500]}")
        
        # Step 2: HYPOTHESIZE
        self.trace.append("\n" + "=" * 50)
        self.trace.append("Step 2: HYPOTHESIZE - 提出假设")
        self.trace.append("=" * 50)
        
        hypotheses = self._hypothesize(pr, read_result)
        self.trace.append(f"假设数量：{len(hypotheses)}")
        for i, h in enumerate(hypotheses, 1):
            self.trace.append(f"  {i}. {h}")
        
        # Step 3: VERIFY (可迭代)
        self.trace.append("\n" + "=" * 50)
        self.trace.append("Step 3: VERIFY - 验证假设")
        self.trace.append("=" * 50)
        
        verification_results = []
        for iteration in range(self.max_iterations):
            self.trace.append(f"\n--- 迭代 {iteration + 1} ---")
            
            if not hypotheses:
                self.trace.append("没有更多假设需要验证")
                break
            
            results, remaining_hypotheses = self._verify(pr, hypotheses)
            verification_results.extend(results)
            
            if not remaining_hypotheses:
                self.trace.append("所有假设已验证")
                break
            
            # 更新假设列表，继续下一轮
            hypotheses = remaining_hypotheses
        
        self.trace.append(f"\n验证结果数量：{len(verification_results)}")
        
        # Step 4: CONCLUDE
        self.trace.append("\n" + "=" * 50)
        self.trace.append("Step 4: CONCLUDE - 生成结论")
        self.trace.append("=" * 50)
        
        result = self._conclude(pr, verification_results)
        result.reasoning_trace = self.trace.copy()
        
        return result

    def _read(self, pr: PR) -> Dict[str, Any]:
        """READ 阶段：理解代码"""
        # 构建代码变更摘要
        code_summary = self._build_code_summary(pr)
        
        print(f"\n📖 READ 阶段：分析代码变更")
        print(f"   变更文件数：{len(pr.changes)}")
        
        messages = [
            {"role": "system", "content": self.READ_SYSTEM},
            {"role": "user", "content": f"请分析以下代码变更：\n\n{code_summary}"}
        ]
        
        response = self.llm_client.chat(messages, show_progress=True)
        
        print(f"   ✅ 分析完成")
        print(f"   关键发现预览：{response[:200]}...")
        
        # 解析响应
        return {
            "raw_response": response,
            "code_summary": code_summary
        }

    def _hypothesize(self, pr: PR, read_result: Dict[str, Any]) -> List[str]:
        """HYPOTHESIZE 阶段：提出假设"""
        print(f"\n💡 HYPOTHESIZE 阶段：提出缺陷假设")
        
        messages = [
            {"role": "system", "content": self.HYPOTHESIZE_SYSTEM},
            {"role": "user", "content": f"""基于以下代码分析，提出可能的缺陷假设：

代码摘要：
{read_result.get('code_summary', '')}

分析结果：
{read_result.get('raw_response', '')[:1000]}

请列出最多 5 个可验证的假设。"""}
        ]
        
        response = self.llm_client.chat(messages, show_progress=True)
        
        # 提取假设（每行一个）
        hypotheses = []
        for line in response.split('\n'):
            line = line.strip()
            if line and any(line.startswith(p) for p in ['1.', '2.', '3.', '4.', '5.', '-']):
                # 移除序号
                line = line.lstrip('1234567890.-').strip()
                if line:
                    hypotheses.append(line)
        
        print(f"   ✅ 提出 {len(hypotheses)} 个假设：")
        for i, h in enumerate(hypotheses[:3], 1):
            print(f"      {i}. {h[:80]}{'...' if len(h) > 80 else ''}")
        if len(hypotheses) > 3:
            print(f"      ... 还有 {len(hypotheses) - 3} 个假设")
        
        return hypotheses[:5]

    def _verify(self, pr: PR, hypotheses: List[str]) -> Tuple[List[Dict[str, Any]], List[str]]:
        """VERIFY 阶段：验证假设"""
        print(f"\n🔍 VERIFY 阶段：验证 {len(hypotheses)} 个假设")
        
        results = []
        remaining = []
        
        for i, hypothesis in enumerate(hypotheses, 1):
            print(f"\n   [{i}/{len(hypotheses)}] 验证：{hypothesis[:60]}...")
            self.trace.append(f"\n验证假设：{hypothesis}")
            
            # 提取关键词进行搜索
            keywords = self._extract_search_keywords(hypothesis)
            print(f"   关键词：{', '.join(keywords[:3])}")
            
            evidence = []
            for keyword in keywords[:3]:
                print(f"     🔎 搜索 '{keyword}'...", end=" ")
                tool_result = self.tool_agent.execute_tool(
                    "code_search",
                    {"pattern": keyword}
                )
                
                if tool_result.success and tool_result.result:
                    evidence.extend(tool_result.result[:2])
                    print(f"✅ 找到 {len(tool_result.result)} 个结果")
                    self.trace.append(f"  搜索 '{keyword}': 找到 {len(tool_result.result)} 个结果")
                    break
                else:
                    print("❌ 无结果")
            
            if evidence:
                results.append({
                    "hypothesis": hypothesis,
                    "evidence": evidence,
                    "verified": True
                })
                print(f"   ✅ 假设已验证（找到证据）")
            else:
                # 没有找到证据，保留假设进行下一轮
                remaining.append(hypothesis)
                print(f"   ⏸️ 未找到直接证据，留待下一轮")
        
        print(f"\n   📊 验证完成：{len(results)} 个已验证，{len(remaining)} 个待验证")
        return results, remaining

    def _conclude(self, pr: PR, verification_results: List[Dict[str, Any]]) -> ReviewResult:
        """CONCLUDE 阶段：生成结论"""
        print(f"\n📝 CONCLUDE 阶段：生成评审报告")
        
        # 构建结论提示词
        evidence_summary = ""
        for vr in verification_results:
            evidence_summary += f"假设：{vr['hypothesis']}\n"
            evidence_summary += f"证据：{len(vr['evidence'])} 条\n\n"
        
        messages = [
            {"role": "system", "content": self.CONCLUDE_SYSTEM},
            {"role": "user", "content": f"""基于以下验证结果，生成最终评审报告：

验证结果：
{evidence_summary}

请输出 JSON 格式的评审结果：
{{
    "issues": [
        {{
            "issue_type": "问题类型",
            "severity": "critical|high|medium|low",
            "message": "问题描述",
            "file_path": "文件路径",
            "line_number": 行号，
            "evidence": ["证据"],
            "suggestion": "修复建议"
        }}
    ],
    "summary": "总结"
}}"""}
        ]
        
        response = self.llm_client.chat(messages, show_progress=True)
        
        # 解析响应
        result = self._parse_response(response, pr.pr_id)
        
        print(f"   ✅ 评审完成，发现 {len(result.issues)} 个问题")
        return result

    def _build_code_summary(self, pr: PR) -> str:
        """构建代码变更摘要"""
        summary = f"PR: {pr.title}\n"
        summary += f"目标分支：{pr.target_branch}\n"
        summary += f"变更文件数：{len(pr.changes)}\n\n"
        
        for change in pr.changes:
            summary += f"文件：{change.file_path}\n"
            summary += f"变更行数：{change.diff.count('\\n')}\n"
            # 只显示 diff 的关键部分
            added = [l for l in change.diff.split('\n') if l.startswith('+') and not l.startswith('+++')]
            removed = [l for l in change.diff.split('\n') if l.startswith('-') and not l.startswith('---')]
            summary += f"新增：{len(added)} 行，删除：{len(removed)} 行\n\n"
        
        return summary

    def _extract_search_keywords(self, hypothesis: str) -> List[str]:
        """从假设中提取搜索关键词"""
        import re
        
        keywords = []
        
        # 提取英文标识符
        identifiers = re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_]*\b', hypothesis)
        keywords.extend([i for i in identifiers if len(i) > 2])
        
        # 提取中文关键词
        chinese = re.findall(r'[\u4e00-\u9fff]{2,}', hypothesis)
        keywords.extend(chinese)
        
        # 去重
        return list(set(keywords))[:5]

    def _parse_response(self, response: str, pr_id: str) -> ReviewResult:
        """解析 LLM 响应"""
        result = ReviewResult(pr_id=pr_id)
        
        json_data = self.llm_client.extract_json(response)
        
        if not json_data:
            result.summary = "评审完成（解析响应失败）"
            return result
        
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

    def get_trace(self) -> List[str]:
        """获取推理轨迹"""
        return self.trace