# chatsift · 群聊阅读代理

> 没时间看群，也能看到里面真正值得看的东西：一个知识点、一个段子、几个人的观点、一条对你有用的情报。

本地运行，数据只存在你自己的 SQLite 里；只把消息发给**你自己配置的** AI 服务。

[![license](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)

> **交流群 QQ：`1078798708`** —— 装不上、用不明白、想提建议，进群问最快。

![演示](docs/images/promo.gif)

---

## 它解决什么问题

群一天几百条，你不可能全看。但里面总有那么几条值得花 10 秒：

- 有人分享了个能省钱的参数
- 有人讲了个特别好笑的段子
- 几个人为一个事争论，你只想知道结论
- 有人发了活动、维护、涨价这种"错过就麻烦"的消息

chatsift 把群消息读一遍，只挑这些，**原话照抄**给你，其余的全部丢掉。

## 它挑什么

五类，都是"值得花 10 秒看"的：

| 类型 | 例子（真实群聊） |
|---|---|
| 知识点 | "K90 max玩端游风扇比拯救者还大，应该是撞温度墙之后才全速运行" |
| 段子 | "黑白滤镜拍出来有种凶宅即视感" |
| 观点 | "台湾人就这样纯翻译啊" / "这个还好，我能理解" |
| 情报 | "你买外星人 别人售后上门可以当场组装一台" |
| 约定 | "明天上午十点开黑，缺一个" |

每条还会给一句点评，说明**为什么值得你看**；点「上下文」能看到前后的对话。

除了单条卡片，每个群还会有一段**「群里发生了什么」**：按话题说清这段时间聊了什么、谁提的、结论是什么、有没有没人答的问题。

## 它怎么保证不说谎

这是整个项目最较真的地方：**AI 只负责挑，不负责写**。

1. 每条卡片必须引用真实消息 id；
2. 卡片里的原话必须是那条消息的**逐字子串**；
3. 程序用代码核对，对不上的整条丢弃，并记进报告的 `dropped` 计数。

所以你不会看到"AI 编出来的观点"。它挑得可能不准，但**引用的每句话都真实存在**。

---

## 三步跑起来

### 1. 准备

- **Python 3.11+**（[下载](https://www.python.org/downloads/)，安装时勾选 Add to PATH）
- **一个 AI 服务的密钥**，见下表
- **NapCat**（下一步要用，先把项目跑起来也可以）

| 服务 | `AI_BASE_URL` | `AI_MODEL` 示例 |
|---|---|---|
| 智谱 | `https://open.bigmodel.cn/api/paas/v4/` | `glm-4-flash`（免费额度够用） |
| DeepSeek | `https://api.deepseek.com/v1` | `deepseek-chat` |
| OpenAI | `https://api.openai.com/v1` | `gpt-4o-mini` |
| 本地 Ollama | `http://127.0.0.1:11434/v1` | `qwen2.5:7b` |

### 2. 启动

**Windows：双击 `start_web.bat`，别的都不用管。** 它会依次：

1. 检查 Python 版本（太低会直接告诉你）
2. 第一次运行时自动建环境、装依赖
3. 没有 `.env` 就用记事本打开，让你填密钥；**保存关闭后自动继续**
4. 检查端口
5. 启动，5 秒后自动打开浏览器

> 关闭那个黑窗口 = 停止服务。

**手动启动**（macOS / Linux，或想看每步在干什么）：

```powershell
python -m venv .venv
.\.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -e .

# 把 .env.example 复制成 .env，填好三项：
#   AI_API_KEY / AI_BASE_URL / AI_MODEL

python run.py
```

看到这两行就对了：

```
WebSocket 接收端：ws://127.0.0.1:8765
面板：http://127.0.0.1:5000
```

> ⚠️ `AI_BASE_URL` 要填**完整地址**（带 `/v1` 或 `/api/paas/v4/`），少一段会一直报错。

### 3. 接上 QQ

**先启动本项目，再配 NapCat**，顺序反了 NapCat 会一直报"连不上"。

本项目不自带 QQ 协议实现，只提供一个接收端（OneBot 11），由 NapCat 主动连过来。

<details>
<summary><b>展开：NapCat 配置详细步骤</b></summary>

**3.1 找到 WebUI 地址和密钥**

启动 NapCat 后，命令行窗口会打印：

```
WebUi Token: 8f3a2c1d9b7e
WebUi User Panel Url: http://127.0.0.1:6099/webui?token=8f3a2c1d9b7e
```

复制整条 URL 到浏览器打开。窗口关了就去 `NapCat\config\webui.json` 找 `token`。

**3.2 登录 QQ**

扫码授权即可。

**3.3 添加「WebSocket 客户端」**

WebUI → 左侧「网络配置」→ 找到 **WebSocket 客户端** → 添加。

> ⚠️ 别选错：
> - **WebSocket 服务器**：NapCat 开端口等别人连 ❌
> - **WebSocket 客户端**（反向 WS）：NapCat 主动连我们 ✅

| 字段 | 填什么 |
|---|---|
| 名称 | 随便，比如 `chatsift` |
| URL | `ws://127.0.0.1:8765` |
| Token | **留空**（我们不校验密码） |
| 消息格式 | `array`（`string` 也兼容） |
| 自动重连 | **开启** |

**3.4 两边各看一次**

- NapCat：这条配置显示 **已连接**
- 我们：终端出现 `QQ 接入端已连接`

只连上一边，消息不会进来。

</details>

### 4. 验收

1. 打开 <http://127.0.0.1:5000>
2. 左侧进「自检」，应该看到 `✓ 接收端 在线` 和 `✓ 接收账号 你的QQ号`
3. 群里发几条消息，顶部「消息」数字会涨
4. 「设置」里选个群点「总结这段时间」，十几秒后出纪要和卡片

> 刚装好是空的，这很正常。等群里聊几句再总结。

---

## 页面怎么用

左侧四个入口：

| 入口 | 内容 |
|---|---|
| **内容流** | 左栏「群里发生了什么」按话题整理；右栏「值得看的」按类型筛选，每群最多 4 条 |
| **历史记录** | 按日期分组列出每一批分析，点开看那一批的话题和卡片 |
| **搜索** | 消息原文、卡片、话题一起搜；也可用 `?q=关键词#search` 直接打开 |
| **自检** | 数据库、接收端、账号、队列、游标、报告，哪项不对直接标出来 |
| **设置** | 总结节奏、手动总结、导出、口味统计、提醒、外观 |

### 卡片上的三个东西

- **判断**：「值得看」或「一般」
- **原话 + 点评**：为什么值得你看
- **「有用 / 无聊」**：点了会记住，攒够 3 条后开始影响下次挑选

### 设置里能干什么

| 区块 | 能做的事 |
|---|---|
| 总结节奏 | 自动总结开关、间隔（1–1440 分钟） |
| 手动总结 | 选群 → 立刻总结这段时间；导出 Markdown |
| 你的口味 | 按类型统计你点过多少"有用/无聊" |
| 外观 | 主题、主色、字号、行距、密度、圆角、卡片样式、背景、内容宽度 |

外观设置存在浏览器本地，也可以用链接分享：

```
http://127.0.0.1:5000/?theme=dark&accent=5&size=17#feed
```

---

## 维护与数据

**自动备份**：每天第一次启动时把数据库复制到 `data/backups/`，保留最近 7 份。

**老消息归档**（搬到归档表，不删数据）：

```powershell
python tools/archive_messages.py --days 180          # 预览
python tools/archive_messages.py --days 180 --apply  # 执行
```

**清理测试数据**：

```powershell
python tools/clean_test_data.py            # 预览
python tools/clean_test_data.py --apply    # 执行
```

**手机也能看**：`.env` 里设

```dotenv
WEB_HOST=0.0.0.0
WEB_PASSWORD=只有你知道的密码
```

同一个 Wi-Fi 下，手机打开 `http://电脑IP:5000`，输密码即可。不设密码就只有本机访问。

**多个 QQ 号**：换号登录 NapCat 之后，新消息会记下当前账号；同一条消息被两个号收到不会重复；旧号的群会留在列表里但不再更新（新号不在那些群里）。

---

## 常见问题

按你看到的信息查：

| 你看到的 | 原因 | 怎么办 |
|---|---|---|
| `接收端 离线` / `没有连接记录` | NapCat 没连过来 | 检查「接上 QQ」那条配置在不在、URL 是否 `8765`、是否启用 |
| NapCat 显示「连接失败」 | 我们的服务没启动，或端口被占 | 先 `python run.py`；终端报 `OSError: 10048` 就是端口被占 |
| 连上几秒又断开 | 配置重复，或我们重启过 | 只保留一条 WS 客户端；开自动重连 |
| 终端刷 `ConnectionClosedError` | 客户端主动断开（换号/重启） | 正常现象，不影响数据 |
| WebUI 打不开 | 缺 token | 从 NapCat 启动日志或 `webui.json` 里复制 |
| 「消息」数字不涨 | 群里没人说话，或账号不在这个群 | 自己发一条试试；确认自检里的接收账号是对的 |
| `AI 配置不完整` | `.env` 少了字段 | 三个 `AI_*` 都要填 |
| `调用 AI 失败` | 地址或 key 不对、网络不通 | 确认 `AI_BASE_URL` 带完整路径 |
| `端口被占用` | 上次的进程没退 | 结束残留 `python.exe`，或改 `WEB_PORT` / `WS_PORT` |
| 有消息但没有卡片 | 这批确实都是表情、图片、寒暄 | 看纪要有没有话题；换一批再试 |
| 某个群一直不出内容 | 消息里可能触发了 AI 服务的内容审查 | 程序会自动把批次对半拆开重试，救不回的那几条跳过，不影响其它群 |
| 换号后旧群不更新 | 新号不在那些群里 | 正常，群详情里能看到最后活跃账号 |
| 想分析接入之前的历史 | 只处理接入之后的消息 | 新版 QQ 已不支持导出聊天记录，暂无导入方案 |

---

## 命令

```powershell
python run.py                  # 全部启动：面板 + 接收端 + 后台分析
python run.py --once           # 只跑一轮分析（处理积压）
python run.py --no-scheduler   # 只采集和看，不自动花钱

python tools/doctor.py                     # 命令行自检
python tools/make_report.py <chat_id> 100  # 手动给某个群挑一遍
python tools/db_report.py                  # 只读体检
python tools/show_messages.py <chat_id> 30 # 只看某群最近消息
python tools/reset_queue.py                # 失败计数清零，让积压重试
python tools/archive_messages.py --days 180
python tools/clean_test_data.py
```

## 配置

全部写在 `.env` 里，代码中没有硬编码：

| 变量 | 默认 | 说明 |
|---|---|---|
| `AI_API_KEY` | — | 必填。旧名 `ZHIPU_API_KEY` 仍兼容 |
| `AI_BASE_URL` | — | 必填。任何 OpenAI 兼容地址 |
| `AI_MODEL` | — | 必填 |
| `WEB_HOST` | `127.0.0.1` | 改成 `0.0.0.0` 允许局域网访问 |
| `WEB_PORT` | `5000` | 面板端口 |
| `WEB_PASSWORD` | 空 | 设了就要登录 |
| `WS_HOST` / `WS_PORT` | `127.0.0.1` / `8765` | 接收端 |
| `DATA_DIR` | `./data` | 数据库目录 |
| `ANALYSIS_INTERVAL` | `300` | 自动总结间隔（秒），页面上可改 |
| `ANALYSIS_WINDOW` | `100` | 每批最多送多少条 |
| `ANALYSIS_MAX_ATTEMPTS` | `5` | 失败重试上限 |
| `AUTO_ANALYSIS` | `1` | 设 `0` 只采集不分析，不花钱 |
| `AI_TIMEOUT` | `60` | 单次请求超时（秒） |

## 数据与隐私

- 消息、分析结果、登录的 QQ 号全部在本地 `./data/assistant.db`，不上传任何服务器；
- 唯一的外部请求是你自己配置的 AI 服务；
- `.env`、`data/` 已在 `.gitignore` 中，不会被提交；
- 分析结果包含聊天原文，截图分享前请自行判断。

## 项目结构

```
app/
  config.py            所有配置项
  service.py           WebSocket 接收端（只入库）
  scheduler.py         后台分析（游标 + 重试 + 停放）
  feed_generator.py    提示词与"逐字核对"校验
  noise.py             机器人 / 模板消息识别
  feedback.py          "有用 / 无聊"反馈
  backup.py            每日自动备份
  report_repository.py 分析结果存取
  session_log.py       连接记录、数据缺口、分析游标
  settings.py          开关与间隔
  health.py            自检逻辑
  web_app.py           面板与 API（含搜索、导出、登录）
  static/              图标
  templates/           页面
run.py                 一键启动
tools/                 自检、手动分析、归档、清理
tests/                 pytest
```

## 开发

```bash
pip install -e ".[dev]"
pytest -q          # 52 个测试
```

## 已知限制

- 每批最多 100 条，一轮会连续处理多批（默认每群 10 批），**没有跨批次记忆**：同一件事分两次出现不会自动合并；
- 只处理接入之后的消息，**不能导入历史记录**；
- 判断"值不值得看"靠提示词，同一批内容偶尔会出现"这次给 0 条"的抖动；
- Flask 内置服务器只适合本机或局域网自用，不适合公网部署；
- 只支持 OneBot 11 群消息。

## License

[MIT](LICENSE)
