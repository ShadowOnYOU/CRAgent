"""
工具调用 Agent
负责调用各种外部工具辅助推理
"""
import json
from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass

import sys
sys.path.insert(0, '.')

from models import ToolResult
from tools.code_search import CodeSearch
from tools.grep_tool import GrepTool
from tools.ast_parser import ASTParser


@dataclass
class ToolDefinition:
    """工具定义"""
    name: str
    description: str
    parameters: Dict[str, Any]
    handler: Callable


class ToolAgent:
    """工具调用 Agent"""
    
    def __init__(self, root_path: str = "."):
        """
        初始化工具 Agent
        
        Args:
            root_path: 代码根路径
        """
        self.root_path = root_path
        self.code_search = CodeSearch(root_path)
        self.grep_tool = GrepTool(root_path)
        self.ast_parser = ASTParser(root_path)
        
        # 注册可用工具
        self.tools: Dict[str, ToolDefinition] = {}
        self._register_default_tools()
    
    def _register_default_tools(self):
        """注册默认工具"""
        
        # 代码搜索工具
        self.tools["code_search"] = ToolDefinition(
            name="code_search",
            description="搜索代码中的关键词或模式",
            parameters={
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "搜索模式（关键词或正则表达式）"
                    },
                    "file_pattern": {
                        "type": "string",
                        "description": "文件匹配模式（可选，如 *.py）"
                    }
                },
                "required": ["pattern"]
            },
            handler=self._code_search_handler
        )
        
        # 查找引用工具
        self.tools["find_references"] = ToolDefinition(
            name="find_references",
            description="查找符号的所有引用位置",
            parameters={
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "符号名称（函数名、变量名等）"
                    }
                },
                "required": ["symbol"]
            },
            handler=self._find_references_handler
        )
        
        # 读取文件工具
        self.tools["read_file"] = ToolDefinition(
            name="read_file",
            description="读取文件的完整内容",
            parameters={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "文件路径"
                    }
                },
                "required": ["file_path"]
            },
            handler=self._read_file_handler
        )
        
        # 查找函数定义工具
        self.tools["find_function"] = ToolDefinition(
            name="find_function",
            description="查找函数的定义位置",
            parameters={
                "type": "object",
                "properties": {
                    "function_name": {
                        "type": "string",
                        "description": "函数名"
                    }
                },
                "required": ["function_name"]
            },
            handler=self._find_function_handler
        )
        
        # AST 分析工具
        self.tools["ast_analysis"] = ToolDefinition(
            name="ast_analysis",
            description="分析 Python 文件的代码结构",
            parameters={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "文件路径"
                    }
                },
                "required": ["file_path"]
            },
            handler=self._ast_analysis_handler
        )

        # 函数上下文工具（用于把搜索命中升级为“函数级证据”）
        self.tools["get_function_context"] = ToolDefinition(
            name="get_function_context",
            description="给定文件路径与行号，返回该行所在函数/方法的范围与代码片段（Python 优先用 AST；其他语言回退为行窗口）。",
            parameters={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "文件路径（可为绝对路径或相对 root_path）",
                    },
                    "line_number": {
                        "type": "integer",
                        "description": "命中行号（1-based）",
                    },
                    "context_lines": {
                        "type": "integer",
                        "description": "围绕命中行的上下文行数（在函数范围内截取），默认 25",
                    },
                    "max_lines": {
                        "type": "integer",
                        "description": "最大返回行数（超过则截断），默认 80",
                    },
                },
                "required": ["file_path", "line_number"],
            },
            handler=self._get_function_context_handler,
        )
        
        # Grep 工具
        self.tools["grep"] = ToolDefinition(
            name="grep",
            description="使用 grep 搜索代码",
            parameters={
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "搜索模式"
                    },
                    "file_pattern": {
                        "type": "string",
                        "description": "文件匹配模式（如 *.py）"
                    }
                },
                "required": ["pattern"]
            },
            handler=self._grep_handler
        )
    
    def _code_search_handler(self, args: Dict[str, Any]) -> ToolResult:
        """代码搜索处理"""
        try:
            pattern = args.get("pattern", "")
            file_pattern = args.get("file_pattern")
            
            results = self.code_search.search(pattern, file_pattern)
            
            return ToolResult(
                tool_name="code_search",
                success=True,
                result=[{
                    "file": r.file_path,
                    "line": r.line_number,
                    "content": r.content
                } for r in results[:20]]  # 限制结果数量
            )
        except Exception as e:
            return ToolResult(
                tool_name="code_search",
                success=False,
                error=str(e)
            )
    
    def _find_references_handler(self, args: Dict[str, Any]) -> ToolResult:
        """查找引用处理"""
        try:
            symbol = args.get("symbol", "")
            results = self.code_search.find_references(symbol)
            
            return ToolResult(
                tool_name="find_references",
                success=True,
                result=[{
                    "file": r.file_path,
                    "line": r.line_number,
                    "content": r.content
                } for r in results[:20]]
            )
        except Exception as e:
            return ToolResult(
                tool_name="find_references",
                success=False,
                error=str(e)
            )
    
    def _read_file_handler(self, args: Dict[str, Any]) -> ToolResult:
        """读取文件处理"""
        try:
            file_path = args.get("file_path", "")
            content = self.code_search.get_file_content(file_path)
            
            return ToolResult(
                tool_name="read_file",
                success=True,
                result={"content": content[:10000]}  # 限制长度
            )
        except Exception as e:
            return ToolResult(
                tool_name="read_file",
                success=False,
                error=str(e)
            )
    
    def _find_function_handler(self, args: Dict[str, Any]) -> ToolResult:
        """查找函数处理"""
        try:
            func_name = args.get("function_name", "")
            result = self.code_search.find_function_definition(func_name)
            
            if result:
                return ToolResult(
                    tool_name="find_function",
                    success=True,
                    result={
                        "file": result.file_path,
                        "line": result.line_number,
                        "content": result.content
                    }
                )
            else:
                return ToolResult(
                    tool_name="find_function",
                    success=False,
                    result=None
                )
        except Exception as e:
            return ToolResult(
                tool_name="find_function",
                success=False,
                error=str(e)
            )
    
    def _ast_analysis_handler(self, args: Dict[str, Any]) -> ToolResult:
        """AST 分析处理"""
        try:
            file_path = args.get("file_path", "")
            structure = self.ast_parser.get_code_structure(file_path)
            
            return ToolResult(
                tool_name="ast_analysis",
                success=True,
                result=structure
            )
        except Exception as e:
            return ToolResult(
                tool_name="ast_analysis",
                success=False,
                error=str(e)
            )
    
    def _grep_handler(self, args: Dict[str, Any]) -> ToolResult:
        """Grep 处理"""
        try:
            pattern = args.get("pattern", "")
            file_pattern = args.get("file_pattern")
            
            results = self.grep_tool.grep(pattern, file_pattern)
            
            return ToolResult(
                tool_name="grep",
                success=True,
                result=[{
                    "file": r.file_path,
                    "line": r.line_number,
                    "content": r.content
                } for r in results[:20]]
            )
        except Exception as e:
            return ToolResult(
                tool_name="grep",
                success=False,
                error=str(e)
            )

    def _get_function_context_handler(self, args: Dict[str, Any]) -> ToolResult:
        """返回命中行所在函数/方法的范围与代码片段。"""
        import os

        try:
            file_path = str(args.get("file_path", ""))
            line_number = int(args.get("line_number", 0))
            context_lines = int(args.get("context_lines", 25))
            max_lines = int(args.get("max_lines", 80))

            if not file_path or line_number <= 0:
                return ToolResult(
                    tool_name="get_function_context",
                    success=False,
                    error="file_path and positive line_number are required",
                )

            def resolve_full_path(p: str) -> str:
                p = str(p or "").strip()
                if not p:
                    return p

                # Normalize common diff/tool prefixes.
                p = p.replace("\\", "/")
                if p.startswith("./"):
                    p = p[2:]
                if p.startswith("a/") or p.startswith("b/"):
                    p = p[2:]

                if os.path.isabs(p):
                    return p

                root_abs = os.path.abspath(self.root_path)
                root_base = os.path.basename(root_abs)
                candidates = [p]

                # Some tools return paths like "<root_base>/src/..."; strip it.
                if p.startswith(root_base + "/"):
                    candidates.append(p[len(root_base) + 1 :])

                for rel in candidates:
                    full = os.path.join(self.root_path, rel)
                    if os.path.exists(full):
                        return full

                # Fall back to the most likely join (even if it doesn't exist) for error reporting.
                return os.path.join(self.root_path, candidates[0])

            full_path = resolve_full_path(file_path)
            if not os.path.exists(full_path):
                return ToolResult(
                    tool_name="get_function_context",
                    success=False,
                    error=f"File not found: {full_path}",
                )

            with open(full_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            total_lines = len(lines)
            line_number = max(1, min(line_number, total_lines))

            def clip_window(start: int, end: int) -> Dict[str, Any]:
                start = max(1, start)
                end = min(total_lines, end)
                window = lines[start - 1 : end]
                truncated = len(window) > max_lines
                if truncated:
                    window = window[:max_lines]
                return {
                    "scope_type": "window",
                    "name": "<window>",
                    "line_start": start,
                    "line_end": end,
                    "match_line": line_number,
                    "truncated": truncated,
                    "snippet": "".join(window),
                }

            # Python：用 AST 找到最小覆盖范围的 FunctionDef
            if full_path.endswith(".py"):
                # ASTParser 内部会 join(root_path, file_path)，这里直接传绝对路径更稳
                funcs = self.ast_parser.get_functions(full_path)
                candidates = [
                    fn for fn in funcs
                    if fn.line_start <= line_number <= fn.line_end
                ]
                if candidates:
                    fn = min(candidates, key=lambda x: (x.line_end - x.line_start, x.line_start))
                    start = fn.line_start
                    end = fn.line_end
                    # 截取：优先给出命中行附近上下文，同时保留函数签名行
                    win_start = max(start, line_number - context_lines)
                    win_end = min(end, line_number + context_lines)

                    snippet_lines = lines[win_start - 1 : win_end]
                    truncated = len(snippet_lines) > max_lines or (win_start != start or win_end != end)
                    if len(snippet_lines) > max_lines:
                        snippet_lines = snippet_lines[:max_lines]

                    # 确保包含函数定义行
                    if start < win_start:
                        snippet_lines = [lines[start - 1]] + ["...<omitted>...\n"] + snippet_lines

                    return ToolResult(
                        tool_name="get_function_context",
                        success=True,
                        result={
                            "scope_type": "function",
                            "name": fn.name,
                            "line_start": start,
                            "line_end": end,
                            "match_line": line_number,
                            "truncated": truncated,
                            "snippet": "".join(snippet_lines),
                        },
                    )

            # 非 Python 或 AST 找不到：回退为行窗口
            return ToolResult(
                tool_name="get_function_context",
                success=True,
                result=clip_window(line_number - context_lines, line_number + context_lines),
            )

        except Exception as e:
            return ToolResult(
                tool_name="get_function_context",
                success=False,
                error=str(e),
            )
    
    def get_tools_schema(self) -> List[Dict[str, Any]]:
        """获取工具 Schema，用于 LLM 工具调用"""
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters
                }
            }
            for tool in self.tools.values()
        ]
    
    def execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> ToolResult:
        """
        执行工具
        
        Args:
            tool_name: 工具名称
            arguments: 工具参数
            
        Returns:
            工具执行结果
        """
        if tool_name not in self.tools:
            return ToolResult(
                tool_name=tool_name,
                success=False,
                error=f"Unknown tool: {tool_name}"
            )
        
        tool = self.tools[tool_name]
        return tool.handler(arguments)
    
    def list_tools(self) -> List[str]:
        """列出所有可用工具"""
        return list(self.tools.keys())