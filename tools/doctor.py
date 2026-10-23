"""命令行自检（网页上也有「自检」按钮，用的是同一份逻辑）。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from app.health import report  # noqa: E402


MARKS = {"ok": "✓", "warn": "!", "error": "✗", "info": "·"}


def main() -> int:
    data = report()

    print("== 个人 AI 助手自检 ==")
    for item in data["items"]:
        mark = MARKS.get(item["state"], "·")
        print(f"{mark} {item['label']:<6}{item['value']}")

    print()
    if data["warnings"]:
        print("结论：需要关注")
        for warning in data["warnings"]:
            print(f"  · {warning}")
        return 1

    print("结论：一切正常")
    return 0


if __name__ == "__main__":
    sys.exit(main())
