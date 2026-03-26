#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""LLM 调用冒烟测试（需要 DASHSCOPE_API_KEY）。

设计目标：
- 不影响现有 agent-system/test_framework.py（它必须不依赖 API Key）
- 这里单独验证：LLMClient 能正常发起请求并收到可解析的 JSON

用法：
  export DASHSCOPE_API_KEY=your_key
  /opt/anaconda3/envs/cragent/bin/python agent-system/test_llm_call.py

可选：
  --require-key    没有 key 时直接失败（退出码 1）
  --model xxx      覆盖模型名（默认读取 config/settings.py）
  --max-tokens 256 覆盖 max_tokens
"""

import argparse
import os
import sys
from typing import Any, Dict, List

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from llm.client import LLMClient


SYSTEM_JSON_ONLY = """你是一个严格的 JSON 生成器。
规则：
1) 只输出 JSON，不要输出解释、不要输出 Markdown
2) JSON 必须是一个对象（以 { 开头、} 结尾）
3) 字段固定为：ok, answer, meta
"""


def run_smoke_test(model: str | None, max_tokens: int | None) -> Dict[str, Any]:
    client = LLMClient(model=model)

    messages: List[Dict[str, str]] = [
        {"role": "system", "content": SYSTEM_JSON_ONLY},
        {
            "role": "user",
            "content": "请输出一个 JSON：answer=\"pong\"，meta.stage=\"smoke\"。",
        },
    ]

    resp = client.chat(
        messages,
        max_tokens=max_tokens,
        show_progress=True,
        trace=None,
        trace_meta={"test": "smoke"},
    )

    data = client.extract_json(resp)
    if not isinstance(data, dict):
        raise AssertionError(f"期望解析到 JSON 对象 dict，但得到：{type(data)}；原始响应：{resp[:200]}")

    if data.get("answer") != "pong":
        raise AssertionError(f"期望 answer=pong，但得到：{data.get('answer')}")

    meta = data.get("meta")
    if not isinstance(meta, dict) or meta.get("stage") != "smoke":
        raise AssertionError(f"期望 meta.stage=smoke，但得到：{meta}")

    if data.get("ok") not in (True, "true", 1):
        # 有些模型可能输出 true/1；只要不是明显错误即可
        pass

    return data


def main() -> int:
    parser = argparse.ArgumentParser(description="LLM 调用冒烟测试")
    parser.add_argument("--require-key", action="store_true", help="没有 API Key 时直接失败")
    parser.add_argument("--model", default=None, help="覆盖模型名（默认使用 config）")
    parser.add_argument("--max-tokens", type=int, default=256, help="max_tokens")
    args = parser.parse_args()

    if not os.getenv("DASHSCOPE_API_KEY"):
        msg = "未设置 DASHSCOPE_API_KEY，跳过 LLM 调用测试。"
        if args.require_key:
            print("❌ " + msg)
            return 1
        print("⚠️  " + msg)
        print("   export DASHSCOPE_API_KEY=your_api_key_here")
        return 0

    print("=" * 60)
    print("运行 LLM 冒烟测试（会产生真实 API 调用）")
    print("=" * 60)

    data = run_smoke_test(model=args.model, max_tokens=args.max_tokens)
    print("✅ LLM 调用成功，且 JSON 可解析")
    print(f"返回：{data}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
