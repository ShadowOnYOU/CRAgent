# sample-lib-2

这是一个用于验证 CRAgent 端到端评审链路的最小示例项目（第二套用例）。

- 代码：`src/samplelib2/`
- 测试：`tests/`
- PR diff 输入：`pr_diffs/002-silent-failure-and-leak.diff`

## 运行测试

在仓库根目录使用你的 conda 环境：

- `cd sample-lib-2 && python -m pytest`

## 端到端评审示例

从仓库根目录运行：

- `python agent-system/main.py --diff sample-lib-2/pr_diffs/002-silent-failure-and-leak.diff --root sample-lib-2 --title "sample-lib-2 002" --output sample-lib-2/review_output_002.json`

该 diff 引入了两类常见问题（用于触发 checklist / strict_facts 的行为验证）：

1. 静默吞错：JSON 解析失败直接返回空字典
2. 资源未成对释放：打开文件未关闭（未使用 context manager）
