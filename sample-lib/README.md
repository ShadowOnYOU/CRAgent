# samplelib

A small, packaging-ready Python library used to test the CRAgent code review workflow.

## Layout

- `src/samplelib/` — library code
- `tests/` — pytest unit tests
- `pr_diffs/` — sample `git diff` files for review

## Quickstart

```bash
cd sample-lib
python -m pip install -e '.[test]'
pytest
```

## Using CRAgent

From the `agent-system/` folder:

```bash
export DASHSCOPE_API_KEY=...  # required by LLM client
python main.py --root ../sample-lib --diff ../sample-lib/pr_diffs/001-introduce-cache-bug.diff --title "Introduce cache" 
```
