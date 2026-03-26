"""
AST 解析工具
提供简单的代码结构分析功能
"""
import ast
import os
from typing import List, Optional, Dict, Any
from dataclasses import dataclass


@dataclass
class FunctionInfo:
    """函数信息"""
    name: str
    file_path: str
    line_start: int
    line_end: int
    args: List[str]
    docstring: str = ""
    calls: List[str] = None  # type: ignore
    
    def __post_init__(self):
        if self.calls is None:
            self.calls = []


@dataclass
class ClassInfo:
    """类信息"""
    name: str
    file_path: str
    line_start: int
    line_end: int
    methods: List[FunctionInfo] = None  # type: ignore
    bases: List[str] = None  # type: ignore
    
    def __post_init__(self):
        if self.methods is None:
            self.methods = []
        if self.bases is None:
            self.bases = []


@dataclass
class ImportInfo:
    """导入信息"""
    module: str
    names: List[str]
    file_path: str


class ASTParser:
    """AST 解析器"""
    
    def __init__(self, root_path: str = "."):
        self.root_path = root_path

    def parse(self, source: str) -> ast.Module:
        """解析一段 Python 源码字符串并返回 AST。

        主要用于单元测试/快速分析场景。
        """
        tree = ast.parse(source)
        self._attach_parents(tree)
        return tree
    
    def parse_file(self, file_path: str) -> Optional[ast.Module]:
        """
        解析 Python 文件
        
        Args:
            file_path: 文件路径
            
        Returns:
            AST 树
        """
        full_path = os.path.join(self.root_path, file_path)
        
        if not os.path.exists(full_path):
            return None
        
        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                source = f.read()
            tree = ast.parse(source)
            self._attach_parents(tree)
            return tree
        except (SyntaxError, UnicodeDecodeError, Exception):
            return None

    def _attach_parents(self, tree: ast.AST) -> None:
        """给 AST 节点挂载 parent 指针，便于向上追溯封闭作用域。"""
        for parent in ast.walk(tree):
            for child in ast.iter_child_nodes(parent):
                setattr(child, 'parent', parent)
    
    def get_functions(self, file_path: str) -> List[FunctionInfo]:
        """
        获取文件中的所有函数
        
        Args:
            file_path: 文件路径
            
        Returns:
            函数信息列表
        """
        tree = self.parse_file(file_path)
        if not tree:
            return []
        
        functions = []
        
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                args = [arg.arg for arg in node.args.args]
                
                docstring = ast.get_docstring(node) or ""
                
                # 获取函数调用的列表
                calls = []
                for child in ast.walk(node):
                    if isinstance(child, ast.Call):
                        if isinstance(child.func, ast.Name):
                            calls.append(child.func.id)
                        elif isinstance(child.func, ast.Attribute):
                            calls.append(child.func.attr)
                
                functions.append(FunctionInfo(
                    name=node.name,
                    file_path=file_path,
                    line_start=node.lineno,
                    line_end=node.end_lineno or node.lineno,
                    args=args,
                    docstring=docstring,
                    calls=calls
                ))
        
        return functions
    
    def get_classes(self, file_path: str) -> List[ClassInfo]:
        """
        获取文件中的所有类
        
        Args:
            file_path: 文件路径
            
        Returns:
            类信息列表
        """
        tree = self.parse_file(file_path)
        if not tree:
            return []
        
        classes = []
        
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                bases = []
                for base in node.bases:
                    if isinstance(base, ast.Name):
                        bases.append(base.id)
                
                methods = []
                for child in node.body:
                    if isinstance(child, ast.FunctionDef):
                        args = [arg.arg for arg in child.args.args]
                        docstring = ast.get_docstring(child) or ""
                        
                        methods.append(FunctionInfo(
                            name=child.name,
                            file_path=file_path,
                            line_start=child.lineno,
                            line_end=child.end_lineno or child.lineno,
                            args=args,
                            docstring=docstring
                        ))
                
                classes.append(ClassInfo(
                    name=node.name,
                    file_path=file_path,
                    line_start=node.lineno,
                    line_end=node.end_lineno or node.lineno,
                    methods=methods,
                    bases=bases
                ))
        
        return classes
    
    def get_imports(self, file_path: str) -> List[ImportInfo]:
        """
        获取文件中的所有导入
        
        Args:
            file_path: 文件路径
            
        Returns:
            导入信息列表
        """
        tree = self.parse_file(file_path)
        if not tree:
            return []
        
        imports = []
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
                imports.append(ImportInfo(
                    module="",
                    names=names,
                    file_path=file_path
                ))
            elif isinstance(node, ast.ImportFrom):
                names = [alias.name for alias in node.names]
                imports.append(ImportInfo(
                    module=node.module or "",
                    names=names,
                    file_path=file_path
                ))
        
        return imports
    
    def find_function_callers(self, file_path: str, function_name: str) -> List[Dict[str, Any]]:
        """
        查找调用指定函数的位置
        
        Args:
            file_path: 文件路径
            function_name: 函数名
            
        Returns:
            调用位置列表
        """
        tree = self.parse_file(file_path)
        if not tree:
            return []
        
        callers = []
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id == function_name:
                    callers.append({
                        'file': file_path,
                        'line': node.lineno,
                        'caller': self._get_enclosing_function(node)
                    })
                elif isinstance(node.func, ast.Attribute) and node.func.attr == function_name:
                    callers.append({
                        'file': file_path,
                        'line': node.lineno,
                        'caller': self._get_enclosing_function(node)
                    })
        
        return callers
    
    def _get_enclosing_function(self, node: ast.AST) -> str:
        """获取包含该节点的函数名"""
        current = node
        while current:
            if isinstance(current, ast.FunctionDef):
                return current.name
            current = getattr(current, 'parent', None)
        return "<module>"
    
    def get_code_structure(self, file_path: str) -> Dict[str, Any]:
        """
        获取代码结构概览
        
        Args:
            file_path: 文件路径
            
        Returns:
            代码结构信息
        """
        return {
            'functions': [
                {
                    'name': f.name,
                    'line': f.line_start,
                    'args': f.args
                }
                for f in self.get_functions(file_path)
            ],
            'classes': [
                {
                    'name': c.name,
                    'line': c.line_start,
                    'methods': [m.name for m in c.methods]
                }
                for c in self.get_classes(file_path)
            ],
            'imports': [
                {
                    'module': i.module,
                    'names': i.names
                }
                for i in self.get_imports(file_path)
            ]
        }