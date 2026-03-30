"""PR 解析器

负责解析和提取 PR 信息。

增强点：
- 支持 multi-hunk unified diff
- 构建 new_line -> diff_line 映射，用于更严格的事实定位
"""

import json
import re
from typing import Any, Dict, List, Optional, Tuple

import sys
sys.path.insert(0, '.')

from models import PR, CodeChange


class PRParser:
    """PR 解析器"""
    
    def __init__(self):
        pass
    
    def parse_diff(self, diff_text: str) -> List[CodeChange]:
        """
        解析 diff 文本
        
        Args:
            diff_text: Git diff 格式的文本
            
        Returns:
            CodeChange 列表
        """
        changes: List[CodeChange] = []
        current_file: Optional[str] = None
        current_diff_lines: List[str] = []

        lines = (diff_text or "").split("\n")

        def flush_current():
            nonlocal current_file, current_diff_lines
            if current_file and current_diff_lines:
                changes.append(self._create_code_change(current_file, current_diff_lines))
            current_file = None
            current_diff_lines = []

        for idx, line in enumerate(lines):
            # 1) 标准 git diff：以 diff --git 作为分隔
            if line.startswith("diff --git"):
                flush_current()
                # diff --git a/x b/y
                m = re.search(r"\sb/(\S+)$", line)
                if m:
                    current_file = m.group(1)
                current_diff_lines = [line]
                continue

            # 2) 非标准 diff（例如只包含 ---/+++/@@ 的片段）
            if line.startswith("--- ") and not current_diff_lines:
                # 开启一个新的 file block（文件名稍后由 +++ 校正）
                current_diff_lines = [line]
                # 尝试先从 --- a/... 推断
                m = re.search(r"---\s+(?:a/)?(.+)$", line)
                if m:
                    current_file = m.group(1).strip()
                continue

            if line.startswith("+++ "):
                if not current_diff_lines:
                    # 避免出现只有 +++ 的异常片段
                    current_diff_lines = [line]
                else:
                    current_diff_lines.append(line)

                m = re.search(r"\+\+\+\s+(?:b/)?(.+)$", line)
                if m:
                    current_file = m.group(1).strip()
                continue

            if current_diff_lines:
                current_diff_lines.append(line)

        flush_current()
        return changes
    
    def _create_code_change(self, file_path: str, diff_lines: List[str]) -> CodeChange:
        """创建 CodeChange 对象（支持多 hunk 与映射）。"""
        diff = "\n".join(diff_lines)

        # 解析 hunks，并构建 new_line -> diff_line（1-based）映射
        hunk_re = re.compile(r"^@@\s+-(\d+)(?:,(\d+))?\s+\+(\d+)(?:,(\d+))?\s+@@")

        diff_hunks: List[Dict[str, Any]] = []
        new_line_to_diff_line: Dict[int, int] = {}

        in_hunk = False
        current_old = 0
        current_new = 0
        current_hunk: Optional[Dict[str, Any]] = None

        old_content: List[str] = []
        new_content: List[str] = []

        def close_hunk(end_diff_line: int):
            nonlocal current_hunk
            if current_hunk is not None:
                current_hunk["diff_line_end"] = end_diff_line
                diff_hunks.append(current_hunk)
                current_hunk = None

        for i, line in enumerate(diff_lines):
            m = hunk_re.match(line)
            if m:
                # 关闭上一个 hunk
                if in_hunk:
                    # 上一个 hunk 结束在当前 header 的前一行：
                    # - 当前 header 行 index=i（0-based）
                    # - 前一行的 1-based 行号就是 i
                    close_hunk(i)

                old_start = int(m.group(1))
                old_count = int(m.group(2) or "1")
                new_start = int(m.group(3))
                new_count = int(m.group(4) or "1")

                current_old = old_start
                current_new = new_start
                in_hunk = True
                current_hunk = {
                    "old_start": old_start,
                    "old_count": old_count,
                    "new_start": new_start,
                    "new_count": new_count,
                    "diff_line_start": i + 1,
                    "diff_line_end": 0,
                }
                continue

            if not in_hunk:
                continue

            # 处理 hunk 内容行
            if not line:
                # 空行属于 context
                new_line_to_diff_line[current_new] = i + 1
                old_content.append("")
                new_content.append("")
                current_old += 1
                current_new += 1
                continue

            if line.startswith("\\ No newline"):
                continue

            prefix = line[0]
            payload = line[1:] if len(line) > 0 else ""

            if prefix == " ":
                new_line_to_diff_line[current_new] = i + 1
                old_content.append(payload)
                new_content.append(payload)
                current_old += 1
                current_new += 1
            elif prefix == "+":
                # 排除 +++
                if line.startswith("+++"):
                    continue
                new_line_to_diff_line[current_new] = i + 1
                new_content.append(payload)
                current_new += 1
            elif prefix == "-":
                # 排除 ---
                if line.startswith("---"):
                    continue
                old_content.append(payload)
                current_old += 1
            else:
                # 其它行（理论上不应出现在 hunk 内）按 context 处理
                new_line_to_diff_line[current_new] = i + 1
                old_content.append(line)
                new_content.append(line)
                current_old += 1
                current_new += 1

        # 关闭最后一个 hunk：最后一行的 1-based 行号为 len(diff_lines)
        if in_hunk:
            close_hunk(len(diff_lines))

        # 计算总体 new 行号范围（跨多 hunk）
        line_start = 0
        line_end = 0
        if diff_hunks:
            starts = [int(h.get("new_start") or 0) for h in diff_hunks if int(h.get("new_start") or 0) > 0]
            ends = []
            for h in diff_hunks:
                ns = int(h.get("new_start") or 0)
                nc = int(h.get("new_count") or 0)
                if ns <= 0:
                    continue
                ends.append(ns + max(nc, 0) - 1)
            line_start = min(starts) if starts else 0
            line_end = max(ends) if ends else 0

        return CodeChange(
            file_path=file_path,
            old_content="\n".join(old_content),
            new_content="\n".join(new_content),
            diff=diff,
            line_start=line_start,
            line_end=line_end,
            diff_hunks=diff_hunks,
            new_line_to_diff_line=new_line_to_diff_line,
        )
    
    def parse_pr_from_json(self, json_data: Dict[str, Any]) -> PR:
        """
        从 JSON 数据解析 PR
        
        Args:
            json_data: 包含 PR 信息的 JSON 数据
            
        Returns:
            PR 对象
        """
        pr = PR(
            pr_id=json_data.get("id", ""),
            title=json_data.get("title", ""),
            description=json_data.get("description", ""),
            author=json_data.get("author", ""),
            jira_ticket=json_data.get("jira_ticket", ""),
            target_branch=json_data.get("target_branch", "main"),
            source_branch=json_data.get("source_branch", ""),
            commit_history=json_data.get("commit_history", [])
        )
        
        # 解析变更
        if "diff" in json_data:
            pr.changes = self.parse_diff(json_data["diff"])
        
        if "changes" in json_data:
            for change_data in json_data["changes"]:
                pr.changes.append(CodeChange(
                    file_path=change_data.get("file_path", ""),
                    old_content=change_data.get("old_content", ""),
                    new_content=change_data.get("new_content", ""),
                    diff=change_data.get("diff", ""),
                    line_start=change_data.get("line_start", 0),
                    line_end=change_data.get("line_end", 0)
                ))
        
        return pr
    
    def parse_pr_from_github_format(self, title: str, body: str, 
                                     files: List[Dict[str, Any]]) -> PR:
        """
        从 GitHub 格式解析 PR
        
        Args:
            title: PR 标题
            body: PR 描述
            files: 文件变更列表
            
        Returns:
            PR 对象
        """
        pr = PR(
            pr_id="",
            title=title,
            description=body
        )
        
        for file_data in files:
            pr.changes.append(CodeChange(
                file_path=file_data.get("filename", ""),
                old_content=file_data.get("previous_contents", ""),
                new_content=file_data.get("contents", ""),
                diff=file_data.get("patch", ""),
                line_start=file_data.get("from_line", 0),
                line_end=file_data.get("to_line", 0)
            ))
        
        return pr
    
    def extract_keywords(self, pr: PR) -> List[str]:
        """
        从 PR 中提取关键词
        
        Args:
            pr: PR 对象
            
        Returns:
            关键词列表
        """
        keywords = []
        
        # 从标题提取
        title_words = pr.title.split()
        keywords.extend([w.strip('.,!?;:') for w in title_words if len(w) > 2])
        
        # 从描述提取
        if pr.description:
            # 简单提取：查找大写字母开头的单词或中文
            desc_words = re.findall(r'\b[A-Z][a-z]+\b|[\u4e00-\u9fff]{2,}', pr.description)
            keywords.extend(desc_words)
        
        # 从变更文件提取
        for change in pr.changes:
            # 提取函数名和类名
            matches = re.findall(r'(?:def|class|function)\s+([a-zA-Z_][a-zA-Z0-9_]*)', 
                               change.diff)
            keywords.extend(matches)
        
        # 去重
        return list(set(keywords))[:20]
    
    def get_changed_files(self, pr: PR) -> List[str]:
        """获取变更文件列表"""
        return [change.file_path for change in pr.changes]
    
    def get_file_types(self, pr: PR) -> Dict[str, int]:
        """获取文件类型统计"""
        types = {}
        for change in pr.changes:
            ext = change.file_path.split('.')[-1] if '.' in change.file_path else 'unknown'
            types[ext] = types.get(ext, 0) + 1
        return types