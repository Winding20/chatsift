# 贡献指南

先谢谢你愿意花时间。这个项目很小，规则也简单。

## 开发环境

```bash
python -m venv .venv
.venv\Scripts\activate        # macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
pytest -q
```

跑测试不需要真实 AI 密钥：需要联网的用例会自动跳过。

## 提 PR 之前

1. `pytest -q` 全绿；
2. 新增的行为尽量配一个测试（尤其是 `feed_generator` 里的合法性校验）；
3. 不要提交 `.env`、`data/`、任何真实聊天记录；
4. 提交信息用一句话说清"改了什么、为什么"。

## 代码风格

- Python 3.11+，不引入新依赖前先开 Issue 讨论；
- 配置一律走 `app/config.py`，不要在业务代码里读环境变量；
- 所有面向用户的中文文案保持一致：直接、具体、不吹牛。

## 想加内容类型？

`feed_generator.py` 里的 `TYPE_LABELS` 是唯一的类型来源。加一类需要同时改：

1. 提示词里的类型说明和例子；
2. `TYPE_LABELS`；
3. `app/templates/feed.html` 里的 `TYPES` 和 `.badge.<type>` 配色；
4. 一个测试，确认这类卡片能通过合法性校验。

## 报告问题

开 Issue 时请附上：

- 能复现的最小配置（不要贴 key）；
- `python tools/db_report.py` 的输出（不含聊天内容的部分）；
- 期望看到什么、实际看到什么。

## License

贡献的代码按 MIT 授权。
