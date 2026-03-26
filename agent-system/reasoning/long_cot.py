"""
Long CoT 推理引擎
实现 READ -> HYPOTHESIZE -> VERIFY -> CONCLUDE 推理循环
"""
import json
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple

import sys
sys.path.insert(0, '.')

from models import PR, Context, ReviewResult, ReviewIssue, RiskLevel
from llm.client import LLMClient
from agents.tool_agent import ToolAgent
from config.settings import config


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

    KEYWORDS_SYSTEM = """你是代码检索策略助手。
你的任务是把“缺陷假设”转换成适合在代码库里搜索的关键词/正则片段。

规则：
1) 只输出 JSON，不要输出任何解释或 Markdown
2) keywords 内每个元素应是“可能在代码中原样出现”的短字符串（标识符/函数名/配置键/错误信息片段/常见 API 名等）
3) 优先给出更具体、更可能命中的词；避免过泛词（如 data、info、value）
4) 最多 8 个关键词

输出格式：
{
    "keywords": ["...", "..."]
}
"""

    VERIFY_EVAL_SYSTEM = """你是代码缺陷验证专家。
你会收到：一个“缺陷假设”以及在代码库里搜索到的若干条证据（文件路径、行号、命中行内容）。

任务：基于证据判断该假设是：confirmed（证据支持）、rejected（证据反驳/明显不成立）、inconclusive（证据不足）。

要求：
1) 只输出 JSON，不要输出任何解释性文字或 Markdown
2) 结论必须由 evidence 引用支撑；如果证据不足，选 inconclusive
3) next_keywords 只能是“下一步更可能命中的搜索词/符号/字符串片段”，最多 5 个

输出格式：
{
  "status": "confirmed|rejected|inconclusive",
  "confidence": 0.0,
  "reason": "...",
  "next_keywords": ["...", "..."]
}
"""

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
        self._keyword_cache: Dict[str, List[str]] = {}

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
        run_trace: List[Dict[str, Any]] = []
        run_trace.append({
            "type": "run_start",
            "ts": datetime.now().isoformat(),
            "engine": "LongCoT",
            "model": getattr(self.llm_client, "model", None),
            "pr_id": pr.pr_id,
            "title": pr.title,
            "changed_files": [c.file_path for c in pr.changes],
        })
        
        # Step 1: READ
        self.trace.append("=" * 50)
        self.trace.append("Step 1: READ - 理解代码")
        self.trace.append("=" * 50)
        
        read_result = self._read(pr, context, run_trace)
        self.trace.append(f"READ 结果：{json.dumps(read_result, ensure_ascii=False)[:500]}")
        
        # Step 2: HYPOTHESIZE
        self.trace.append("\n" + "=" * 50)
        self.trace.append("Step 2: HYPOTHESIZE - 提出假设")
        self.trace.append("=" * 50)
        
        hypotheses = self._hypothesize(pr, read_result, run_trace)
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
            
            results, remaining_hypotheses = self._verify(pr, hypotheses, run_trace)
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
        
        result = self._conclude(pr, verification_results, run_trace)
        result.reasoning_trace = self.trace.copy()
        result.run_trace = run_trace
        run_trace.append({
            "type": "run_end",
            "ts": datetime.now().isoformat(),
            "issues": len(result.issues),
            "summary": result.summary,
        })
        
        return result

    def _read(self, pr: PR, context: Optional[Context], run_trace: List[Dict[str, Any]]) -> Dict[str, Any]:
        """READ 阶段：理解代码"""
        # 构建给 LLM 的输入：包含真实 diff（按预算截断）+ 可选 Context
        code_summary = self._build_code_summary(pr, context)
        
        print(f"\n📖 READ 阶段：分析代码变更")
        print(f"   变更文件数：{len(pr.changes)}")
        
        messages = [
            {"role": "system", "content": self.READ_SYSTEM},
            {"role": "user", "content": f"请分析以下代码变更：\n\n{code_summary}"}
        ]

        response = self.llm_client.chat(
            messages,
            show_progress=True,
            trace=run_trace,
            trace_meta={"stage": "READ"},
        )
        
        print(f"   ✅ 分析完成")
        print(f"   关键发现预览：{response[:200]}...")
        
        # 解析响应
        return {
            "raw_response": response,
            "code_summary": code_summary
        }

    def _truncate_middle(self, text: str, max_chars: int) -> str:
        if text is None:
            return ""
        text = str(text)
        if max_chars <= 0 or len(text) <= max_chars:
            return text
        # 保留头尾，避免只截断到前面导致丢失后续 hunk
        head_len = max_chars // 2
        tail_len = max_chars - head_len
        return text[:head_len] + "\n...<truncated>...\n" + text[-tail_len:]

    def _hypothesize(self, pr: PR, read_result: Dict[str, Any], run_trace: List[Dict[str, Any]]) -> List[str]:
        """HYPOTHESIZE 阶段：提出假设"""
        print(f"\n💡 HYPOTHESIZE 阶段：提出缺陷假设")
        
        messages = [
                        {"role": "system", "content": self.HYPOTHESIZE_SYSTEM},
                        {"role": "user", "content": f"""基于以下代码分析，提出可能的缺陷假设。

代码摘要：
{read_result.get('code_summary', '')}

分析结果：
{read_result.get('raw_response', '')[:1000]}

要求：
1) 最多 5 个假设；每个假设必须可验证（能通过搜索/测试/日志/静态分析验证）
2) 请严格输出 JSON，不要输出任何 Markdown/解释性文字

输出格式：
{{
    "hypotheses": [
        "...",
        "..."
    ]
}}"""}
                ]
        
        response = self.llm_client.chat(
            messages,
            show_progress=True,
            trace=run_trace,
            trace_meta={"stage": "HYPOTHESIZE"},
        )
        
        hypotheses = self._extract_hypotheses(response)
        
        print(f"   ✅ 提出 {len(hypotheses)} 个假设：")
        for i, h in enumerate(hypotheses[:3], 1):
            print(f"      {i}. {h[:80]}{'...' if len(h) > 80 else ''}")
        if len(hypotheses) > 3:
            print(f"      ... 还有 {len(hypotheses) - 3} 个假设")
        
        return hypotheses[:5]

    def _extract_hypotheses(self, response: str) -> List[str]:
        """从 LLM 输出中抽取假设列表。

        优先解析 JSON，其次兼容 Markdown（### 1. ... + **假设：** ...）。
        """
        hypotheses: List[str] = []

        json_data = self.llm_client.extract_json(response)
        if isinstance(json_data, dict):
            raw = json_data.get("hypotheses")
            if isinstance(raw, list):
                hypotheses = [self._clean_hypothesis_text(x) for x in raw if isinstance(x, str) and x.strip()]
        elif isinstance(json_data, list):
            hypotheses = [self._clean_hypothesis_text(x) for x in json_data if isinstance(x, str) and x.strip()]

        if not hypotheses:
            hypotheses = self._extract_hypotheses_fallback(response)

        # 去重并保持顺序
        seen = set()
        unique: List[str] = []
        for h in hypotheses:
            if not h:
                continue
            key = h.lower()
            if key in seen:
                continue
            seen.add(key)
            unique.append(h)
        return unique[:5]

    def _extract_hypotheses_fallback(self, response: str) -> List[str]:
        import re

        lines = response.splitlines()

        # 1) 优先抓每段里的“假设：...”行（最贴近你给的例子）
        hypothesis_line_re = re.compile(r"^\s*(?:\*\*?)?假设(?:\*\*?)?\s*[:：]\s*(.+?)\s*$")
        out: List[str] = []
        for line in lines:
            m = hypothesis_line_re.match(line)
            if not m:
                continue
            out.append(self._clean_hypothesis_text(m.group(1)))
        if out:
            return out

        # 2) 兼容标题行："### 1. ..." / "1. ..." / "- ..."
        heading_re = re.compile(r"^\s*(?:#{1,6}\s*)?(\d+)\.(.+)$")
        bullet_re = re.compile(r"^\s*[-*]\s+(.+)$")
        for line in lines:
            line = line.strip()
            if not line:
                continue
            m = heading_re.match(line)
            if m:
                out.append(self._clean_hypothesis_text(m.group(2)))
                continue
            m = bullet_re.match(line)
            if m:
                out.append(self._clean_hypothesis_text(m.group(1)))
        return out

    def _clean_hypothesis_text(self, text: str) -> str:
        import re

        s = str(text).strip()
        if not s:
            return ""
        # 去掉常见 Markdown 噪音
        s = re.sub(r"^\s*#+\s*", "", s)
        s = s.replace("**", "").replace("__", "")
        # 删除多余空白
        s = re.sub(r"\s+", " ", s)
        # 去掉前缀序号/标点
        s = s.lstrip("-•*\t ")
        s = re.sub(r"^\d+\s*[.)、]\s*", "", s)
        return s.strip()

    def _verify(self, pr: PR, hypotheses: List[str], run_trace: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[str]]:
        """VERIFY 阶段：验证假设"""
        print(f"\n🔍 VERIFY 阶段：验证 {len(hypotheses)} 个假设")
        
        results = []
        remaining = []
        
        for i, hypothesis in enumerate(hypotheses, 1):
            print(f"\n   [{i}/{len(hypotheses)}] 验证：{hypothesis[:60]}...")
            self.trace.append(f"\n验证假设：{hypothesis}")
            
            # 提取关键词进行搜索
            keywords = self._extract_search_keywords(hypothesis, run_trace)
            print(f"   关键词：{', '.join(keywords[:3])}")
            
            evidence: List[Dict[str, Any]] = []
            evidence_seen = set()
            max_keywords_to_try = 3
            max_evidence_items = 10

            for keyword in keywords[:max_keywords_to_try]:
                print(f"     🔎 搜索 '{keyword}'...", end=" ")

                run_trace.append({
                    "type": "tool_request",
                    "ts": datetime.now().isoformat(),
                    "tool": "code_search",
                    "arguments": {"pattern": keyword},
                    "meta": {"stage": "VERIFY", "hypothesis": hypothesis},
                })

                tool_result = self.tool_agent.execute_tool("code_search", {"pattern": keyword})

                run_trace.append({
                    "type": "tool_response",
                    "ts": datetime.now().isoformat(),
                    "tool": "code_search",
                    "success": tool_result.success,
                    "error": tool_result.error,
                    "result": tool_result.result,
                    "meta": {"stage": "VERIFY", "hypothesis": hypothesis},
                })
                
                if tool_result.success and tool_result.result:
                    added_count = 0
                    for item in tool_result.result[:10]:
                        if not isinstance(item, dict):
                            continue
                        key = (item.get("file"), item.get("line"), item.get("content"))
                        if key in evidence_seen:
                            continue
                        evidence_seen.add(key)
                        evidence.append(item)
                        added_count += 1
                        if len(evidence) >= max_evidence_items:
                            break

                    print(f"✅ 找到 {len(tool_result.result)} 个结果 (+{added_count} 采样)")
                    self.trace.append(
                        f"  搜索 '{keyword}': 找到 {len(tool_result.result)} 个结果，采样 {added_count} 条证据"
                    )

                    if len(evidence) >= max_evidence_items:
                        break
                else:
                    print("❌ 无结果")

            # 将“单行命中”升级为“函数级上下文”（只 enrich 前几条，避免爆 prompt）
            max_scopes_to_attach = 3
            for item in evidence[:max_scopes_to_attach]:
                if not isinstance(item, dict):
                    continue
                if item.get("scope") is not None:
                    continue
                file_path = item.get("file")
                line_no = item.get("line")
                if not file_path or not line_no:
                    continue

                run_trace.append({
                    "type": "tool_request",
                    "ts": datetime.now().isoformat(),
                    "tool": "get_function_context",
                    "arguments": {"file_path": file_path, "line_number": line_no},
                    "meta": {"stage": "VERIFY", "hypothesis": hypothesis},
                })

                ctx_result = self.tool_agent.execute_tool(
                    "get_function_context",
                    {"file_path": file_path, "line_number": line_no},
                )

                run_trace.append({
                    "type": "tool_response",
                    "ts": datetime.now().isoformat(),
                    "tool": "get_function_context",
                    "success": ctx_result.success,
                    "error": ctx_result.error,
                    "result": ctx_result.result,
                    "meta": {"stage": "VERIFY", "hypothesis": hypothesis},
                })

                if ctx_result.success and ctx_result.result:
                    item["scope"] = ctx_result.result
            
            if not evidence:
                remaining.append(hypothesis)
                print(f"   ⏸️ 未找到直接证据，留待下一轮")
                continue

            # 用证据内容做一次“确认/推翻/不确定”的判定
            try:
                evaluation = self._evaluate_hypothesis_with_evidence(hypothesis, evidence, run_trace)
            except Exception as e:
                evaluation = {
                    "status": "inconclusive",
                    "confidence": 0.0,
                    "reason": f"LLM verification error: {e}",
                    "next_keywords": [],
                }

            status = str(evaluation.get("status", "inconclusive"))
            if status == "confirmed":
                results.append({
                    "hypothesis": hypothesis,
                    "evidence": evidence,
                    "verified": True,
                    "evaluation": evaluation,
                })
                print(f"   ✅ 假设已确认（证据支持）")
                self.trace.append(f"  验证结论：confirmed | {evaluation.get('reason', '')}")
            elif status == "rejected":
                print(f"   ❌ 假设被推翻（证据反驳/不成立）")
                self.trace.append(f"  验证结论：rejected | {evaluation.get('reason', '')}")
            else:
                remaining.append(hypothesis)
                print(f"   ⏸️ 证据不足，保留到下一轮")
                self.trace.append(f"  验证结论：inconclusive | {evaluation.get('reason', '')}")

                nk = evaluation.get("next_keywords")
                if isinstance(nk, list) and nk:
                    prev = self._keyword_cache.get(hypothesis, keywords)
                    merged: List[str] = []
                    seen = set()
                    for k in (nk + prev):
                        k = self._clean_keyword(k)
                        if not k:
                            continue
                        key = k.lower()
                        if key in seen:
                            continue
                        seen.add(key)
                        merged.append(k)
                    self._keyword_cache[hypothesis] = merged[:8]
        
        print(f"\n   📊 验证完成：{len(results)} 个已验证，{len(remaining)} 个待验证")
        return results, remaining

    def _conclude(self, pr: PR, verification_results: List[Dict[str, Any]], run_trace: List[Dict[str, Any]]) -> ReviewResult:
        """CONCLUDE 阶段：生成结论"""
        print(f"\n📝 CONCLUDE 阶段：生成评审报告")
        
        # 构建结论提示词
        evidence_summary = ""
        for vr in verification_results:
            hyp = vr.get("hypothesis", "")
            ev = vr.get("evidence", [])
            evaluation = vr.get("evaluation")

            evidence_summary += f"假设：{hyp}\n"
            if isinstance(evaluation, dict) and evaluation.get("reason"):
                evidence_summary += f"验证理由：{evaluation.get('reason')}\n"
            if isinstance(ev, list):
                evidence_summary += f"证据：{len(ev)} 条（采样如下）\n"
                evidence_summary += self._summarize_evidence_for_llm(ev, max_items=6) + "\n"
            evidence_summary += "\n"
        
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
        
        response = self.llm_client.chat(
            messages,
            show_progress=True,
            trace=run_trace,
            trace_meta={"stage": "CONCLUDE"},
        )
        
        # 解析响应
        result = self._parse_response(response, pr.pr_id)
        
        print(f"   ✅ 评审完成，发现 {len(result.issues)} 个问题")
        return result

    def _build_code_summary(self, pr: PR, context: Optional[Context]) -> str:
        """构建代码变更摘要（用于喂给 LLM）。

        注意：这里必须包含真实 diff（至少关键片段），否则 READ 阶段无法做代码级理解。
        """
        # 经验：token 预算转字符预算做近似（中英文混合时较粗，但足够防止爆 prompt）
        total_budget_chars = max(8000, min(60000, int(getattr(config.review, "max_context_tokens", 8000) * 4)))
        per_file_budget_chars = max(2000, min(12000, total_budget_chars // max(1, len(pr.changes))))

        parts: List[str] = []
        parts.append(f"PR: {pr.title}")
        if pr.description:
            parts.append(f"描述: {self._truncate_middle(pr.description, 2000)}")
        parts.append(f"目标分支: {pr.target_branch}")
        parts.append(f"变更文件数: {len(pr.changes)}")

        if context:
            if context.related_files:
                parts.append("\n[Context.related_files]\n" + "\n".join(context.related_files[:50]))
            if context.checklist:
                parts.append("\n[Context.checklist]\n" + "\n".join([f"- {c}" for c in context.checklist[:50]]))
            if context.docs_context:
                parts.append("\n[Context.docs_context]\n" + self._truncate_middle(context.docs_context, 3000))
            if context.code_context:
                parts.append("\n[Context.code_context]\n" + self._truncate_middle(context.code_context, 6000))

        parts.append("\n[Diffs]")
        for change in pr.changes:
            diff_text = change.diff or ""
            # 如果 diff 为空，至少给出新旧内容（同样要限长）
            if not diff_text and (change.old_content or change.new_content):
                diff_text = "(no unified diff provided)\n" + "\n".join([
                    "--- old",
                    self._truncate_middle(change.old_content or "", per_file_budget_chars // 2),
                    "+++ new",
                    self._truncate_middle(change.new_content or "", per_file_budget_chars // 2),
                ])

            added = [l for l in diff_text.split("\n") if l.startswith("+") and not l.startswith("+++")]
            removed = [l for l in diff_text.split("\n") if l.startswith("-") and not l.startswith("---")]

            header = [
                f"\n=== {change.file_path} ===",
                f"新增: {len(added)} 行, 删除: {len(removed)} 行",
            ]
            parts.append("\n".join(header))
            parts.append("```diff\n" + self._truncate_middle(diff_text, per_file_budget_chars) + "\n```")

        full = "\n".join(parts)
        return self._truncate_middle(full, total_budget_chars)

    def _extract_search_keywords_regex(self, hypothesis: str) -> List[str]:
        import re

        keywords: List[str] = []

        # 提取英文标识符（变量/函数/类/常量）
        identifiers = re.findall(r"\b[a-zA-Z_][a-zA-Z0-9_]*\b", hypothesis)
        keywords.extend([i for i in identifiers if len(i) > 2])

        # 提取点号链（module.func / obj.attr）
        dotted = re.findall(r"\b[a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)+\b", hypothesis)
        keywords.extend(dotted)

        # 提取引号里的短文本（错误信息片段/配置 key 等）
        quoted = re.findall(r"['\"]([^'\"\n]{3,80})['\"]", hypothesis)
        keywords.extend([q.strip() for q in quoted if q.strip()])

        # 提取中文短语（代码里命中率较低，但对日志/注释仍可能有用）
        chinese = re.findall(r"[\u4e00-\u9fff]{2,}", hypothesis)
        keywords.extend(chinese)

        # 去重并保持顺序
        seen = set()
        out: List[str] = []
        for k in keywords:
            k = str(k).strip()
            if not k:
                continue
            key = k.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(k)
        return out[:8]

    def _clean_keyword(self, s: Any) -> str:
        import re

        if s is None:
            return ""
        text = str(s).strip()
        if not text:
            return ""
        text = text.replace("`", "").strip()
        # 压缩空白，避免把整句塞进来
        text = re.sub(r"\s+", " ", text)
        # 太长的直接丢弃（关键词应该短）
        if len(text) > 80:
            return ""
        return text

    def _summarize_evidence_for_llm(self, evidence: List[Dict[str, Any]], max_items: int = 6) -> str:
        lines: List[str] = []
        for item in evidence[:max_items]:
            if not isinstance(item, dict):
                continue
            file = str(item.get("file", ""))
            line = item.get("line", "")
            content = str(item.get("content", ""))
            if not file and not content:
                continue
            scope = item.get("scope")
            if isinstance(scope, dict) and scope.get("snippet"):
                scope_type = scope.get("scope_type", "scope")
                name = scope.get("name", "")
                ls = scope.get("line_start", "")
                le = scope.get("line_end", "")
                truncated = scope.get("truncated", False)
                head = f"- {file}:{line} | in {scope_type} {name} [{ls}-{le}]"
                if truncated:
                    head += " (truncated)"
                lines.append(head)
                lines.append(scope.get("snippet", ""))
            else:
                lines.append(f"- {file}:{line} | {content}")
        return "\n".join(lines)

    def _evaluate_hypothesis_with_evidence(
        self,
        hypothesis: str,
        evidence: List[Dict[str, Any]],
        run_trace: Optional[List[Dict[str, Any]]],
    ) -> Dict[str, Any]:
        evidence_text = self._summarize_evidence_for_llm(evidence)
        messages = [
            {"role": "system", "content": self.VERIFY_EVAL_SYSTEM},
            {
                "role": "user",
                "content": f"""假设：\n{hypothesis}\n\n证据（search 命中）：\n{evidence_text}\n\n请输出严格 JSON。""",
            },
        ]

        response = self.llm_client.chat(
            messages,
            show_progress=False,
            trace=run_trace,
            trace_meta={"stage": "VERIFY_EVAL", "hypothesis": hypothesis[:200]},
        )

        json_data = self.llm_client.extract_json(response)
        if isinstance(json_data, dict):
            status = json_data.get("status")
            if status in ("confirmed", "rejected", "inconclusive"):
                return json_data

        return {
            "status": "inconclusive",
            "confidence": 0.0,
            "reason": "LLM verification output parse failed",
            "next_keywords": [],
        }

    def _extract_search_keywords_llm(self, hypothesis: str, run_trace: Optional[List[Dict[str, Any]]]) -> List[str]:
        """用 LLM 生成更适合代码搜索的关键词。

        注意：LLM 可能产生“命中率低/不存在”的词，因此这里返回的是候选集，后续会通过 code_search 自然淘汰。
        """
        messages = [
            {"role": "system", "content": self.KEYWORDS_SYSTEM},
            {
                "role": "user",
                "content": f"""缺陷假设：\n{hypothesis}\n\n请输出 JSON：{{\"keywords\": [..]}}""",
            },
        ]

        response = self.llm_client.chat(
            messages,
            show_progress=False,
            trace=run_trace,
            trace_meta={"stage": "KEYWORDS", "hypothesis": hypothesis[:200]},
        )

        json_data = self.llm_client.extract_json(response)
        if isinstance(json_data, dict):
            raw = json_data.get("keywords")
            if isinstance(raw, list):
                cleaned = [self._clean_keyword(x) for x in raw]
                return [c for c in cleaned if c]
        elif isinstance(json_data, list):
            cleaned = [self._clean_keyword(x) for x in json_data]
            return [c for c in cleaned if c]

        return []

    def _extract_search_keywords(self, hypothesis: str, run_trace: Optional[List[Dict[str, Any]]] = None) -> List[str]:
        """从假设中提取搜索关键词（LLM 优先，规则回退）。

        目标：宁可多给一些候选词，也不要只给“中文语义句子”。
        """
        hypothesis = str(hypothesis or "").strip()
        if not hypothesis:
            return []

        cached = self._keyword_cache.get(hypothesis)
        if cached is not None:
            return cached

        # 规则先给一组“保底可解释”的关键词
        regex_keywords = self._extract_search_keywords_regex(hypothesis)

        llm_keywords: List[str] = []
        try:
            llm_keywords = self._extract_search_keywords_llm(hypothesis, run_trace)
        except Exception:
            llm_keywords = []

        # 合并：LLM 在前（通常更贴近“该搜什么”），规则在后（提供确定锚点）
        merged: List[str] = []
        seen = set()
        for k in (llm_keywords + regex_keywords):
            k = self._clean_keyword(k)
            if not k:
                continue
            key = k.lower()
            if key in seen:
                continue
            seen.add(key)
            merged.append(k)

        # 如果 LLM 没产出且规则也很差，最后再给一个“整句子里挑出的长词”保底
        if not merged:
            merged = regex_keywords

        out = merged[:8]
        self._keyword_cache[hypothesis] = out
        return out

    def _parse_response(self, response: str, pr_id: str) -> ReviewResult:
        """解析 LLM 响应"""
        result = ReviewResult(pr_id=pr_id)
        
        json_data = self.llm_client.extract_json(response)
        
        if not json_data or not isinstance(json_data, dict):
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