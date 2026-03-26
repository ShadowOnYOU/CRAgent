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