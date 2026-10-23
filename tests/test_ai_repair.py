from app.ai_client import repair_json


def test_repair_truncated_object():
    text = '{"cards":[{"type":"knowledge","quote":"你好"'
    result = repair_json(text)

    assert isinstance(result, dict)
    assert result["cards"][0]["type"] == "knowledge"


def test_repair_strips_code_fence():
    text = '```json\n{"cards": [], "digest": []}\n```'
    result = repair_json(text)

    assert result == {"cards": [], "digest": []}


def test_repair_ignores_leading_prose():
    text = '好的，结果如下：\n{"cards":[]}'
    result = repair_json(text)

    assert result == {"cards": []}


def test_repair_returns_none_for_garbage():
    assert repair_json("完全不是 JSON") is None
    assert repair_json("") is None


def test_repair_handles_arrays():
    result = repair_json('[{"a": 1}, {"b": 2}]')

    assert result == [{"a": 1}, {"b": 2}]
