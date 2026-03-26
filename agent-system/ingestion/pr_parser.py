"""
PR 解析器
负责解析和提取 PR 信息
"""
import json
import re
from typing import List, Dict, Any, Optional

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
        changes = []
        current_file = None
        current_diff_lines = []
        in_new_file = False
        
        lines = diff_text.split('\n')
        
        for line in lines:
            # 检测新文件
            if line.startswith('diff --git'):
                # 保存之前的文件
                if current_file and current_diff_lines:
                    changes.append(self._create_code_change(current_file, current_diff_lines))
                
                # 提取新文件名
                match = re.search(r'b/(.+)', line)
                if match:
                    current_file = match.group(1)
                current_diff_lines = [line]
                in_new_file = True
            
            elif line.startswith('--- '):
                # 旧文件名，跳过
                continue
            
            elif line.startswith('+++ '):
                # 新文件名，确认文件
                match = re.search(r'\+\+\+ b/(.+)', line)
                if match:
                    current_file = match.group(1)
                current_diff_lines.append(line)
            
            elif current_file:
                current_diff_lines.append(line)
        
        # 处理最后一个文件
        if current_file and current_diff_lines:
            changes.append(self._create_code_change(current_file, current_diff_lines))
        
        return changes
    
    def _create_code_change(self, file_path: str, diff_lines: List[str]) -> CodeChange:
        """创建 CodeChange 对象"""
        diff = '\n'.join(diff_lines)
        
        # 计算行号范围
        line_start = 0
        line_end = 0
        
        for i, line in enumerate(diff_lines):
            if line.startswith('@@'):
                # 解析 @@ -old_start,count +new_start,count @@
                match = re.search(r'\+(\d+)', line)
                if match:
                    line_start = int(match.group(1))
                break
        
        # 计算结束行
        added_lines = sum(1 for l in diff_lines if l.startswith('+') and not l.startswith('+++'))
        line_end = line_start + added_lines - 1 if line_start > 0 else 0
        
        # 提取新旧内容
        old_content = []
        new_content = []
        
        for line in diff_lines:
            if line.startswith('-') and not line.startswith('---'):
                old_content.append(line[1:])
            elif line.startswith('+') and not line.startswith('+++'):
                new_content.append(line[1:])
            elif not line.startswith(('diff', '@@', 'index', '---', '+++')):
                old_content.append(line)
                new_content.append(line)
        
        return CodeChange(
            file_path=file_path,
            old_content='\n'.join(old_content),
            new_content='\n'.join(new_content),
            diff=diff,
            line_start=line_start,
            line_end=line_end
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