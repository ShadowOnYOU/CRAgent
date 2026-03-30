"""
评审过滤器
实现 LLM-as-Judge 过滤逻辑
"""
from __future__ import annotations

import os
import re
from dataclasses import replace
from typing import List, Optional, Set, Tuple

import sys
sys.path.insert(0, '.')

from models import ReviewResult, ReviewIssue, RiskLevel
from llm.client import LLMClient
from models import PR


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

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        root_path: Optional[str] = None,
    ):
        """
        初始化过滤器
        
        Args:
            llm_client: LLM 客户端（可选，用于 LLM 过滤）
        """
        self.llm_client = llm_client
        self.root_path = root_path
    
    def filter(
        self,
        result: ReviewResult,
        min_severity: RiskLevel = RiskLevel.LOW,
        min_confidence: float = 0.3,
        pr: Optional[PR] = None,
        root_path: Optional[str] = None,
        strict_facts: bool = False,
    ) -> ReviewResult:
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
            reasoning_trace=result.reasoning_trace,
            run_trace=result.run_trace
        )

        effective_root = root_path if root_path is not None else self.root_path
        
        # 严重级别映射
        severity_order = {
            RiskLevel.LOW: 0,
            RiskLevel.MEDIUM: 1,
            RiskLevel.HIGH: 2,
            RiskLevel.CRITICAL: 3
        }
        
        min_sev_value = severity_order.get(min_severity, 0)
        
        for issue in result.issues:
            # L3 事实校验与强约束：防止 file/line/evidence 幻觉
            if strict_facts:
                checked_issue = self._apply_fact_checks(issue, pr=pr, root_path=effective_root)
                if checked_issue is None:
                    continue
                issue = checked_issue

            # 检查严重级别
            issue_sev_value = severity_order.get(issue.severity, 0)
            if issue_sev_value < min_sev_value:
                continue
            
            # 检查置信度
            # 仅在 strict_facts 模式启用：让“降级置信度”真正触发剔除
            if strict_facts and issue.confidence < min_confidence:
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
    
    def filter_with_llm(
        self,
        result: ReviewResult,
        pr: Optional[PR] = None,
        root_path: Optional[str] = None,
        strict_facts: bool = False,
    ) -> ReviewResult:
        """
        使用 LLM 进行智能过滤
        
        Args:
            result: 原始评审结果
            
        Returns:
            过滤后的结果
        """
        if not self.llm_client:
            return self.filter(result, pr=pr, root_path=root_path, strict_facts=strict_facts)

        # 先做事实校验（可选），避免把“不可定位/无证据”提交给 LLM
        if strict_facts:
            result = self.filter(
                result,
                min_severity=RiskLevel.LOW,
                min_confidence=0.0,
                pr=pr,
                root_path=root_path,
                strict_facts=True,
            )
        
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
            reasoning_trace=result.reasoning_trace,
            run_trace=result.run_trace
        )
        
        for i, issue in enumerate(result.issues, 1):
            if i in keep_indices:
                filtered.issues.append(issue)
        
        filtered.summary = f"经过 LLM 评估，保留 {len(filtered.issues)} 个高价值问题"
        return filtered

    def _apply_fact_checks(
        self,
        issue: ReviewIssue,
        pr: Optional[PR],
        root_path: Optional[str],
    ) -> Optional[ReviewIssue]:
        """对单条 issue 执行事实校验。

        规则（严格模式）：
        - file_path 非法/不可定位 -> 剔除
        - line_number 非法/不可定位 -> 剔除
        - evidence 为空或无法在文件/PR diff 中复现 -> 降级到低置信度（通常会被后续 min_confidence 剔除）
        """
        normalized_path = self._normalize_issue_file_path(issue.file_path, root_path)
        if normalized_path is None:
            return None

        issue = replace(issue, file_path=normalized_path)

        if not self._is_safe_relpath(issue.file_path):
            return None

        if issue.line_number <= 0:
            return None

        file_text = self._try_read_file(root_path, issue.file_path)

        # 1) file/line 的“存在性与范围”校验
        if file_text is not None:
            if not self._is_line_in_file(file_text, issue.line_number):
                return None
        else:
            # 文件不在磁盘上：允许退化到 PR diff 的 hunk 新文件行范围校验
            if pr is not None:
                change = self._find_change_for_file(pr, issue.file_path)
                if change is None:
                    return None

                if not self._is_line_in_diff_hunks(change.diff, issue.line_number):
                    # 能找到文件但无法定位到任何 hunk：降级而非立刻剔除
                    issue = replace(issue, confidence=min(issue.confidence, 0.4))
            else:
                # 没有 PR 信息也无法读文件，无法验证行号
                issue = replace(issue, confidence=min(issue.confidence, 0.4))

        # 2) evidence 可复现校验
        if not issue.evidence:
            return replace(issue, confidence=0.0)

        searchable_texts: List[str] = []
        if file_text is not None:
            searchable_texts.append(file_text)

        if pr is not None:
            change = self._find_change_for_file(pr, issue.file_path)
            if change is not None:
                searchable_texts.append(change.diff or "")
                # parse_diff 生成的 new_content 对“无磁盘文件”的场景更友好
                searchable_texts.append(change.new_content or "")

        if not self._evidence_is_reproducible(issue.evidence, searchable_texts):
            return replace(issue, confidence=min(issue.confidence, 0.3))

        return issue

    def _normalize_issue_file_path(self, path: str, root_path: Optional[str]) -> Optional[str]:
        """把模型/工具产出的路径归一化为仓库内的相对路径。

        允许：
        - 去掉 diff 常见前缀：a/、b/
        - 去掉 ./
        - 若传入的是“root_path 内的绝对路径”，转换为相对路径

        仍然拒绝：
        - root_path 之外的绝对路径
        - 非法/空路径
        """
        if not path or not isinstance(path, str):
            return None

        p = path.strip().replace("\\", "/")
        if not p:
            return None

        while p.startswith("./"):
            p = p[2:]

        # 若模型返回的路径包含 root 目录名前缀（如 sample-lib/src/...），则剥掉该前缀
        if root_path:
            try:
                abs_root = os.path.abspath(root_path)
                root_name = os.path.basename(abs_root.rstrip(os.sep))
                if root_name and p.startswith(root_name + "/"):
                    candidate = p[len(root_name) + 1 :]
                    # 仅当 candidate 在 root 下确实存在时才采用，避免误剥
                    if os.path.exists(os.path.join(abs_root, candidate)):
                        p = candidate
            except Exception:
                pass

        if p.startswith("a/") or p.startswith("b/"):
            p = p[2:]

        if p in ("", ".", "/"):
            return None

        # 如果是绝对路径，且落在 root_path 下，则转成相对路径
        if os.path.isabs(p):
            if not root_path:
                return None
            try:
                abs_root = os.path.abspath(root_path)
                abs_p = os.path.abspath(p)
                if os.path.commonpath([abs_root, abs_p]) != abs_root:
                    return None
                p = os.path.relpath(abs_p, abs_root).replace("\\", "/")
            except Exception:
                return None

        # 统一路径形式（不在此处做安全拒绝，留给 _is_safe_relpath 处理）
        p = os.path.normpath(p).replace("\\", "/")
        if p in ("", "."):
            return None

        return p

    def _is_safe_relpath(self, path: str) -> bool:
        if not path or not isinstance(path, str):
            return False
        if os.path.isabs(path):
            return False
        # 归一化后拒绝上跳路径
        norm = os.path.normpath(path).replace("\\", "/")
        if norm.startswith("../") or norm == "..":
            return False
        return True

    def _try_read_file(self, root_path: Optional[str], file_path: str) -> Optional[str]:
        if not root_path:
            return None
        try:
            abs_root = os.path.abspath(root_path)
            abs_file = os.path.abspath(os.path.join(abs_root, file_path))
            # 防路径穿越
            if os.path.commonpath([abs_root, abs_file]) != abs_root:
                return None
            if not os.path.isfile(abs_file):
                return None
            with open(abs_file, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()
        except Exception:
            return None

    def _is_line_in_file(self, file_text: str, line_number: int) -> bool:
        if line_number <= 0:
            return False
        # splitlines() 不保留末尾空行；对行号范围校验够用
        return line_number <= len(file_text.splitlines())

    def _find_change_for_file(self, pr: PR, file_path: str):
        for c in getattr(pr, "changes", []) or []:
            if c.file_path == file_path:
                return c
        return None

    def _is_line_in_diff_hunks(self, diff_text: str, line_number: int) -> bool:
        """判断行号是否落在 unified diff 的任意一个 new-file hunk 范围内。"""
        if not diff_text:
            return False

        # @@ -oldStart,oldCount +newStart,newCount @@
        hunk_re = re.compile(r"^@@\s+-(\d+)(?:,(\d+))?\s+\+(\d+)(?:,(\d+))?\s+@@", re.M)
        for m in hunk_re.finditer(diff_text):
            new_start = int(m.group(3))
            new_count = int(m.group(4) or "1")
            new_end = new_start + max(new_count, 0) - 1
            if new_start <= line_number <= new_end:
                return True
        return False

    def _normalize_for_search(self, text: str) -> str:
        # 去掉常见包装，压缩空白
        text = text.strip()
        text = re.sub(r"^```[a-zA-Z0-9_+-]*\n|\n```$", "", text)
        text = text.replace("\r\n", "\n")
        text = re.sub(r"\s+", " ", text)
        return text

    def _extract_evidence_fragments(self, evidence: str) -> List[str]:
        if not evidence:
            return []
        raw = evidence.strip()
        if not raw:
            return []

        # 优先保留更像“代码行”的片段
        lines = [ln.strip("\n") for ln in raw.splitlines()]
        cleaned: List[str] = []
        for ln in lines:
            ln = ln.strip()
            if not ln:
                continue

            # 常见工具输出形态："path:line | code" —— 只取 code 部分用于复现匹配
            if "|" in ln:
                ln = ln.split("|", 1)[1].strip()
                if not ln:
                    continue
            # 去掉 diff/markdown 常见前缀
            ln = ln.lstrip("+- ")
            if len(ln) < 6:
                continue
            cleaned.append(ln)

        cleaned.sort(key=len, reverse=True)
        fragments = cleaned[:3]
        # 兜底：若没有足够行，则用整体（归一化后）
        if not fragments:
            fragments = [raw]
        return fragments

    def _evidence_is_reproducible(self, evidence_list: List[str], searchable_texts: List[str]) -> bool:
        if not searchable_texts:
            return False

        normalized_targets = [self._normalize_for_search(t) for t in searchable_texts if t]
        if not normalized_targets:
            return False

        for ev in evidence_list:
            for frag in self._extract_evidence_fragments(ev):
                frag_n = self._normalize_for_search(frag)
                if not frag_n:
                    continue
                if any(frag_n in target for target in normalized_targets):
                    return True
        return False
    
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