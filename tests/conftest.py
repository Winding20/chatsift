import shutil
from uuid import uuid4

import pytest

import app.database as database

# 测试数据库放在工作区内，避免依赖系统临时目录
# （某些受限环境下，pytest 自建的临时目录创建后无法再次访问）。
TEST_DATA_DIR = database.BASE_DIR / ".tmp" / "testdb"


def pytest_sessionstart(session):
    """每次开跑前清空上一次留下的测试库。

    Windows 上单个 db 文件有时因句柄未释放删不掉，逐个删会越积越多；
    改成"整目录重建"，最多只留本次会话的量。
    """
    shutil.rmtree(TEST_DATA_DIR, ignore_errors=True)


@pytest.fixture(autouse=True)
def test_database(monkeypatch):
    TEST_DATA_DIR.mkdir(parents=True, exist_ok=True)
    test_database_path = TEST_DATA_DIR / f"{uuid4().hex}.db"

    monkeypatch.setattr(database, "DATABASE_PATH", test_database_path)
    database.init_database()

    yield

    for suffix in ("", "-wal", "-shm", "-journal"):
        candidate = test_database_path.with_name(
            test_database_path.name + suffix
        )
        try:
            candidate.unlink(missing_ok=True)
        except OSError:
            pass
