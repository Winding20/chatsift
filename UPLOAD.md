# 上传到 GitHub 操作手册

这个 `github/` 文件夹就是**可以直接发布的版本**：已经剔除了虚拟环境、数据库、缓存、日志和本地 `.env`，只保留源码、测试、文档和配置模板。

---

## 一、上传前自查（3 分钟）

在项目根目录（`B:\个人ai助手项目文件夹`）打开终端：

```powershell
# 1) 用已有的虚拟环境跑一遍测试，确认干净副本能过
cd github
..\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider

# 2) 确认没有敏感文件混进来（应该什么都搜不到）
Get-ChildItem -Recurse -Force -Filter ".env"
Get-ChildItem -Recurse -Force -Filter "*.db"
Select-String -Path (Get-ChildItem -Recurse -Include *.py,*.md,*.toml -Name) -Pattern "sk-[A-Za-z0-9]{20,}" -ErrorAction SilentlyContinue
```

预期：测试全绿、上面三条都没有输出。

---

## 二、在 GitHub 网页建仓库

1. 打开 <https://github.com/new>
2. Repository name：`personal-ai-assistant`
3. Description：`本地优先的群聊阅读代理：把没时间看的群消息，挑成值得看的内容`
4. 可见性：想清楚再选（公开 / 私有）
5. **不要**勾 "Add a README file"、"Add .gitignore"、"Choose a license"——本地已经有了，勾了会冲突
6. 点 Create repository

---

## 三、把本地内容推上去

```powershell
cd B:\个人ai助手项目文件夹\github

git init
git add .
git status                # 确认没有 .env / data/*.db
git commit -m "feat: 群聊阅读代理首个公开版本"

git branch -M main
git remote add origin ssh://git@ssh.github.com:443/Winding20/chatsift.git
git push -u origin main
```

第一次 push 要认证：推荐用 **Personal Access Token**（Settings → Developer settings → Personal access tokens → Fine-grained tokens，权限勾 `Contents: Read and write`），当作密码填。

> 网络不通时把 `https://github.com` 换成你常用的镜像或走代理，命令其余部分不变。

---

## 四、推完做四件事

1. **Actions**：进仓库 → Actions 标签，确认 `tests` 工作流跑过（绿勾）
2. **About**：右上角齿轮，填 Description 和 Topics：`qq`、`onebot`、`llm`、`local-first`、`python`
3. **README 顶部徽章**：把 `LICENSE` 旁边的 Python 版本徽章换成本仓库地址即可
4. **检查隐私**：随便点一个文件，确认没有聊天原文、没有 key、没有数据库

---

## 五、以后怎么更新

主项目（`B:\个人ai助手项目文件夹`）是开发目录，`github/` 是发布副本。改了代码后：

```powershell
# 在项目根目录执行，把改动同步到发布副本（不覆盖 .git 和 data）
robocopy app  github\app  /MIR /XD __pycache__
robocopy tests github\tests /MIR /XD __pycache__
copy run.py github\run.py
copy README.md github\README.md

cd github
git add -A
git commit -m "update: ..."
git push
```

---

## 六、这个版本里刻意没有的东西

| 没有 | 原因 |
|---|---|
| `.env` | 含真实密钥，永远不进仓库 |
| `data/assistant.db` | 含真实聊天记录，属于隐私数据 |
| `.venv/` | 体积大、可重建 |
| `app/report_generator.py` | 早期的分析模块，已被 `feed_generator.py` 取代 |
| `check_database.py` | 根目录遗留脚本，功能已被 `tools/db_report.py` 覆盖 |
| `tests/test_websocket_client.py` | 不是测试，是手工发包脚本，已移到 `tools/send_test_messages.py` |

---

## 七、发布时建议在 Release 里写清楚

- 这是**实验性**版本，内容质量依赖提示词和模型，可能挑得不全；
- 不含 QQ 协议实现，需要自备 NapCat；
- 只处理你本人有权访问的群，遵守平台条款与当地法律；
- 数据只存本地，唯一外发是你自己配置的 AI 服务。
