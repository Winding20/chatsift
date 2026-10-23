from app.ai_client import ZhipuAIClient


def test_zhipu_client_configuration(monkeypatch):
    monkeypatch.setenv("ZHIPU_API_KEY", "test-key")
    monkeypatch.setenv(
        "ZHIPU_BASE_URL",
        "https://open.bigmodel.cn/api/paas/v4/",
    )
    monkeypatch.setenv("ZHIPU_MODEL", "glm-4-flash")

    client = ZhipuAIClient()

    assert client.model == "glm-4-flash"
    assert client.client is not None