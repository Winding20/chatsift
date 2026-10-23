from datetime import datetime, timedelta

from app import web_app as web_module
from app.models import Message
from app.repositories import MessageRepository


class FakeAIClient:
    model = "fake-model"

    def __init__(self, *args, **kwargs) -> None:
        pass

    def chat_json(self, prompt):
        return {
            "cards": [
                {
                    "type": "knowledge",
                    "quote": "4060 值不值",
                    "why": "有人在问配置，可能对买机器有用",
                    "score": 4,
                    "confidence": "claim",
                    "message_ids": ["m1"],
                },
                {
                    "type": "joke",
                    "quote": "凭空出现的段子",
                    "why": "编的",
                    "score": 5,
                    "confidence": "meme",
                    "message_ids": ["m1"],
                },
            ]
        }


def seed(chat_id: str = "c1") -> None:
    repository = MessageRepository()
    base = datetime(2026, 1, 1, 12, 0)

    for index in range(3):
        repository.save(
            Message(
                id=f"m{index + 1}",
                source="qq",
                chat_id=chat_id,
                chat_name="测试群",
                sender_id="u1",
                sender_name="张三",
                content=f"第 {index + 1} 条消息：4060 值不值",
                timestamp=base + timedelta(minutes=index),
            )
        )


def client():
    return web_module.app.test_client()


def test_chat_detail_returns_no_report_before_generation():
    seed()

    response = client().get("/api/chats/c1")
    data = response.get_json()

    assert response.status_code == 200
    assert [m["id"] for m in data["messages"]] == ["m1", "m2", "m3"]
    assert data["report"] is None
    assert data["sources"] == []


def test_analyze_saves_feed_and_drops_unverifiable_quote(monkeypatch):
    seed()
    monkeypatch.setattr(web_module, "ZhipuAIClient", FakeAIClient)

    response = client().post("/api/chats/c1/analyze", json={"limit": 10})
    data = response.get_json()

    assert response.status_code == 200
    cards = data["report"]["payload"]["cards"]
    assert len(cards) == 1
    assert cards[0]["type_label"] == "知识点"
    assert cards[0]["quote"] == "4060 值不值"
    assert cards[0]["sender"] == "张三"
    # 引用不存在 / 原话对不上的卡片必须被丢弃
    assert data["report"]["dropped"] == 1
    assert [message["id"] for message in data["sources"]] == ["m1"]


def test_feed_merges_cards_from_reports(monkeypatch):
    seed()
    monkeypatch.setattr(web_module, "ZhipuAIClient", FakeAIClient)
    client().post("/api/chats/c1/analyze", json={"limit": 10})

    data = client().get("/api/feed").get_json()

    assert data["stats"]["card_count"] == 1
    assert data["stats"]["chats_with_feed"] == 1
    assert data["cards"][0]["chat_name"] == "测试群"
    assert data["cards"][0]["score"] == 4


def test_analyze_reports_configuration_error(monkeypatch):
    seed()

    def broken():
        raise ValueError("未配置 ZHIPU_API_KEY")

    monkeypatch.setattr(web_module, "ZhipuAIClient", broken)

    response = client().post("/api/chats/c1/analyze")

    assert response.status_code == 400
    assert "ZHIPU_API_KEY" in response.get_json()["error"]


def test_analyze_unknown_chat_returns_404(monkeypatch):
    monkeypatch.setattr(web_module, "ZhipuAIClient", FakeAIClient)

    response = client().post("/api/chats/nope/analyze")

    assert response.status_code == 404
