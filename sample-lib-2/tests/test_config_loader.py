from __future__ import annotations

import json

from samplelib2 import load_json_config


def test_load_json_config_valid(tmp_path):
    p = tmp_path / "cfg.json"
    p.write_text(json.dumps({"a": 1, "b": "x"}), encoding="utf-8")

    assert load_json_config(str(p)) == {"a": 1, "b": "x"}


def test_load_json_config_invalid_json_returns_empty_dict(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{not: json}", encoding="utf-8")

    # 当前行为：解析失败返回空 dict（这本身是可被 code review 质疑的设计）
    assert load_json_config(str(p)) == {}
