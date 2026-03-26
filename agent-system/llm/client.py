"""
LLM 客户端
封装阿里云百炼 API 调用
"""
import json
import os
from datetime import datetime
from typing import List, Dict, Any, Optional, Generator
from openai import OpenAI

from config.settings import config


class LLMClient:
    """LLM 客户端"""

    TRACE_MAX_CHARS = 4000
    
    def __init__(self, api_key: Optional[str] = None, 
                 base_url: Optional[str] = None,
                 model: Optional[str] = None):
        """
        初始化 LLM 客户端
        
        Args:
            api_key: API 密钥，默认从环境变量 DASHSCOPE_API_KEY 读取
            base_url: API 基础 URL
            model: 模型名称
        """
        # 优先从参数获取，其次环境变量，最后配置文件
        self.api_key = api_key or os.getenv("DASHSCOPE_API_KEY", "") or config.llm.api_key
        self.base_url = base_url or config.llm.base_url
        self.model = model or config.llm.model
        
        if not self.api_key:
            raise ValueError("API key is required. Set DASHSCOPE_API_KEY environment variable.")
        
        # 确保 API Key 格式正确（移除可能的空格）
        self.api_key = self.api_key.strip()
        
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=60.0,  # 60 秒超时
            max_retries=2
        )
    
    def chat(self, messages: List[Dict[str, str]], 
             temperature: Optional[float] = None,
             max_tokens: Optional[int] = None,
             show_progress: bool = True,
             trace: Optional[List[Dict[str, Any]]] = None,
             trace_meta: Optional[Dict[str, Any]] = None) -> str:
        """
        发送聊天请求
        
        Args:
            messages: 消息列表，格式为 [{"role": "user", "content": "..."}]
            temperature: 温度参数
            max_tokens: 最大 token 数
            show_progress: 是否显示进度提示
            
        Returns:
            AI 回复的内容
        """
        if show_progress:
            print(f"  [LLM] 正在调用 {self.model} 模型，请稍候...")

        if trace is not None:
            trace.append({
                "type": "llm_request",
                "ts": datetime.now().isoformat(),
                "model": self.model,
                "temperature": temperature or config.llm.temperature,
                "max_tokens": max_tokens or config.llm.max_tokens,
                "messages": self._truncate_messages(messages),
                "meta": trace_meta or {},
            })
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature or config.llm.temperature,
                max_tokens=max_tokens or config.llm.max_tokens
            )
            
            if show_progress:
                print(f"  [LLM] 响应完成")

            content = response.choices[0].message.content
            if trace is not None:
                trace.append({
                    "type": "llm_response",
                    "ts": datetime.now().isoformat(),
                    "model": self.model,
                    "content": self._truncate_text(content),
                    "meta": trace_meta or {},
                })

            return content
        except Exception as e:
            if show_progress:
                print(f"  [LLM] 请求失败：{e}")

            if trace is not None:
                trace.append({
                    "type": "llm_error",
                    "ts": datetime.now().isoformat(),
                    "model": self.model,
                    "error": str(e),
                    "meta": trace_meta or {},
                })
            raise

    def _truncate_text(self, text: str) -> str:
        if text is None:
            return ""
        text = str(text)
        if len(text) <= self.TRACE_MAX_CHARS:
            return text
        return text[: self.TRACE_MAX_CHARS] + "...<truncated>"

    def _truncate_messages(self, messages: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for m in messages:
            out.append({
                "role": m.get("role"),
                "content": self._truncate_text(m.get("content", "")),
                "content_len": len(m.get("content", "") or ""),
            })
        return out
    
    def chat_with_tools(self, messages: List[Dict[str, str]],
                        tools: List[Dict[str, Any]],
                        temperature: Optional[float] = None) -> Dict[str, Any]:
        """
        发送带工具调用的聊天请求
        
        Args:
            messages: 消息列表
            tools: 工具定义列表
            temperature: 温度参数
            
        Returns:
            包含回复内容或工具调用信息的字典
        """
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=tools,
            temperature=temperature or config.llm.temperature
        )
        
        choice = response.choices[0]
        message = choice.message
        
        result = {
            "content": message.content,
            "tool_calls": []
        }
        
        if message.tool_calls:
            for tc in message.tool_calls:
                result["tool_calls"].append({
                    "id": tc.id,
                    "name": tc.function.name,
                    "arguments": json.loads(tc.function.arguments)
                })
        
        return result
    
    def stream_chat(self, messages: List[Dict[str, str]],
                    temperature: Optional[float] = None) -> Generator[str, None, None]:
        """
        流式聊天
        
        Args:
            messages: 消息列表
            temperature: 温度参数
            
        Yields:
            逐块返回的回复内容
        """
        stream = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature or config.llm.temperature,
            stream=True
        )
        
        for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
    
    def extract_json(self, text: str) -> Optional[Dict[str, Any]]:
        """
        从文本中提取 JSON
        
        Args:
            text: 包含 JSON 的文本
            
        Returns:
            解析后的 JSON 对象
        """
        # 尝试查找 ```json 代码块
        import re
        
        json_pattern = r'```json\s*(.*?)\s*```'
        match = re.search(json_pattern, text, re.DOTALL)
        
        if match:
            json_str = match.group(1)
        else:
            # 尝试直接解析
            json_str = text.strip()
        
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            # 尝试查找第一个 { 和最后一个 }
            start = text.find('{')
            end = text.rfind('}') + 1
            if start != -1 and end > start:
                try:
                    return json.loads(text[start:end])
                except json.JSONDecodeError:
                    pass
            return None
    
    def count_tokens(self, text: str) -> int:
        """
        估算 token 数量（简单估算：中文字符数 + 英文单词数）
        
        Args:
            text: 文本内容
            
        Returns:
            估算的 token 数
        """
        # 简单估算
        chinese_chars = len([c for c in text if '\u4e00' <= c <= '\u9fff'])
        english_chars = len([c for c in text if c.isascii() and c.isalpha()])
        return chinese_chars + english_chars // 4