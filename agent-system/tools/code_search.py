"""
代码搜索工具
支持基于关键词和简单模式的代码检索
"""
import os
import re
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass


@dataclass
class SearchResult:
    """搜索结果"""
    file_path: str
    line_number: int
    content: str
    context_before: str = ""
    context_after: str = ""


class CodeSearch:
    """代码搜索器"""
    
    def __init__(self, root_path: str = "."):
        self.root_path = root_path
        # 默认搜索的文件扩展名
        self.extensions = [".py", ".java", ".js", ".ts", ".go", ".cpp", ".c", ".h"]
    
    def search(self, pattern: str, file_pattern: Optional[str] = None) -> List[SearchResult]:
        """
        搜索代码
        
        Args:
            pattern: 搜索模式（关键词或正则）
            file_pattern: 文件匹配模式
            
        Returns:
            搜索结果列表
        """
        results = []
        
        for root, dirs, files in os.walk(self.root_path):
            # 跳过隐藏目录和常见忽略目录
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ['node_modules', '__pycache__', 'venv', 'build']]
            
            for file in files:
                file_path = os.path.join(root, file)
                
                # 检查文件扩展名
                if not any(file.endswith(ext) for ext in self.extensions):
                    continue
                
                # 检查文件模式
                if file_pattern and not re.match(file_pattern, file):
                    continue
                
                try:
                    file_results = self._search_in_file(file_path, pattern)
                    results.extend(file_results)
                except (UnicodeDecodeError, PermissionError):
                    continue
        
        return results
    
    def _search_in_file(self, file_path: str, pattern: str) -> List[SearchResult]:
        """在单个文件中搜索"""
        results = []
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
        except Exception:
            return results
        
        # 尝试作为正则表达式匹配
        try:
            regex = re.compile(pattern)
        except re.error:
            # 如果不是有效正则，则作为普通字符串搜索
            regex = None
        
        for i, line in enumerate(lines):
            match = False
            
            if regex:
                match = regex.search(line) is not None
            else:
                match = pattern in line
            
            if match:
                context_before = ''.join(lines[max(0, i-2):i])
                context_after = ''.join(lines[i+1:min(len(lines), i+3)])
                
                results.append(SearchResult(
                    file_path=file_path,
                    line_number=i + 1,
                    content=line.strip(),
                    context_before=context_before.strip(),
                    context_after=context_after.strip()
                ))
        
        return results
    
    def find_references(self, symbol: str) -> List[SearchResult]:
        """
        查找符号引用
        
        Args:
            symbol: 符号名称（函数名、变量名等）
            
        Returns:
            引用位置列表
        """
        # 使用单词边界匹配
        pattern = r'\b' + re.escape(symbol) + r'\b'
        return self.search(pattern)
    
    def find_function_definition(self, func_name: str) -> Optional[SearchResult]:
        """
        查找函数定义
        
        Args:
            func_name: 函数名
            
        Returns:
            函数定义位置
        """
        patterns = [
            rf'def\s+{re.escape(func_name)}\s*\(',  # Python
            rf'function\s+{re.escape(func_name)}\s*\(',  # JavaScript
            rf'(?:public|private|protected)?\s*\w+\s+{re.escape(func_name)}\s*\(',  # Java/C++
        ]
        
        for pattern in patterns:
            results = self.search(pattern)
            if results:
                return results[0]
        
        return None
    
    def get_file_content(self, file_path: str) -> str:
        """
        获取文件内容
        
        Args:
            file_path: 文件路径
            
        Returns:
            文件内容
        """
        full_path = os.path.join(self.root_path, file_path)
        if not os.path.exists(full_path):
            return ""
        
        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception:
            return ""
    
    def search_in_range(self, file_path: str, pattern: str, 
                        start_line: int, end_line: int) -> List[SearchResult]:
        """
        在指定行范围内搜索
        
        Args:
            file_path: 文件路径
            pattern: 搜索模式
            start_line: 起始行号
            end_line: 结束行号
            
        Returns:
            搜索结果
        """
        results = []
        full_path = os.path.join(self.root_path, file_path)
        
        if not os.path.exists(full_path):
            return results
        
        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
        except Exception:
            return results
        
        # 调整行号范围
        start_line = max(1, start_line) - 1  # 转为 0-based
        end_line = min(len(lines), end_line)
        
        for i in range(start_line, end_line):
            line = lines[i]
            if pattern in line:
                results.append(SearchResult(
                    file_path=file_path,
                    line_number=i + 1,
                    content=line.strip()
                ))
        
        return results