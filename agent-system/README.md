# Code Review Agent

基于阿里云百炼 LLM 的代码评审智能体系统。

## 🏗️ 架构设计

```
┌─────────────────────────────────────────┐
│  L1: 动态上下文工程层 (Context Engine)   │
│  - PR 解析模块                            │
│  - 上下文召回（依赖分析/RAG/筛选）         │
└────────────────┬────────────────────────┘
                 ↓
┌─────────────────────────────────────────┐
│  L2: 多 Agent 推理决策层 (核心大脑)        │
│  - 缺陷识别 Agent                         │
│  - 工具调用 Agent                         │
│  - Long CoT 推理引擎                      │
└────────────────┬────────────────────────┘
                 ↓
┌─────────────────────────────────────────┐
│  L3: 结果过滤层 (LLM-as-Judge)           │
│  - 事实校验                              │
│  - 去重降噪                              │
│  - 低价值过滤                            │
└────────────────┬────────────────────────┘
                 ↓
┌─────────────────────────────────────────┐
│  反馈闭环 (持续进化)                      │
└─────────────────────────────────────────┘
```

## 📁 项目结构

```
agent-system/
├── config/              # 配置模块
│   └── settings.py
├── models/              # 数据模型
│   └── __init__.py
├── llm/                 # LLM 客户端
│   └── client.py
├── tools/               # 工具集
│   ├── code_search.py
│   ├── grep_tool.py
│   └── ast_parser.py
├── agents/              # Agent 模块
│   ├── bug_agent.py
│   └── tool_agent.py
├── ingestion/           # PR 解析模块
│   └── pr_parser.py
├── reasoning/           # Long CoT 推理引擎
│   └── long_cot.py
├── judge/               # 结果过滤层
│   └── filter.py
├── feedback/            # 反馈闭环
│   └── loop.py
├── main.py              # 主入口
├── requirements.txt     # 依赖
└── README.md            # 本文档
```

## 🚀 快速开始

### 1. 创建虚拟环境（推荐）

```bash
cd agent-system
python3.12 -m venv venv
source venv/bin/activate  # Linux/macOS
# 或
venv\Scripts\activate     # Windows
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 配置 API Key

```bash
export DASHSCOPE_API_KEY=your_api_key_here
```

在阿里云百炼控制台获取 API Key: https://dashscope.console.aliyun.com/

### 4. 运行演示

```bash
python main.py
```

### 5. 评审 diff 文件

```bash
python main.py --diff changes.diff --title "Fix bug in user module"
```

## 🧪 测试

本项目提供两类测试：

1) **不依赖 API Key 的本地回归测试**（推荐先跑这个）

```bash
# 不需要设置 DASHSCOPE_API_KEY
python test_framework.py
```

2) **真实 LLM 的集成测试脚本**（会产生真实 API 调用；未设置 key 时默认跳过）

```bash
export DASHSCOPE_API_KEY=your_api_key_here

# LLM 冒烟测试：验证 LLMClient 可调用且 JSON 可解析
python test_llm_call.py

# 过滤器集成测试：真实调用 filter_with_llm，并验证 strict_facts 事实约束不会被破坏
python test_llm_filter_integration.py
```

如需在 CI 中强制要求提供 key，可加 `--require-key`：

```bash
python test_llm_call.py --require-key
python test_llm_filter_integration.py --require-key
```

## 🆕 近期更新（更贴近“真实 code review”）

以下能力已在主流程（LongCoT）中落地：

- READ：输入包含真实 diff（按预算截断）+ 可选 Context
- HYPOTHESIZE：强制 JSON 输出，并带解析 fallback
- VERIFY：检索关键词由 LLM 主导生成（含缓存/清洗/正则回退）
- VERIFY：从“命中即停”升级为“可控递归深挖”
  - keyword → code_search
  - 从证据片段抽取候选 symbol → find_function / find_references
  - 证据不足时利用 next_keywords 继续挖掘
  - 带上限控制（最大深度/最大工具调用/最大证据条数），避免 token 与耗时爆炸
- 证据粒度：通过 get_function_context 将“单行命中”升级为“函数级片段”（Python 优先 AST；其他语言回退行窗口）
- 证据驱动判定：对每个假设输出 confirmed/rejected/inconclusive，并把理由与证据传递到结论
- run_trace：记录 llm_request/llm_response/tool_request/tool_response/run_start/run_end，便于复盘与 Debug

运行流程的更详细说明见仓库根目录：[运行流程详解.md](../%E8%BF%90%E8%A1%8C%E6%B5%81%E7%A8%8B%E8%AF%A6%E8%A7%A3.md)

## ▶️ 跑 sample-lib 示例（推荐）

仓库自带了一个可复现实例（`sample-lib/`）以及对应 diff：

```bash
cd agent-system
export DASHSCOPE_API_KEY=your_api_key_here

# 评审 sample-lib 的示例 diff
python main.py \
  --diff ../sample-lib/pr_diffs/001-introduce-cache-bug.diff \
  --root ../sample-lib \
  --title "SampleLib: Introduce cache bug" \
  --output ../sample-lib/review_output.json
```

## 📖 使用示例

### 基本使用

```python
from main import CodeReviewAgent
from models import PR, CodeChange

# 创建 Agent
agent = CodeReviewAgent(root_path="/path/to/code")

# 创建 PR 对象
pr = PR(
    pr_id="PR-001",
    title="Add user authentication",
    description="Implement OAuth2 login",
    changes=[
        CodeChange(
            file_path="auth.py",
            diff="... git diff content ...",
            line_start=1,
            line_end=10
        )
    ]
)

# 执行评审
result = agent.review_pr(pr)

# 打印结果
agent.print_result(result)
```

### 直接评审 diff

```python
agent = CodeReviewAgent()

diff_text = """
diff --git a/example.py b/example.py
--- a/example.py
+++ b/example.py
@@ -1,5 +1,7 @@
 def process_data(data):
-    result = data.get('result')
+    result = data['result']
     return result.process()
"""

result = agent.review_diff(diff_text, "Fix data processing")
agent.print_result(result)
```

### 获取推理轨迹

```python
result = agent.review_pr(pr)

# 查看推理过程
trace = agent.get_reasoning_trace()
for step in trace:
    print(step)
```

### 反馈收集

```python
from feedback.loop import FeedbackLoop
from models import FeedbackStatus

feedback = FeedbackLoop()

# 记录反馈
feedback.accept(pr_id="PR-001", issue_index=0, comment="确实是个问题")
feedback.reject(pr_id="PR-001", issue_index=1, comment="误报")

# 查看统计
stats = feedback.get_stats()
print(f"采纳率：{feedback.get_acceptance_rate():.2%}")
```

## ⚙️ 配置选项

在 `config/settings.py` 中配置：

```python
# LLM 配置
LLMConfig(
    api_key="your_key",
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    model="qwen-plus",
    max_tokens=4096,
    temperature=0.7
)

# 评审配置
ReviewConfig(
    max_context_tokens=8000,
    min_confidence=0.6,
    enable_tool_augmented=True
)
```

## 🔧 命令行参数

```
usage: main.py [-h] [--diff DIFF] [--root ROOT] [--title TITLE] 
               [--simple] [--no-filter] [--output OUTPUT]

options:
  -h, --help            显示帮助信息
  -d, --diff DIFF       Git diff 文件路径
  -r, --root ROOT       代码根路径 (默认：.)
  -t, --title TITLE     PR 标题
  -s, --simple          使用简单模式（不使用 Long CoT）
  --no-filter           禁用结果过滤
  -o, --output OUTPUT   输出结果文件路径
```

## 🎯 核心特性

### 1. Long CoT 推理

实现 `READ → HYPOTHESIZE → VERIFY → CONCLUDE` 推理循环：

- **READ**: 理解代码变更，识别关键变量和潜在问题点
- **HYPOTHESIZE**: 提出可能的缺陷假设
- **VERIFY**: 使用工具搜索证据验证假设
- **CONCLUDE**: 基于验证结果生成评审结论

### 2. 工具增强推理

内置工具：
- `code_search`: 代码关键词搜索
- `find_references`: 查找符号引用
- `read_file`: 读取文件内容
- `find_function`: 查找函数定义
- `ast_analysis`: AST 代码结构分析
- `grep`: 系统 grep 搜索

### 3. 结果过滤

- 严重级别过滤
- 置信度过滤
- 低价值问题识别
- 重复问题去重
- LLM 智能过滤（可选）

### 4. 反馈闭环

- 三态反馈：Accept / Ignore / Reject
- 自动统计采纳率
- 误报案例分析
- 评测数据集导出

## 📊 输出格式

```json
{
  "summary": "发现 2 个需要关注的问题",
  "issues": [
    {
      "type": "潜在空指针异常",
      "severity": "high",
      "message": "直接访问字典键可能导致 KeyError",
      "file": "example.py",
      "line": 2,
      "suggestion": "使用 data.get('result') 或先检查键是否存在"
    }
  ]
}
```

## 🔮 后续迭代计划

1. **RAG 增强** - 集成向量数据库，检索企业知识库
2. **多 Agent 协作** - 需求一致性 Agent + 缺陷识别 Agent
3. **GitHub/GitLab 集成** - 直接读取 PR/MR
4. **微调支持** - 基于反馈数据微调模型
5. **并发问题检测** - 专门的并发缺陷分析

## 📝 License

MIT License