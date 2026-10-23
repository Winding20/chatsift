"""数据库自动备份。

每次启动检查一次，当天没有备份就复制一份，只保留最近若干份。
备份是原样拷贝 sqlite 文件，不做增量。
"""

from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path

from app.config import get_data_dir

KEEP = 7


def backup_dir() -> Path:
    path = get_data_dir() / "backups"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _today_file() -> Path:
    return backup_dir() / f"assistant-{date.today():%Y%m%d}.db"


def backup_now(source: Path | None = None) -> Path | None:
    """备份一次；源文件不存在时返回 None。"""
    from app.database import DATABASE_PATH

    src = Path(source or DATABASE_PATH)
    if not src.exists():
        return None

    target = _today_file()
    if target.exists():
        return target

    shutil.copy2(src, target)
    _prune()
    return target


def maybe_daily_backup() -> Path | None:
    """当天已经有备份就跳过。"""
    if _today_file().exists():
        return None
    return backup_now()


def list_backups() -> list[Path]:
    return sorted(backup_dir().glob("assistant-*.db"), reverse=True)


def _prune(keep: int = KEEP) -> None:
    backups = list_backups()
    for old in backups[keep:]:
        try:
            old.unlink()
        except OSError:
            pass
