"""集中读取环境变量。所有可配置项都在这里，代码里不再出现硬编码。

AI_* 是通用配置（任何 OpenAI 兼容端点都能用）；
ZHIPU_* 作为旧名字保留兼容，AI_* 优先。
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _first(*names: str) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value is not None and value.strip():
            return value.strip()
    return None


def _float(names: tuple[str, ...], default: float) -> float:
    raw = _first(*names)
    if raw is None:
        return default
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _int(names: tuple[str, ...], default: int) -> int:
    raw = _first(*names)
    if raw is None:
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _bool(names: tuple[str, ...], default: bool) -> bool:
    raw = _first(*names)
    if raw is None:
        return default
    return raw.lower() not in ("0", "false", "no", "off", "")


def get_ai_settings() -> dict[str, str | None]:
    return {
        "api_key": _first("AI_API_KEY", "ZHIPU_API_KEY"),
        "base_url": _first("AI_BASE_URL", "ZHIPU_BASE_URL"),
        "model": _first("AI_MODEL", "ZHIPU_MODEL"),
    }


def get_data_dir() -> Path:
    raw = _first("DATA_DIR")
    path = Path(raw).expanduser() if raw else BASE_DIR / "data"
    if not path.is_absolute():
        path = BASE_DIR / path
    return path


def get_web_host() -> str:
    return _first("WEB_HOST") or "127.0.0.1"


def get_web_port() -> int:
    return _int(("WEB_PORT",), 5000)


def get_web_password() -> str:
    """给局域网访问设个密码；留空表示只在本机用、不校验。"""
    return _first("WEB_PASSWORD") or ""


def get_ws_host() -> str:
    return _first("WS_HOST") or "127.0.0.1"


def get_ws_port() -> int:
    return _int(("WS_PORT",), 8765)


def get_analysis_interval() -> float:
    """自动分析周期（秒）。默认 5 分钟。"""
    return _float(("ANALYSIS_INTERVAL", "AI_ANALYSIS_DELAY"), 300.0)


def get_analysis_window() -> int:
    """每个群每次送进模型的消息条数上限。"""
    return _int(("ANALYSIS_WINDOW",), 100)


def get_analysis_max_attempts() -> int:
    """同一批消息最多重试几次，超过就停放，避免无限重试。"""
    return _int(("ANALYSIS_MAX_ATTEMPTS",), 5)


def get_auto_analysis() -> bool:
    """是否在后台自动分析（关掉就只采集、不花钱）。"""
    return _bool(("AUTO_ANALYSIS",), True)


def get_ai_timeout() -> float:
    return _float(("AI_TIMEOUT",), 60.0)


# --- 旧接口，保留兼容 -------------------------------------------------


def get_ai_analysis_delay() -> float:
    return get_analysis_interval()


def get_ai_analysis_max_wait() -> float:
    return _float(("AI_ANALYSIS_MAX_WAIT",), 30.0)
