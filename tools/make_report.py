"""命令行生成某个群的 AI 分析报告（不依赖网页服务）。

用法：
    .\\.venv\\Scripts\\python.exe -X utf8 tools\\make_report.py <chat_id> [消息条数]
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.ai_client import ZhipuAIClient  # noqa: E402
from app.feed_generator import generate  # noqa: E402
from app.repositories import MessageRepository  # noqa: E402
from app.report_repository import AnalysisReportRepository  # noqa: E402


def main() -> None:
    if len(sys.argv) < 2:
        print("用法: python tools/make_report.py <chat_id> [消息条数]")
        return

    chat_id = sys.argv[1]
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 60

    messages = MessageRepository().get_by_chat(chat_id, limit=limit)
    if not messages:
        print(f"群 {chat_id} 没有消息")
        return

    report = generate(ZhipuAIClient(), messages)
    report_id = AnalysisReportRepository().save(
        chat_id,
        messages[-1].chat_name,
        report,
    )

    print(f"report_id={report_id} 覆盖 {report.message_count} 条 丢弃 {report.dropped} 条")
    print(json.dumps(report.payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
