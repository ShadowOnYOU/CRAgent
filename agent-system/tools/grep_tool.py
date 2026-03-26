"""
Grep 工具
提供类似 grep 的文本搜索功能
"""
import os
import re
import subprocess
from typing import List, Optional
from dataclasses import dataclass


@dataclass
class GrepResult:
    """Grep 搜索结果"""
    file_path: str
    line_number: int
    content: str
    match_start: int = 0
    match_end: int = 0


class GrepTool:
    """Grep 工具类"""
    
    def __init__(self, root_path: str = "."):
        self.root_path = root_path
    
    def grep(self, pattern: str, 
             file_pattern: Optional[str] = None,
             ignore_case: bool = False,
             max_results: int = 100) -> List[GrepResult]:
        """
        执行 grep 搜索
        
        Args:
            pattern: 搜索模式
            file_pattern: 文件匹配模式
            ignore_case: 是否忽略大小写
            max_results: 最大结果数
            
        Returns:
            搜索结果列表
        """
        results = []
        
        # 构建 grep 命令
        cmd = ["grep", "-n", "-r"]
        
        if ignore_case:
            cmd.append("-i")
        
        # 添加文件模式过滤
        if file_pattern:
            cmd.extend(["--include", file_pattern])
        
        cmd.extend([pattern, self.root_path])
        
        try:
            output = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if output.returncode == 0:
                for line in output.stdout.strip().split('\n'):
                    if not line:
                        continue
                    
                    # 解析 grep 输出格式：file:line:content
                    parts = line.split(':', 2)
                    if len(parts) >= 3:
                        file_path = parts[0]
                        line_num = int(parts[1])
                        content = parts[2]
                        
                        results.append(GrepResult(
                            file_path=file_path,
                            line_number=line_num,
                            content=content
                        ))
                        
                        if len(results) >= max_results:
                            break
                            
        except subprocess.TimeoutExpired:
            pass
        except Exception:
            pass
        
        return results
    
    def grep_python(self, pattern: str, ignore_case: bool = False) -> List[GrepResult]:
        """在 Python 文件中搜索"""
        return self.grep(pattern, file_pattern="*.py", ignore_case=ignore_case)
    
    def grep_java(self, pattern: str, ignore_case: bool = False) -> List[GrepResult]:
        """在 Java 文件中搜索"""
        return self.grep(pattern, file_pattern="*.java", ignore_case=ignore_case)
    
    def grep_js(self, pattern: str, ignore_case: bool = False) -> List[GrepResult]:
        """在 JavaScript 文件中搜索"""
        return self.grep(pattern, file_pattern="*.js", ignore_case=ignore_case)
    
    def count_matches(self, pattern: str, file_pattern: Optional[str] = None) -> int:
        """
        统计匹配次数
        
        Args:
            pattern: 搜索模式
            file_pattern: 文件匹配模式
            
        Returns:
            匹配次数
        """
        cmd = ["grep", "-r", "-c"]
        
        if file_pattern:
            cmd.extend(["--include", file_pattern])
        
        cmd.extend([pattern, self.root_path])
        
        try:
            output = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            total = 0
            for line in output.stdout.strip().split('\n'):
                if ':' in line:
                    try:
                        count = int(line.split(':')[-1])
                        total += count
                    except ValueError:
                        continue
            return total
        except Exception:
            return 0
    
    def grep_with_context(self, pattern: str, 
                          context_lines: int = 2,
                          file_pattern: Optional[str] = None) -> List[dict]:
        """
        带上下文的 grep 搜索
        
        Args:
            pattern: 搜索模式
            context_lines: 上下文行数
            file_pattern: 文件匹配模式
            
        Returns:
            带上下文的结果
        """
        cmd = ["grep", "-n", "-r", "-B", str(context_lines), "-A", str(context_lines)]
        
        if file_pattern:
            cmd.extend(["--include", file_pattern])
        
        cmd.extend([pattern, self.root_path])
        
        results = []
        
        try:
            output = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if output.returncode == 0:
                current_result = None
                context_lines_list = []
                
                for line in output.stdout.strip().split('\n'):
                    if line.startswith('--'):
                        # 分隔符
                        if current_result:
                            current_result['after_context'] = '\n'.join(context_lines_list)
                            results.append(current_result)
                            current_result = None
                            context_lines_list = []
                        continue
                    
                    if line.startswith('-'):
                        # 前缀上下文
                        if current_result is None:
                            pass  # 忽略前面的上下文
                        continue
                    
                    if line.startswith('+'):
                        # 后缀上下文
                        context_lines_list.append(line[1:])
                        continue
                    
                    # 匹配行
                    if current_result:
                        current_result['after_context'] = '\n'.join(context_lines_list)
                        results.append(current_result)
                    
                    parts = line.split(':', 2)
                    if len(parts) >= 3:
                        current_result = {
                            'file_path': parts[0],
                            'line_number': int(parts[1]),
                            'content': parts[2],
                            'before_context': '',
                            'after_context': ''
                        }
                        context_lines_list = []
                
                if current_result:
                    current_result['after_context'] = '\n'.join(context_lines_list)
                    results.append(current_result)
                    
        except Exception:
            pass
        
        return results