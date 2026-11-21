# AGENTS.md — 知识库助手 / 塞莎特——题谱

面向 Qoder 等编码代理的项目约定。读代码前先读本文件。

## 这是什么

Python/Tkinter 本地桌面应用（另带本地 HTTP 网页端与手机页面），面向高校师生的科研选题工作台。
原项目位于 `G:\skill\knowledge-monitor`（保持不动），本目录是 Qoder 开发副本。

- 产品定义：`PRODUCT.md`
- 设计系统：`DESIGN.md`（改 UI 前必读）
- 功能与限制：`README.md`、`功能说明手册.md`
- 入口：`app_main.py`（桌面）、`web_server.py`（网页/手机）、`kb_widget.py`（旧版小卡片）

## 运行环境

本机默认 `python`（3.9）缺少依赖，必须使用：

```powershell
D:\miniconda3\python.exe app_main.py
```

零新增 pip 依赖是硬约束（现有 numpy 1.26 / sklearn 1.8 可用）。纯离线优先，联网功能必须可降级。
中文界面，字号下限 13px；启动到首屏 < 1.5 秒。

## 常用命令

```powershell
D:\miniconda3\python.exe check_tokens.py        # 深浅主题对比度自检，失败项必须为 0
D:\miniconda3\python.exe tools_smoke_app.py     # 冒烟测试（11 项，会开窗口）
D:\miniconda3\python.exe tools_e2e_test.py      # 端到端功能测试（54 项）
D:\miniconda3\python.exe tools_test_nav.py      # 及 test_web / test_profile / test_prompt / test_tilt
                                                # test_qr / test_new / test_download / test_personalize
                                                # test_pwa / test_chat
D:\miniconda3\python.exe tools_shot_pages_all.py  # 16 张截图，深/浅主题各一套
D:\miniconda3\python.exe web_server.py          # 网页端，默认 8765
```

GUI 测试需要桌面会话；无图形环境时至少跑 `check_tokens.py` 并说明未验证 UI。

## 参赛 Web 版

`competition/site/` 是 2026 Qoder 高校创造力大赛的静态演示版（StudyHack 赛道），
不替代桌面端，也没有后端 / 在线模型 / API Key。

```powershell
D:\miniconda3\python.exe competition\scripts\export_web_data.py   # 只读导出静态数据
cd competition\site; python -m http.server 4173                    # 本地预览
node competition\scripts\check_site.mjs                            # 7 路由 × 3 宽度回归
node competition\scripts\capture_screenshots.mjs                   # 21 张验收截图
```

改 Web 版后需重新导出数据（如涉及数据）、在本地跑 `check_site.mjs`，再更新 `dist/` 并发布。
`dist/` 被 `.gitignore` 排除；`competition/screenshots/` 作为参赛证据保留。不要把 `llm_config.json` 或用户数据带入 Web 版。

## 架构速查

| 文件 | 职责 |
|---|---|
| `app_main.py` | 主窗口、导航、12 个页面装配 |
| `app_theme.py` / `design_tokens.py` | 主题、语义色、字号档位、Card/Canvas 自绘 |
| `page_*.py` | 各页面：topic / gap / latest / ideas / skills / mentor / venue / library / map / profile / plan / settings |
| `advisor_index.py` | 学者索引加载、合并、匹配、排序 |
| `topic_gen.py` / `topic_fusion.py` / `topic_constraint.py` | 选题候选生成与约束 |
| `research_diagnose.py` / `research_gap.py` / `novelty_check.py` | 结构体检、文献空白、查重 |
| `research_skills.py` / `prompt_context.py` | 7 套科研方法论与提示词 |
| `kb_vector.py` / `semantic_search.py` / `fulltext.py` | 本地语义检索、PDF 全文索引 |
| `arxiv_latest.py` / `kb_download.py` / `paper_sources.py` | arXiv/OpenAlex/Europe PMC 抓取与下载 |
| `profile_memory.py` / `plan_store.py` | 迭代画像、研究计划持久化 |
| `ui_parts.py` | LazyList、WrapRow 等通用控件 |
| `app_paths.py` | RES/DATA/KB 三类路径解析，打包前后行为差异 |

## 数据与安全

- 用户数据：`research_memory.json`、`research_plan.json`、`researcher_profile.json`、`llm_config.json`、`config.json`。
  这些文件被 `.gitignore` 排除；测试必须使用 `tools_isolate.py` 隔离，不得写入真实数据。
- `llm_config.json`（含 API Key）**没有**复制到本目录。需要测大模型功能时，请手动在原项目与本目录之间复制，且不要提交。
- 外部只读数据：
  - 知识库 PDF：路径见 `config.json` 的 `kb_path`；没配时默认取程序目录下的 `知识库/`
  - arXiv 向量索引（约 1.4 GB）：默认 `<KB_VECTOR_DIR>/index`；`KB_VECTOR_DIR` 依次取环境变量、`config.json` 的 `kb_vector_path`、最后退回 `G:\kb-vector`（见 `kb_vector.py` 的 `_base_dir()`）
- 代码与界面上的数字必须来自真实计算，不得编造。

## 改动规则

1. 改 UI 先看 `DESIGN.md`，字号/颜色/圆角只用令牌，不新增魔法值。
2. 不引入新 pip 依赖；确需引入必须先征得用户同意。
3. 任何结论类文案（空白、新颖性、导师匹配）必须同时写明核查范围与局限。
4. 提交前：`check_tokens.py` 失败项 0；相关测试套件全绿；不改动用户数据。
5. 现有目录不是 git 仓库的完整历史，首个提交是 Qoder 接手基线。

## 已知遗留（不要当成新 bug 重复修）

- 约 40 条 PDF 标题抽取错误（双栏 PDF 上限约 74%）；
- venue 首屏 3–3.9s、profile 首屏 6.5–10.5s 偏慢；
- 浅色主题下卡片无描边，仅靠画布与卡片亮度差区分；
- 531 个真实方向中 35 个导师页推荐不出学者（另有 207 个在图谱页按关键词精确计数为 0）（OpenAlex 主题颗粒度限制；按方向名/关键词匹配学者 fields、keywords、lab 统计，2026-11-20 合并后现算）；
- 跨学科边界判定是关键词 + venue 近似，非论文内容判定。

## 文档约定（2026-11-20 起）

- 顶层 `README.md` 是简体中文主文档，`README.en.md` / `README.zh-TW.md` 是同结构的完整翻译，`README.zh-CN.md` 只做目录与回链、**不重复正文**（三份正文各自漂移的教训来自上一版 1441 行的 README）。
- 改数字时先跑 `.tmp/nums.py` 一类的现数脚本，不要凭记忆；口径要写清（例如学者 21,847 是文件行数，合并去重后 18,345 才是界面显示的「可推荐」数）。
- 旧文档都在 `docs/origin/`，只作历史证据，不再更新。
- README 配图用 `docs/images/`（由 `tools_shots_all.py` 1440×900 产出后拷入）；`screenshots/` 整个目录在 `.gitignore` 里，不要往里放要展示的图。
