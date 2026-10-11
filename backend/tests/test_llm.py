"""Respuestas del LLM que no son JSON válido: se guardan para diagnosticarlas."""

import json

import pytest

from app import llm as L
from app.config import Settings


class _Resp:
    def __init__(self, content, finish):
        self._data = {"choices": [{"message": {"content": content}, "finish_reason": finish}]}

    def raise_for_status(self):
        pass

    def json(self):
        return self._data


def _server(monkeypatch, tmp_path, responses):
    calls = []

    def post(*_a, **_k):
        calls.append(1)
        return responses[min(len(calls), len(responses)) - 1]

    monkeypatch.setattr(L.httpx, "post", post)
    monkeypatch.setattr(L.time, "sleep", lambda _s: None)
    monkeypatch.setattr(L, "DATA_DIR", tmp_path)
    return L.LLMServer(Settings()), calls


def test_truncated_response_is_saved_and_not_retried(monkeypatch, tmp_path):
    server, calls = _server(monkeypatch, tmp_path, [_Resp('{"a": "sin cerrar', "length")])
    with pytest.raises(L.LLMError, match="se cortó"):
        server.chat_json("sistema", [{"type": "image_url", "image_url": {"url": "data:..."}},
                                     {"type": "text", "text": "hola"}], {"type": "object"}, max_tokens=10)
    assert len(calls) == 1
    [saved] = list((tmp_path / "llm_failures").iterdir())
    data = json.loads(saved.read_text(encoding="utf-8"))
    assert data["finish_reason"] == "length" and data["response"] == '{"a": "sin cerrar'
    assert data["messages"][1]["content"] == [{"type": "text", "text": "hola"}]  # sin la imagen


def test_invalid_json_is_retried(monkeypatch, tmp_path):
    server, calls = _server(monkeypatch, tmp_path, [_Resp("no es json", "stop"), _Resp('{"ok": 1}', "stop")])
    assert server.chat_json("s", "u", {"type": "object"}) == {"ok": 1}
    assert len(calls) == 2
