# Qoder 使用日志

日期：2026-11-17
项目目录：`G:\Qoder\workers\knowledge-monitor`
原始项目：`G:\skill\knowledge-monitor`（保持不动）

本日志只记录可验证的工作，不把已有桌面原型说成从零生成。

## 0. 起点

桌面原型是一个已有的 Python / Tkinter 本地应用，包含方向库、候选生成、结构体检、文献空白、学者索引、venue 与 7 套方法论。参赛要求是公网可打开的 Qoder Sites 链接，因此需要在不破坏原项目的前提下，做一份可独立演示的 Web 版。

## 1. 复制与边界确认

- 将源码、配置模板与必要数据复制到 `G:\Qoder\workers\knowledge-monitor`；
- 不复制 `llm_config.json`、API Key、用户研究记忆 / 画像；
- 确认 `.gitignore` 已排除 `config.json`、`research_memory.json`、`researcher_profile.json`、`llm_config.json`、日志与构建产物；
- 原项目不参与后续修改。

## 2. 架构阅读与取舍

在 Qoder 中阅读：

- `PRODUCT.md`、`DESIGN.md`、`AGENTS.md`、`README.md`、`功能说明手册.md`；
- `topic_gen.py`、`research_diagnose.py`、`research_gap.py`、`research_skills.py`、`advisor_index.py`；
- `kb_widget.py` 的方向库加载与 `venue_meta.json`、`institution_localization.json` 等数据结构。

取舍：

- 只把确定性算法移植到浏览器：方向匹配、候选生成、9 项结构体检、文献共现展示；
- 需要 53.8 万篇 arXiv 向量的查重、PDF 全文检索、在线模型、下载与画像管理保留在桌面完整版；
- Web 版不接后端、不接模型、不保存用户账号数据。

## 3. 数据导出

新增 `competition/scripts/export_web_data.py`：

- 只读调用原桌面引擎与本地数据；
- 导出 `index.json`、387 个方向数据文件、`advisors.json`、`venues.json`；
- 统计结果：24 类目 / 387 方向 / 345 篇本地文献 / 126 venue / 18,281 位学者索引（17,677 位可推荐）/ 每方向 12 位学者；
- 生成 5 个虚拟示例方向的 `dataId` 映射，保证示例能直接打开真实方向数据；
- 为每个方向附带 `localGap`（方向内方法 × 任务共现）与本地命中数，供矩阵联动和星图使用；
- 不写入用户数据，不发起网络请求。

复现：

```powershell
cd G:\Qoder\workers\knowledge-monitor
D:\miniconda3\python.exe competition\scripts\export_web_data.py
```

## 4. Web 实现

新增 `competition/site/`：

- `index.html`：SPA 外壳、侧栏、移动端底部导航、SVG 图标；
- `assets/core.js`：数据加载、方向匹配、候选生成、9 项体检、`localStorage`；
- `assets/app.js`：7 个路由、各页面渲染、事件绑定；
- `assets/styles.css`：Nudge 设计变量、深浅主题、1220 / 980 / 760 / 420 断点、移动端详情前置；
- `data/`：导出的静态 JSON。

路由：

`#/workshop`、`#/gap`、`#/advisors`、`#/venues`、`#/methods`、`#/plan`、`#/about`。

交互要点：

- 5 个示例方向均可生成 18 条候选、12 位学者、若干 venue；
- 输入方向库中没有的说法时，用全库数据兜底；
- 直接打开 `#/advisors` 默认进入学者检索，直接打开 `#/venues` 默认展示全部 126 个 venue；
- 手机端选择候选后，详情面板自动排到候选列表上方并滚动到标题；
- 研究计划只写入本机 `localStorage`，不向服务器发送。

## 5. 浏览器验收

新增 `competition/scripts/check_site.mjs`（无头 Chrome + CDP）：

- 7 个路由 × 1440 / 1024 / 390 三种宽度；
- 检查页面标题、控制台错误、横向溢出；
- 检查 5 个示例的方向数据、候选数、学者数、venue 数；
- 检查直达路由默认状态；
- 检查手机端详情顺序与点选后的滚动位置。

结果：

```text
ALL_CHECKS_PASSED
```

本地与公网均通过，无控制台错误。

新增 `competition/scripts/capture_screenshots.mjs`，初版生成 11 张截图；界面重构后扩展为 17 张：

- 桌面 10 张：首页、候选、体检、计划、学者、venue、文献空白、方法论、关于、深色主题；
- 平板 1 张：1024px 候选与详情；
- 手机 6 张：首页、结果、详情、筛选、文献空白、方法论。

最后一次截图在最终移动端 `scroll-margin-top` 与路由回顶调整之后重新生成，输出 `NO_BROWSER_ERRORS`。

## 5.1 界面重构与二次验收

第一版功能完整，但视觉仍偏通用 SaaS。按用户反馈，重新研究了 ResearchRabbit、Consensus、Litmaps 的界面层级与留白，确定“科研档案柜 / 学术期刊工作台”方向，并在 Qoder 中完成：

- 重写 `index.html` 外壳：文字印章品牌、深色索引栏、OFFLINE INDEX 状态、主题切换；
- 重写 `styles.css`：纸面背景与细网格、墨色正文、深青 / 赭石强调、衬线标题、等宽编号、2–4px 小圆角、细线分隔；
- 重写首页输入区、候选列表、Research Brief、9 格结构审计、文献矩阵、导师目录、venue 卡片、方法论目录、计划页与关于页；
- 保留 Nudge 的 `--site-*` 变量契约，深浅主题同时支持系统偏好与手动切换。

重构过程中发现并修正：

- 桌面端误显示汉堡菜单和侧栏关闭按钮（CSS 通用选择器覆盖）；
- 手机端 Toast 位于底部时遮住“生成候选”按钮，改为顶部提示；
- 390px 下详情页签被裁切，压缩页签内边距与字号；
- 方法论卡片的名称与适用场景粘连，改为块级排版；
- 路由切换保留上一页滚动位置，改为 `requestAnimationFrame` 后立即回到页首；
- 整页截图时固定侧栏只覆盖 1000px，截图改为按内容高度设置视口。

二次回归结果：

```text
ALL_CHECKS_PASSED
NO_CONSOLE_ERRORS
NO_BROWSER_ERRORS
```

7 个路由 × 1440 / 1024 / 390 全部通过；5 个示例方向均生成 18 条候选、12 位导师与有效 venue；移动端详情顺序和点选滚动均通过。

## 5.2 矩阵联动与题谱星图（第四轮）

用户提出：文献空白的方法 × 任务矩阵是否会随搜索更新；能否做一个按论文数量决定星点大小、按大类着色、并带个人层的科研知识图谱。本轮改动：

- **导出层**：`export_web_data.py` 为每个方向增加 `localGap`（方向内方法 / 任务共现）；`index.json` 增加星图元数据与逐方向本地命中数；`index.json` 改为在方向循环结束后写入。
- **矩阵联动**：`app.js` 的文献空白页增加「全库 / 当前方向」分段按钮，当前方向模式读取 `directionData.localGap`；无命中时显示 0 行并写明原因。
- **星图**：新增 `assets/atlas.js` 与 `#/atlas` 路由。387 个方向为星点，半径与透明度由本地命中数决定；24 个大类先螺旋分布再分簇，类别标签做碰撞避让；连线为同大类 / 共享关键词；支持搜索联想、拖拽、缩放、图例筛选、方向详情；金色环映射本机已存选题。
- **边界**：星图只表达结构分组，不是引用图或语义相似度图；页面明确说明是种子布局，并保留未来替换真实布局的接口。
- **验收**：`check_site.mjs` 扩展到 8 路由 × 3 宽度，新增 387 星点 / 24 大类 / 24 图例、搜索、图例、个人层、矩阵全库与当前方向切换断言；`capture_screenshots.mjs` 扩展为 23 张截图。本地回归输出 `ALL_CHECKS_PASSED`、`NO_CONSOLE_ERRORS`、`NO_BROWSER_ERRORS`。

## 5.3 先识别方向，再生成候选（第五轮）

用户反馈：输入「密码学」后立刻给出 18 条候选，没有展示识别到的领域和依据，不严谨。本轮把生成流程拆成三步：

- **状态机**：`state.phase` 增加 `review`，识别结果暂存在 `state.pending`（原始输入、命中方向、置信度、候选方向、方向数据）；确认前 `state.candidates` 保持为空。
- **识别页**：新增 `reviewHtml()`，展示原始输入、命中方向与大类、置信度、别名映射、实际命中的方向名 / 术语 / 关键词及类型、相邻方向改选入口；同时写明匹配只在 387 个方向名 / 术语 / 关键词中做字符串匹配，不是语义检索，也不是文献查新。
- **数据边界**：识别页给出本地文献数、方向导师数、venue 数与全库标题数；本地文献为 0 时明确说明只提供结构参考。
- **未命中兜底**：`matchDirection` 低于阈值时显示「未命中方向库」，说明库覆盖 387 个方向，并提供「用全库数据生成」按钮（`data-mode="fallback"`）。
- **结果页**：识别条持续显示置信度 / 领域 / 方向 / 匹配依据 / 数据量，并提供「重新识别」；示例按钮保留原示例名作为选题标题，识别到的大类单独展示。
- **交互细节**：识别后输入区切换为紧凑模式并自动滚到识别页；确认后自动滚到识别条；星图点选方向时自动确认，保持一步直达结果。
- **验收**：`check_site.mjs` 增加识别页、识别依据、未命中兜底断言；个人层、导师 / venue、矩阵等原有断言改为先确认方向；`capture_screenshots.mjs` 增加 `desktop-review`、`mobile-review`，共 23 张。

本地回归：

```text
PASS 示例「单目深度估计」先进入方向识别页
PASS 识别页展示方向 / 领域 / 匹配依据 (3D与几何视觉 · 计算机视觉)
PASS 未命中方向时先说明边界并提供全库兜底 (0 个近似方向)
NO_CONSOLE_ERRORS
ALL_CHECKS_PASSED
```

## 5.4 输入校验、旧结果清理与星图移除（第六轮）

用户提供截图：输入框只有「12」，下方出现「计算思维与K12教育」联想，并保留着上一方向的 18 条候选；要求优化这种情况，并移除星图。

- **原因**：`suggestDirections` 对 `12` 做子串匹配，命中 `K12` / `yolov12`；同时输入新内容不会清空 `state.direction` 与 `state.candidates`，旧结果继续显示。
- **输入校验**：`core.js` 新增 `isMeaningfulDirectionQuery`：去空白后至少 2 个字符、至少含一个汉字或拉丁字母、不能是纯数字 / 符号；`matchDirection` 与 `suggestDirections` 共用该判断，不满足时直接返回空结果。
- **旧结果清理**：`app.js` 的无效输入分支调用 `resetDirection(query)`，清空方向、候选、识别条与识别页，再就地提示「不像一个研究方向：至少输入 2 个汉字，或一个完整术语（如 目标检测、SLAM）」并弹出 toast；`updateSuggestions` 对无效输入直接隐藏联想框。
- **输入变更提示**：结果页修改输入但尚未重新识别时，显示「下方仍是旧方向的识别结果」；重新识别或清空后隐藏。
- **星图移除**：删除 `assets/atlas.js`、`#/atlas` 路由与页面渲染、侧栏 / 移动端入口、`i-atlas` 图标、星图样式、`index.json` 星图元数据、导出脚本中的星图字段，以及 `desktop-atlas` / `mobile-atlas` / `mobile-atlas-map` 三张截图；导航恢复为 7 个页面、移动端 5 项。
- **验收**：`check_site.mjs` 改为 7 路由 × 3 宽度，新增纯数字不识别、短数字不联想、旧结果清理三类断言；`capture_screenshots.mjs` 改为 21 张并新增 `desktop-validation`。本地回归：

```text
PASS 纯数字「12」不进入识别页也不生成候选
PASS 短数字输入给出明确提示且不出联想
PASS 已有结果时输入无效方向会清掉旧结果并给出提示
NO_CONSOLE_ERRORS
ALL_CHECKS_PASSED
```

## 5.5 联想框浮层修复（第六轮补丁）

用户粘贴截图：输入框获得焦点后，方向联想被选题面板底边裁掉，看起来像被下方识别条遮住。

- **定位**：`.query-panel` 的 `overflow: hidden` 会裁掉绝对定位的 `#suggestBox`；面板也未建立独立层级。
- **样式修复**：`.query-panel` 改为 `overflow: visible`、`position: relative`、`z-index: 5`；`.query-brief` 与 `.query-form` 分别补圆角，窄屏堆叠与紧凑模式单独覆盖；`.suggest` 提升到 `z-index: 30`，`max-height: min(300px, 45vh)`，改用大阴影。
- **交互修复**：`app.js` 增加输入框的 `focusin` / `click` 监听，点击即展开联想；空输入展示 5 个示例方向，无效输入仍不联想。
- **完整列表**：`suggestDirections` 默认上限从 7 提升到 60；联想框顶部增加固定计数条（「N 个 · 可上下滚动」），最大高度改为 `min(440px, 60vh)`，方向多时滚动查看。`计算机视觉` 从 7 条变为 27 条。
- **验收**：`check_site.mjs` 新增「联想下拉浮在页面上方、不被容器裁切」与「大类查询展示完整方向列表并可滚动」断言，用 `elementFromPoint` 检查浮层中心命中自身，并检查面板 `overflow`、计数条与滚动高度；21 张截图重新生成，`NO_BROWSER_ERRORS`，本地回归 `ALL_CHECKS_PASSED`、`NO_CONSOLE_ERRORS`。

## 6. Qoder Sites 发布

1. 在 `competition/site/` 建立 Qoder Sites 项目，写入 `.选题智库.qoder.site`，登记 7 个页面与 appearance / radius / spacing / typography / motion 能力；
2. 将 `index.html`、`assets/`、`data/` 复制到 `dist/`，并对 `dist/` 做敏感信息扫描：`api_key`、`sk-`、`llm_config`、本机用户名、本地绝对路径均无命中；
3. 通过 `prepare_site` 上传 `dist/`，等待验证操作完成；首次描述文件处于 pending，使用同一 action 与 inputs 重试后写入成功；
4. `publish_site` 后验证 `published: true`；
5. 初始访问策略为 private，按赛事「评委点开即可访问」的要求改为 public，并读回确认 `access_mode: public`。

当前状态（2026-11-17 核对）：

- 站点：`题谱`
- 地址：https://topic-compass-jzkhsw942zj.qoder.website
- lifecycle：active
- access_mode：public
- hasPublishedContent：true

### 6.1 重构版重新发布

界面重构后，将新的 `index.html`、`styles.css`、`app.js` 同步到 `dist/`，核对 `data/` 与 `assets/` 与源目录一致，再用新的发布动作重新准备并发布：

- 草稿校验 `artifactReady: true`、`canPublish: true`；
- 发布后 `published: true`、`readiness: publication_completed`；
- 公网 7 个路由 × 1440 / 1024 / 390 回归通过，输出 `NO_CONSOLE_ERRORS` 与 `ALL_CHECKS_PASSED`；
- 抽查公网 `styles.css` 与 `app.js`，SHA-256 与 `dist/` 完全一致；`index.html` 仅多出 Qoder 平台注入的水印脚本，页面标记已是新外壳（`OFFLINE INDEX`、主题切换、文字印章品牌）。

### 6.2 更名与第三轮发布

用户反馈原名「选题智库」偏大众，并希望参考 `machinelearningwithme.com` 的温暖、图谱化科研界面。本轮完成：

- 作品名改为 **题谱 / RESEARCH QUESTION ATLAS**；统一更新 `index.html`、`favicon.svg`、`app.js` 中的标题、面包屑与关于页，保留路由、数据和站点 ID；
- 重写 `styles.css`：奶油纸面、墨蓝标题、赭棕主笔、金色批注、大圆角卡片、半透明浅色侧栏与胶囊页签；首屏加入抽象 Atlas 图谱；深色主题改为暖黑纸面；
- 本地重跑 7 路由 × 1440 / 1024 / 390、5 个示例方向、直达路由默认状态与移动端详情顺序，输出 `ALL_CHECKS_PASSED`、`NO_CONSOLE_ERRORS`；
- 重新生成 17 张截图，复核首屏、候选详情、文献空白、导师、期刊、方法论、研究与深色主题；修正图谱椭圆误继承描边、深色输入框与左侧介绍区仍为浅色的问题；
- 同步 `dist/` 后更新站点显示名并重新发布，再对公网版本重跑同一套回归。

发布结果：

- 新发布动作 `1f55f21a-474a-4b5c-8232-afc76bc7377b`，验证 `published: true`、`readiness: publication_completed`；
- 公网标题为 `题谱 · 从研究方向到可核查选题`；线上 `styles.css` 与 `app.js` 的 SHA-256 与 `dist/` 完全一致；
- 公网回归覆盖 7 路由 × 1440 / 1024 / 390、5 个示例方向与移动端详情顺序，输出 `ALL_CHECKS_PASSED`、`NO_CONSOLE_ERRORS`；
- Qoder Sites 项目显示名已更新为「题谱」，站点 ID、地址与 public 访问策略保持不变。

### 6.3 矩阵联动与星图版发布（历史，星图后已移除）

- 设计工作台当时登记第 8 个页面「题谱星图」（`#/atlas`），保留原有 7 个页面与设计能力；该页面已在第六轮删除，设计登记同步回到 7 个页面；
- 同步 `dist/`：`index.html`、`assets/app.js`、`assets/atlas.js`、`assets/core.js`、`assets/styles.css`、`assets/favicon.svg` 与 `data/`；
- 敏感信息复扫：`sk-`、`api_key`、`llm_config`、本机用户目录、`research_memory` 等均无真实命中（`mask-image` 属于误报）；
- 新发布动作 `7f54c2c2-da6f-4ad4-a7ea-7d08ccc5f433`：草稿 `artifactReady: true`、`canPublish: true`，发布后 `published: true`、`readiness: publication_completed`；
- 公网回归覆盖 8 路由 × 1440 / 1024 / 390、5 个示例方向、星图 387 方向 / 24 大类 / 搜索 / 图例 / 个人层、矩阵全库与当前方向切换，输出 `ALL_CHECKS_PASSED`、`NO_CONSOLE_ERRORS`；
- 公网 `app.js`、`atlas.js`、`styles.css`、`data/index.json` 的 SHA-256 与 `dist/` 完全一致。

### 6.4 方向识别版发布（历史）

- 同步 `dist/`：`index.html`、`assets/app.js`、`assets/styles.css`，其余资源与上一版一致；
- 敏感信息复扫：真实密钥模式、`llm_config`、本机路径均无命中；
- 新发布动作 `81339cb7-7cdc-4b07-97a3-1509e92a72eb`：草稿 `artifactReady: true`、`canPublish: true`，发布后 `published: true`、`readiness: publication_completed`，release `01a1e958-2106-76dc-bb4a-f1441f2f5117`；
- 当轮公网回归覆盖当时的 8 路由 × 1440 / 1024 / 390、识别页与未命中兜底、5 个示例方向、星图与矩阵联动，输出 `ALL_CHECKS_PASSED`、`NO_CONSOLE_ERRORS`；
- 公网 `app.js`、`styles.css`、`data/index.json` 的 SHA-256 与 `dist/` 完全一致（`app.js` `17af58b1…`、`styles.css` `04976799…`）。该版本后来被 6.5 的移除版取代。

### 6.5 输入校验与星图移除版发布

- 设计工作台页面从 8 个更新为 7 个，删除「题谱星图」，保留选题工坊、文献空白、导师与院校、期刊会议、科研方法论、研究计划、关于与数据范围；
- 同步 `dist/`：`index.html`、`assets/app.js`、`assets/core.js`、`assets/styles.css`、`assets/favicon.svg`、`data/index.json`；`dist/assets/` 不再包含 `atlas.js`；
- 敏感信息复扫：真实密钥模式、`llm_config`、`research_memory`、本机用户名与路径均无命中；
- 新发布动作 `384d5b7d-510e-459c-ab9b-ef1924e3b06e`，草稿 `artifactReady: true`、`canPublish: true`，发布后 `published: true`、`readiness: publication_completed`，release `01a1e965-faf0-7108-a5e7-3cd931c04e85`，deployment `01a1e965-260a-791c-8ab6-09d3c5a08d48`；
- 公网回归覆盖 7 路由 × 1440 / 1024 / 390、无效输入提示与旧结果清理、5 个示例方向、矩阵全库与当前方向切换，输出 `ALL_CHECKS_PASSED`、`NO_CONSOLE_ERRORS`；
- 公网 `app.js`（`ece2953e…`）、`core.js`（`b60314f1…`）、`styles.css`（`5f0e5c79…`）、`data/index.json`（`90326567…`）的 SHA-256 与 `dist/` 完全一致；`index.html` 因平台注入 Qoder 水印而按预期不同。

### 6.6 联想框浮层修复发布

- 同步 `dist/`：`assets/app.js`、`assets/styles.css`，其余资源不变；
- 新发布动作 `96a0c2a5-2b07-456d-8aaf-2ca5dcdaaaac`，发布后 `published: true`、`readiness: publication_completed`，release `01a1e982-9c5c-7f3c-8e13-3840e029828e`，deployment `01a1e981-e9aa-7336-8ccf-ff191230cb76`；
- 公网回归覆盖联想浮层、7 路由 × 1440 / 1024 / 390、无效输入清理与矩阵联动，输出 `ALL_CHECKS_PASSED`、`NO_CONSOLE_ERRORS`；
- 公网 `app.js`（`b2345dc6…`）、`styles.css`（`f20902df…`）与 `dist/` 完全一致。

### 6.7 联想数量与滚动发布

- 用户反馈「计算机视觉」只联想 7 条，希望可以滚动或完整展示；排查确认是 `suggestDirections` 展示层默认上限 7 条，方向库本身未缺数据；
- 同步 `dist/`：`assets/app.js`、`assets/core.js`、`assets/styles.css`，其余资源不变；
- 默认上限提升到 60，「计算机视觉」变为 27 条；联想框最高 `min(440px, 60vh)`，内部滚动，顶部固定「匹配方向 N 个 · 可上下滚动」；
- 新发布动作 `47daaf40-3b1a-4cc4-a437-0d4e8cf184ef`，发布后 `published: true`、`readiness: publication_completed`，release `01a1e988-543d-7972-9dc1-0767cca7e003`，deployment `01a1e987-0c5a-7a72-a037-85c2f11be25a`；
- 公网回归覆盖 7 路由 × 1440 / 1024 / 390、联想浮层、27 条完整列表与无效输入清理，输出 `ALL_CHECKS_PASSED`、`NO_CONSOLE_ERRORS`；
- 公网 `app.js`（`b95c1d54…`）、`core.js`（`90458d3d…`）、`styles.css`（`34a99765…`）、`data/index.json`（`90326567…`）与 `dist/` 完全一致。

### 6.8 应用领域、标签组合与导师详情（第八轮）

用户指出：方向选择没有考虑应用领域、可选太少；需要标签组合式选题；候选要说清常用数据集；三个维度条看不出差异；导师地区太少，且卡片不能点进去看作者与官网链接。

- **数据扩展**：新增 `competition/scripts/expand_applications.mjs`（幂等），在 387 个基础方向上补充应用标签与公开基准，并新增 36 个应用型方向（`d388`–`d423`），方向库达到 25 类目 / 423 方向；`applications.json` 提供 37 个标签（5 组）与 5 个任务偏好。
- **数据集层**：整理 176 个公开基准，按方向给出常用数据集、指标与代表基线；补充 `红外与低光视觉`、`3D与几何视觉`、`生物信息` 等方向级覆盖，修复别名方向落到大类后显示通用 ImageNet / COCO 的问题，并同步 `d023` / `d025` / `d219`。
- **匹配逻辑**：新增 `detectApplications` / `appBoost` / `appsForDirection` / `recommendDirections`，应用场景参与方向匹配与推荐排序。
- **前端交互**：工坊增加 `search / tags / browse` 三种输入页签；标签组合按命中数推荐方向并回填识别流程，识别条标注「标签组合命中」或「目录选择」；候选卡与详情新增推荐数据集、指标与基线卡片；三维度改为带中位数、差值、排名的可比较图表。
- **导师页**：地区筛选扩展到 9 个大区 / 46 个地区（31 个省级行政区 + 港澳台 + 12 个海外地区），补全别名；学者卡片可点击或回车打开详情弹层，提供 ORCID、OpenAlex、DBLP、Google Scholar、机构主页、个人主页六类入口，未核验主页明确标为「搜索入口」，支持 Escape 关闭与移动端底部抽屉。
- **验收**：`check_site.mjs` 增加标签组合、目录浏览、数据集、维度差异、地区目录与导师弹层的断言，并修正 SPA 状态刷新方式（`localStorage.clear()` 后 `Page.reload({ ignoreCache: true })`）与 Escape 全局关闭；`capture_screenshots.mjs` 扩展为 25 张。本地回归输出 `ALL_CHECKS_PASSED`、`NO_CONSOLE_ERRORS`、`NO_BROWSER_ERRORS`。
- **补丁**：手机端方向输入标签重复渲染的问题已修掉（结果态不再额外输出一个 `query-label`），并把表单在窄屏排到图谱与统计之前、三个入口压成一行；新增断言「手机端方向输入标签只出现一次」。
- **发布**：同步 `dist/`（423 个方向文件、`applications.json`、`benchmarks.json` 等），敏感信息复扫无命中；发布动作 `7081076a-cf1c-49b8-ac62-9df72a5eff9c`，`published: true`、`readiness: publication_completed`，publish operation `01a1e9cd-37a1-738b-b4b9-a061471ae435`；
- 公网回归覆盖 7 路由 × 1440 / 1024 / 390、标签组合、目录浏览、数据集、三维度、地区目录与导师弹层，输出 `ALL_CHECKS_PASSED`、`NO_CONSOLE_ERRORS`；
- 公网 `app.js`（`a12aec7b…`）、`core.js`（`a96c7d4b…`）、`styles.css`（`765b775d…`）、`data/index.json`（`903dde39…`）、`applications.json`（`f62e983b…`）、`benchmarks.json`（`c6b0310b…`）、`advisors.json`（`8e766f31…`）与 `dist/` 完全一致。

### 6.9 正式版体验收敛与素材库（第九轮）

用户按 8 张截图反馈：整体 UI 要更贴近正式使用；结果页要能回到方向确认并保留刚才的选择；确认页多余说明与右侧演示卡要移除；原始数据量不在结果页出现，改由独立素材库解释；移除文献空白；方向不确定时给标签与「大类 → 小类」两级入口并按关键词关联强度推荐；导师页展示全部学者、平铺 / 列表双视图；个人主页不得再跳搜索引擎，改为院校真实链接。

- **工坊回流**：结果页「重新识别」改为「调整方向」（`edit-direction`），回到方向确认页并保留输入、识别方向与应用场景；「重新输入」（`reset-direction`）才清空。确认页删除右侧「这次不做什么 / 生成后会得到」与原始库计数。
- **候选数量**：取消固定 18 条，按方向关键词与场景标签关联强度生成 12–22 条，三类策略各至少 3 条；结果栏只保留匹配数与场景。
- **素材库**：新增 `scripts/build_materials.mjs` 与 `#/materials` 路由，输出 `materials.json`（423 方向 / 194 数据集 / 345 文献统计 / 126 venue / 12,450 学者）；Web 端移除文献空白路由、入口与截图。
- **方向发现**：`applications.json` 扩展到 42 个标签（5 组）；`browsePanelHtml` 改为两级目录，小方向按 `buildTermCounts` 的关键词共现关联强度排序，标注强 / 中 / 弱关联。
- **导师目录**：新增 `scripts/export_scholars.mjs`，从 `advisor_directory_full.json` 的 15,952 条记录按 ORCID（无 ORCID 时按姓名 + 机构）去重为 12,450 位，输出 7.8 MB `advisors.json`；前端取消 2,000 条截断，提供平铺 / 列表、分页加载与「加载更多」。
- **真实主页**：个人主页只取 CSRankings（421 位）与 ORCID（423 位）公开链接，共 844 位；11,967 位有院校官网；新增离线脚本 `scripts/enrich_direction_links.mjs`，为 423 个方向文件补 4,297 条院校链接与 1,026 条可核验个人主页（海外优先 CSRankings，缺少机构记录时从学术主页域名推导院校根域）。删除 Bing 搜索入口与「搜索入口」标签；无主页时只显示院校官网、ORCID、DBLP、Google Scholar。地区空结果提供「查看全部地区学者」清空筛选。
- **样式收敛**：新增 `assets/refine.css`，压缩首屏说明为 4 步流程条，统一快速大类、两级目录、确认页、素材库与导师工具栏的间距、层级与断点。
- **验收**：`check_site.mjs` 覆盖 7 路由 × 1440 / 1024 / 390、回到方向确认并保留输入、12–22 条候选、结果栏无原始计数、两级目录关联标签、素材库关系与状态保留、12,450 位学者、平铺 / 列表 / 加载更多、真实主页 / 院校官网、无搜索跳转、空地区清空；输出 `ALL_CHECKS_PASSED`、`NO_CONSOLE_ERRORS`。`capture_screenshots.mjs` 更新为 26 张（新增 `desktop-materials*`、`desktop-advisors-list`、`desktop-tags`、`desktop-browse`，删除 3 张 gap 截图），输出 `NO_BROWSER_ERRORS`。
- **发布**：`dist/` 由 `site/` 全量重建（含 `refine.css`、`materials.json`、423 个补全链接的方向文件），敏感信息复扫无命中；发布动作 `a429275a-9050-4ab1-a214-bcd694b63ef8`，`published: true`、`readiness: publication_completed`，publish operation `01a1ea53-bc55-7b97-adbb-b606ba43738c`；
- 公网回归覆盖 7 路由 × 1440 / 1024 / 390、回到方向确认、12–22 条候选、两级目录、素材库、12,450 位学者、平铺 / 列表、真实主页与空地区清空，输出 `ALL_CHECKS_PASSED`、`NO_CONSOLE_ERRORS`；
- 公网 `app.js`（`3db9ffc4…`）、`core.js`（`f6634574…`）、`styles.css`（`765b775d…`）、`refine.css`（`7202939a…`）、`data/index.json`（`903dde39…`）、`applications.json`（`f62e983b…`）、`benchmarks.json`（`c6b0310b…`）、`materials.json`（`3180bcdb…`）、`advisors.json`（`b9a9593d…`）与 `dist/` 完全一致；`index.html` 由平台注入水印脚本，其余字节一致。

### 6.10 ORCID 核验与论文库（第十轮）

用户在天池论坛看到「导师雷达」项目后，要求学习其技术、链接与数据来源，优化导师库与论文库；截图指出 Andrew Zisserman 被标成上海交通大学，个人主页入口是搜索页。本轮沿用「公开数据 + 离线快照 + 说明边界」的做法，不接入在线模型或实时接口。

- **数据来源**：新增 `scripts/enrich_orcid.mjs`。对 423 个方向推荐学者里的 1,292 个 ORCID，读取 ORCID 公共 API v3.0 的 `/record`（姓名、任职、研究者链接、公开作品），按本地缓存增量拉取，可断点续跑；任职机构再查 ROR 机构库，取得机构官网、ROR 标识、国家与地区。输出 `orcid.json`（1,292 条记录）与 `papers.json`（8,254 篇）。
- **机构修正**：只在 ORCID 存在「无结束日期」的任职记录时覆盖原机构，并同步机构中文名、地区、院校官网与 ROR；本轮 1,177 个 ORCID 姓名匹配，657 位有任职记录，477 位修正机构，90 位补到公开个人主页，867 位有公开作品。Zisserman 由「上海交通大学」修正为 University of Oxford，地区英国，入口指向 ox.ac.uk 与 ror.org/052gg0110。
- **发表活跃度**：按 ORCID 作品去重后统计 2021–2026 年逐年篇数、近五年篇数、最近发表年份与收录总数；学者详情用 6 根柱状图展示，并明确「只统计该 ORCID 下的公开作品，不代表全部成果」。
- **论文库**：新增 `#/papers` 路由与 `papers.json`，收录 8,254 篇期刊 / 会议 / 书章 / 预印本等学术类型作品（按 DOI 或标题去重），来自 853 位推荐学者、覆盖 19 个领域；可按题目、学者、年份、类型、领域筛选、分页加载，点标题跳 DOI；学者详情可一键「在论文库查看这位学者」。晚于核验日期（2026-11-18）的提前登记年份不计入，页面写明这一点。
- **主页与入口**：个人主页仍只用 CSRankings / ORCID 的公开链接；没有核验主页时不生成任何搜索跳转，只给院校官网、ORCID、ROR、DBLP 与 Google Scholar，并在弹层底部说明「未收录个人主页」。
- **姓名显示**：目录里 DBLP 风格的 `0001` 后缀只从显示层去掉，匹配与去重仍用原值，避免改坏索引。
- **移动端**：底部导航增加「论文」后为 6 项，390px 下不换行、不横向溢出。
- **验收**：`check_site.mjs` 覆盖 8 路由 × 1440 / 1024 / 390，新增「Zisserman 机构为 Oxford 且不再出现上海交通大学」「详情含 ORCID 与 ROR 链接」「6 根活跃度柱」「近期论文按钮进入论文库并按学者筛选」「论文库分页、关键词、领域筛选与加载更多」等断言；`capture_screenshots.mjs` 扩展为 31 张，新增学者入口、论文库桌面与手机截图。本地回归输出 `ALL_CHECKS_PASSED`、`NO_CONSOLE_ERRORS`、`NO_BROWSER_ERRORS`。
- **发布**：`dist/` 由 `site/` 全量重建（439 个文件 / 23 MB，含 `orcid.json`、`papers.json`），敏感信息复扫无命中（`sk-` 的 2 处命中均为论文标题中的 `Task-` / `risk-`）；发布动作 `24051a8e-9e60-4cab-a2d7-26cb9c20735d`，publish operation `01a1eaba-23ab-7e44-9c5d-219d8cbb456a`，release `01a1eaba-23ab-7df6-b819-8a8eec4bc76c`，验证 `published: true`、`readiness: publication_completed`；
- 公网回归覆盖 8 路由 × 1440 / 1024 / 390、ORCID 机构修正、活跃度、论文库筛选与分页，输出 `ALL_CHECKS_PASSED`、`NO_CONSOLE_ERRORS`；
- 公网 `app.js`（`a158325d…`）、`core.js`（`caf2fa29…`）、`styles.css`（`765b775d…`）、`refine.css`（`11306d01…`）、`orcid.json`（`78c127c7…`）、`papers.json`（`c16c323c…`）、`advisors.json`（`b9a9593d…`）、`data/index.json`（`903dde39…`）的 SHA-256 与 `dist/` 完全一致。

### 6.11 院校目录与地区待核验（第十一轮）

用户反馈两件事：地区应按大学所在地区划分，没有地区信息的人也要有地方可去；在页签旁增加「院校」入口，列出所有学校，点进学校查看对应导师。

- **地区归档**：新增 `regionOf`，先取规范化省份，其次国家；离线快照中两者都为空的记录归入新分组「地区待核验」。地区下拉改为「全部地区（12,450 位）」+ 待核验分组 + 9 个大区 / 46 个地区，共 10 组 / 48 项；总数改为当前列表的真实行数，不再出现「全部地区（9,314 位）」与 12,450 位总数不一致。学者卡片在地区处显示「地区待核验」虚线徽标。
- **数据事实**：12,450 位学者中 2,973 位的院校在离线快照里没有可核验的省市或国家，归入待核验分组；该分组可正常筛选、分页与查看详情，不会被隐藏或从总数里悄悄扣掉。页面范围说明直接写出这个数字与原因。
- **院校视图**：页签增加「院校 2,393」。按规范化英文机构名聚合，避免同一所学校因 ORCID 中文译名不同被拆成多条；每条显示中文校名、英文校名、地区与收录人数，支持校名搜索、院校所在地区筛选和每次 80 所的加载更多。点进学校后显示该校全部学者，继续支持地区筛选、平铺 / 列表切换、分页与学者详情，并可返回院校列表；空结果给出「查看全部地区院校」。
- **状态处理**：切换页签会重置院校、地区和搜索条件；在院校目录内切换地区只重绘列表，保留搜索框光标；直达院校视图时才加载学者数据，已加载后不重复请求 7.8 MB 文件。
- **移动端修复**：院校行作为网格子项默认 `min-width: auto`，长英文校名把行撑到 412px，390px 下人数与箭头被裁切；补 `min-width: 0` 后行宽回到 328px。同步让搜索元信息在窄屏换行。
- **验收**：`check_site.mjs` 新增「院校目录列出全部学校并提供地区待核验」「院校目录可按地区待核验筛选」「校名检索」「点进院校查看对应导师」「未划分地区学者归入待核验分组」「手机端院校目录无横向溢出」等断言，地区目录断言更新为 10 组 / 48 项；原有空地区、平铺 / 列表和 ORCID 断言的执行顺序调整为在院校视图之后回到按方向推荐。`capture_screenshots.mjs` 扩展为 34 张，新增 `desktop-advisors-institutions`、`desktop-advisors-school`、`mobile-advisors-institutions`。本地回归输出 `ALL_CHECKS_PASSED`、`NO_CONSOLE_ERRORS`、`NO_BROWSER_ERRORS`。
- **发布**：`dist/` 全量重建（439 个文件 / 23 MB），敏感信息与本地路径复扫无命中（`sk-` 命中均为论文标题中的 `task-oriented` 等词）；发布动作 `9adc3d76-469b-4c83-9991-9dda79b80128`，publish operation `01a1ead4-4333-777e-8c05-f6501cfe1e10`，验证 `published: true`、`readiness: publication_completed`、`access_mode: public`；
- 公网回归覆盖 8 路由 × 1440 / 1024 / 390，院校目录、地区待核验、点进学校、ORCID 修正与论文库，输出 `ALL_CHECKS_PASSED`、`NO_CONSOLE_ERRORS`；
- 公网 `app.js`（`eceee6a4…`）、`core.js`（`caf2fa29…`）、`styles.css`（`765b775d…`）、`refine.css`（`dbec971f…`）、`advisors.json`（`b9a9593d…`）、`orcid.json`（`78c127c7…`）、`papers.json`（`c16c323c…`）、`data/index.json`（`903dde39…`）的 SHA-256 与 `dist/` 完全一致；`index.html` 由平台注入水印脚本，其余字节一致。

### 6.12 院校地区补齐、学者详情扩面与期刊页搜索（第十二轮）

用户提出四点：地区待核验应按学校实际位置划分，需要真正去查；只有少数学者能看到 Zisserman 那样的完整详情，希望扩大到其他人；期刊页需要平铺 / 列表切换；「按方向推荐」应能直接在页内输入方向搜索，而不是先回工坊。

- **院校地区补齐**：新增 `enrich_institution_regions.mjs`，从学者原始记录里的 OpenAlex 机构 ID 出发，逐所查询 OpenAlex institutions 的 `geo.region`、`geo.city`、`country_code` 与 `ids.ror`，把中国机构映射为省级行政区、海外机构映射为中文国家名，写回 `advisors.json` 的 `province` / `country` / `institutionCity` / `institutionRor` / `regionSource`。首轮 31 所学校遇到 HTTP 429，加入退避重试并让缓存里的错误记录重新请求；最终 **425 / 425 所**原本缺地区的学校全部解析，**3,136 位**学者补齐地区与院校 ROR，`地区待核验` 归零，院校目录中的每所学校都能显示所在地区。生成 `data/institution_regions.json` 作为核对账单（425 条，含 OpenAlex 地区、ROR 与人数）。
- **不再有「地区待核验」桶**：地区下拉与院校目录在待核验为 0 时不再渲染该分组；页面范围说明改为「全部 12,450 位均已按院校所在地归档」，并写明数据来自 OpenAlex 机构地理字段与 ROR 离线快照。
- **学者详情扩面**：详情弹层现在对所有学者显示地区徽标与统计中的「地区」；院校 ROR 标识在 ORCID 记录缺失时回退到机构库 ROR；对没有命中 ORCID 公开记录快照的学者，底部明确写出原因（「ORCID 标识已收录但快照未覆盖」或「暂无 ORCID 标识」），不再让用户误以为数据丢失。卡片脚注也区分「ORCID 已核验 / 个人主页已收录 / 院校官网已收录 / ORCID 可核验 / 仅索引记录」。没有为了覆盖率去抓取 8,000 多条 ORCID 作品记录：那会把 `orcid.json` 与 `papers.json` 从 MB 级推到百 MB 级，Web 静态版无法承受；因此活跃度与近期论文仍只覆盖姓名匹配的 1,177 位，边界直接写在弹层里。
- **期刊页**：`#/venues` 的「按方向推荐」页签内新增研究方向输入框与「推荐 venue」按钮，复用方向库匹配与 `loadDirectionData`，匹配期间显示「正在匹配…」；结果与「全部 126 个」都支持平铺 / 列表切换，切换只改容器类名，不丢输入内容；直达期刊页不再强制跳到「全部」，默认展示可搜索的推荐入口。列表视图为单行卡片（名称与 CCF、类型、国家、领域、简介、主页），手机端自动转回纵向卡片。
- **验收**：`check_site.mjs` 更新为「期刊页默认提供方向推荐入口」「期刊页可直接输入方向并推荐 venue」「期刊推荐支持平铺 / 列表并保留输入」「全部目录沿用列表视图并可切回平铺」「手机端期刊页提供方向搜索与视图切换」「手机端期刊列表无横向溢出」；地区相关断言改为「院校目录全部学校均按校址归入地区」「按北京筛选院校」「导师目录全部按院校地区归类，无待核验分组」。本地与公网回归均为 `ALL_CHECKS_PASSED`、`NO_CONSOLE_ERRORS`；截图扩展到 36 张，新增 `desktop-venues-rec`、`desktop-venues-list`。
- **发布**：`dist/` 由 `site/` 全量重建（440 个文件 / 24 MB），敏感信息与本地路径复扫无命中（`sk-` 命中仍为论文标题中的普通英文词）；发布动作 `3b59d456-473b-4ac4-93a9-db6082d3a43c`，publish operation `01a1ec7f-682e-715d-800e-8388647cd0fb`，验证 `published: true`、`readiness: publication_completed`、`access_mode: public`。
- 公网 `app.js`（`7bb0b7cd…`）、`core.js`（`caf2fa29…`）、`styles.css`（`765b775d…`）、`refine.css`（`24b86371…`）、`advisors.json`（`65c8598c…`）、`institution_regions.json`（`136d85fa…`）、`orcid.json`（`78c127c7…`）、`papers.json`（`c16c323c…`）、`data/index.json`（`903dde39…`）的 SHA-256 与 `dist/` 完全一致；`index.html` 由平台注入水印脚本，其余字节一致。

### 6.13 ORCID 全量扩面、论文分类补齐与发布（第十三轮）

用户反馈：没有 ORCID 快照的学者仍看不到活跃度和近期论文，希望把有 ORCID 标识的那批尽量补上，让大部分详情页都能像 Zisserman 一样完整。本轮在离线快照、同名保护和诚实边界内做扩面，不接入实时接口。

- **目标扩面**：`enrich_orcid.mjs` 从只处理 423 个方向的 1,292 个 ORCID，扩展到目录内 9,398 个与方向库独有 348 个，去重后 9,746 个目标；全部写入本地缓存，支持断点续跑。最终 9,730 个有公开记录，16 个无记录或已注销。
- **身份匹配**：8,602 位姓名匹配，其中 1,215 位是方向推荐学者、7,387 位是目录内新增匹配。严格匹配优先；方向学者的弱匹配必须通过任职机构或唯一全名校验；非方向学者若公开任职记录全部在海外，不自动合并。共拒绝 625 个仅含海外任职、484 个姓名不一致与 19 个弱匹配记录（例如 Shandong University 的 Ling Sun 与 ANU 天体物理学者同名，未合并）。
- **详情范围**：5,355 位有公开作品，923 位的详情可给出 ORCID 公开主页。方向学者中 665 位按当前任职核验机构，481 位修正机构；非方向新增匹配只补充活跃度、3 篇近期作品、任职范围与公开主页，不改动目录机构，也不进入论文库。匹配但未公开任职的 4,812 位标为「仅姓名与作品匹配」，公开记录含中国任职的 2,575 位标注「公开记录包含中国院校任职」。
- **论文库**：8,412 篇（883 个 ORCID、25 个领域，按 DOI / 标题去重）。补齐 2,126 篇原缺分类的论文：方向库独有学者的大类由所属方向补入，现在全部论文都有领域分类。论文库仍只收录方向推荐学者；非方向学者的详情明确写出「暂未纳入论文库」。论文库学者数改为按 ORCID 去重，界面与数据口径一致（883）。
- **截图修复**：`desktop-advisor-expanded` 先切到「全部学者」再搜索 Yuanqing Xia，避免沿用上次方向查询状态；新增截图展示「ORCID 已匹配」、6 年活跃度、3 篇近期论文与未纳入论文库说明。截图总数为 37 张。
- **验收**：本地与公网回归均输出 `ALL_CHECKS_PASSED`、`NO_CONSOLE_ERRORS`。覆盖 9,746 目标、8,602 匹配、Yuanqing Xia 新增详情、Ling Sun 海外同名拒绝、Zisserman Oxford 修正、论文库 8,412 篇 / 883 位 / 25 个领域、院校 2,394 所与全部响应式路由。
- **发布**：`dist/` 由 `site/` 全量重建（440 个文件 / 29 MB），敏感信息与本地路径复扫无命中；发布动作 `0879f5d4-876a-4111-902b-69befec5cd4a`，publish operation `01a1ecab-feb2-79d0-9387-0749714ec4ba`，deployment `01a1ecaa-60dc-73a1-b902-32335a9174e7`，release `01a1ecab-feb2-797d-88cf-b1ee77356043`；验证 `published: true`、`readiness: publication_completed`、`access_mode: public`。
- 公网 `app.js`（`d4b52da5…`）、`core.js`（`caf2fa29…`）、`styles.css`（`765b775d…`）、`refine.css`（`24b86371…`）、`orcid.json`（`1fc6124c…`，7,004,437 字节）、`papers.json`（`1abc4ba0…`，3,337,473 字节）、`advisors.json`（`65c8598c…`）、`institution_regions.json`（`136d85fa…`）、`materials.json`（`3180bcdb…`）、`data/index.json`（`903dde39…`）的 SHA-256 与 `dist/` 完全一致；`index.html` 由平台注入水印脚本，其余字节一致。

### 6.14 启动界面、数据集扩库、计数口径与方向联想（第十四轮）

用户反馈四组问题：工坊大类胶囊点击后没有替换/刷新方向；素材库出现「应用领域 109 却只有 2 个数据集」的计数疑问，要求说明数字含义并大幅扩充论文用过的公开数据集与链接；导师与期刊的方向输入只有输入框，没有关键词提示；还需要一个更科学、实用、商业化的启动界面。

- **大类点击反馈**：`discover-cat` 现在切到目录页并写入当前大类，新增「大类」胶囊显示所选大类，筛选框占位符改为「在「计算机视觉」内筛选关键词或术语」，右侧同步列出该大类 25 个方向并按关联强度排序；截图 `desktop-cat-chip.png` 验证。
- **计数口径**：素材库所有胶囊数字统一为「当前筛选池中归属于该项的数据集数量」；剔除伪大类「应用领域」，改为 23 个有数据集的研究大类与 37 个应用场景；筛选后显示「已显示 36 / 106 个数据集」；顶部把 282 标注为「数据集含论文出处」，关系条把 423 标注为「个方向已挂基准卡」。
- **数据集扩库**：新增 `dataset_expansion.mjs`（人工整理的公开基准与官方主页/来源论文）、`expand_datasets.mjs`（按 `index.json` / `applications.json` 校验大类、场景与方向名后幂等合并）、`paper_sources.mjs`（人工核对的论文标题与链接）、`resolve_papers.mjs`（arXiv 批量解析）、`resolve_papers_crossref.mjs`（Crossref DOI 解析）。数据集从 176 增至 365，全部附官方主页，282 个附来源或代表论文；其余 83 个多为长期维护的数据仓库、竞赛数据或行业轨迹，详情页明确写「以官方数据集页为准」，不虚构引用。校验结果：0 重复、0 缺主页、0 未知大类/场景/方向。
- **方向联想**：`suggestDirections` 扩展到首页、工坊、导师、期刊四个方向输入框；输入 2 个字即显示方向、类别与别名，支持 ↑/↓、Enter、Escape，点击即写入并执行对应动作；首页联想框此前被 `.start-hero { overflow: hidden }` 裁切，已改为 `overflow: visible` 并给装饰层补 `border-radius: inherit`。
- **启动界面**：新增 `#/start` 工作台首页与 `start.css`：方向输入 + 快速示例、423 方向 / 365 数据集 / 12,450 位可浏览学者 / 126 venue 快照、抽象图谱、四个入口卡片与续做卡片；输入后经 `pendingLaunch` 进入工坊并自动识别。`pendingLaunch` 由 `requestAnimationFrame` 改为 `setTimeout`，避免后台/隐藏标签页不执行回调导致不识别。
- **计数校核**：新增 `scripts/sync_web_stats.mjs`，把 `index.json` 统计与导出数据对齐：`scholars_indexed=18,281` 保留为原始记录数，新增 `scholars_exported=12,450`、`schools_exported=2,394`（按 ORCID 任职合并后的院校数）、`orcid_papers=8,412`、`datasets=365`、`categories=24`、`applications=37`；首页与各页不再使用 18,281 / 2,216 / 176 等旧口径。
- **修复**：论文页覆盖范围误用未定义的 `stats` 变量导致页面中断，改为 `state.index.stats.directions`；截图脚本在启动页加入后仍从根路径进入工坊，已改为显式 `#/workshop` 并强制刷新，避免目录页状态残留。
- **验收**：`check_site.mjs` 本地与公网均为 `ALL_CHECKS_PASSED`、`NO_CONSOLE_ERRORS`；截图脚本输出 `NO_BROWSER_ERRORS`，截图增至 40 张（新增首页联想、大类胶囊、素材筛选）。
- **发布**：`dist/` 由 `site/` 全量重建（441 个文件 / 29 MB），敏感信息复扫无命中。首次上传返回 `sites_upload_unavailable`，保留同一 action 等待后重试；发布动作 `5bd2d7fc-db99-468b-9aca-1b0d957426d1`，验证 operation `01a1ece4-f89f-7ea7-886f-e1be190ff7a4`，publish operation `01a1ece5-b805-79e9-95df-19b4c67a13b8`，deployment `01a1ece0-972e-746b-b698-50c079af8feb`，release `01a1ece5-b805-797e-8ea3-8caab7581147`；验证 `published: true`、`readiness: publication_completed`、`access_mode: public`。
- 公网 `app.js`（`fa01a035…`）、`core.js`（`caf2fa29…`）、`styles.css`（`765b775d…`）、`refine.css`（`24b86371…`）、`start.css`（`d15b4aed…`）、`data/index.json`（`45f15e0d…`）、`data/benchmarks.json`（`174ac51e…`）、`data/materials.json`（`36f1e40c…`）的 SHA-256 与 `dist/` 一致。

### 6.15 全屏开场页与进入系统动效（第十五轮）

用户指出上一轮的 `#/start` 并不是他说的首页：他希望打开网站时先看到一个类似动画的开场页，点击「进入系统」后才进入现在的工作台。本轮把开场页做成独立的入口层，工作台保持不变。

- **入口路由**：根路径与 `#/intro` 都进入开场页，`#/start` 等工作台深链直接进入应用；`currentRoute()` 在无 hash 时返回 `intro`，浏览器后退回根路径会重新播放开场，进入系统后写入 `#/start`。
- **首屏无闪烁**：`index.html` 头部内联脚本在首次绘制前读取 hash，命中开场时设置 `html[data-intro="1"]`；`intro.css` 依据该属性隐藏 `.app`、`.mobile-nav` 与 toast，静态开场 HTML 不依赖数据加载即可显示，数据在后台并行载入。
- **画面与动效**：暖色纸面背景 + 网格 + 光晕 + 大字水印「谱」；标题三行逐行上滑（`introLineUp`，0.12s / 0.24s / 0.36s 延迟）；右侧深色 Atlas 卡片内含 Canvas 网络图（42–76 个节点、5 个聚类、最近邻连线 + 金色枢纽、节点呼吸、沿边流动的脉冲、环轨与扫描光），下方实时统计 423 方向 / 365 数据集 / 12,450 可浏览学者 / 126 期刊会议与构建进度条（第十六轮已改为工作台界面预览）。
- **进入与跳过**：`#introEnter` 触发 430ms 的 `is-leaving` 淡出后跳转 `#/start`，防止重复点击；`#introSkip` 与开场页 Enter 键等效；`prefers-reduced-motion` 下停顿动画、改为静态绘制网络。
- **响应式**：≤960px 单列可滚动；≤620px 隐藏顶部 meta、CTA 通栏、统计 2×2、卡片降至 262px。
- **修复**：`.intro-kicker` 与既有 `styles.css:739` 同名规则冲突导致眉标两端撑开，统一改名 `.intro-eyebrow` 并改为 `align-items:center`；标题原本两行在窄屏折成「第一 / 周。」，拆为三行并补第三段延迟；手机端右上 meta 被裁切，≤620px 直接隐藏。
- **验收**：`check_site.mjs` 新增开场页桌面断言（全屏遮罩、应用隐藏、Canvas、3 行标题、4 个节点标注、「进入系统」按钮、无横向溢出）与手机端断言（可见、无溢出、按钮宽 348px），并验证点击后 hash 为 `#/start`、应用可见、开场隐藏、工作台标题包含「可核查」；素材库等原有 `h1` 选择器改为 `#view h1`，避免命中隐藏的开场标题。本地与公网回归均为 `ALL_CHECKS_PASSED`、`NO_CONSOLE_ERRORS`。
- **截图**：`capture_screenshots.mjs` 新增 `desktop-intro`、`mobile-intro`、`desktop-home`（进入系统后的首页），总数 42 张，输出 `NO_BROWSER_ERRORS`。
- **发布**：`dist/` 由 `site/` 同步重建（442 个文件 / 30 MB），敏感信息与本地路径复扫无命中；设计工作台页面清单更新为开场页 + 9 个页面。发布动作 `abeb0a54-8dc4-44a2-9f41-47a95c274ea5`，publish operation `01a1ecfe-f4da-71ea-8c8f-8b7bfac4a738`，deployment `01a1ecfe-4c14-7c6b-b68b-a072a5a454ae`，release `01a1ecfe-f4da-71a0-9aa8-91c6fddacf07`；验证 `published: true`、`readiness: publication_completed`、`access_mode: public`。
- 公网 `app.js`（`df37f9df…`）、`core.js`（`caf2fa29…`）、`intro.css`（`50f9551c…`）、`styles.css`（`765b775d…`）、`start.css`（`d15b4aed…`）、`data/index.json`（`45f15e0d…`）、`data/materials.json`（`36f1e40c…`）、`data/orcid.json`、`data/papers.json` 的 SHA-256 与 `dist/` 一致；`index.html` 仅多出平台注入的水印脚本，其余字节一致。

### 6.16 开场页界面预览化与侧栏收敛（第十六轮）

用户反馈：侧栏「工作台首页」去掉；开场页要像一个可直接落地、商用化的产品界面，而不是简单的图谱；左侧换成「知识是人类缔造巴别塔的阶梯，思想是构建未来的桥梁」，助手作用只做一句说明；移除「跳过开场」。

- **侧栏**：删除「开始」分组与「工作台首页」导航项，侧栏从「选题与研究」开始；品牌标识仍链接 `#/start`，路由与页面不变。
- **文案**：三行衬线标题承载新引语，「巴别塔」用金色批注；说明压缩为「题谱是一个选题助手：输入研究方向，得到可验证的问题、公开数据集、导师与投稿去处。」；CTA 旁改为「无需登录 · 本地离线运行」，不再提供跳过入口。
- **界面预览**：移除 Canvas 绘图与 200 余行动画代码，改为产品界面 mock：窗口栏、深色方向输入（CSS 打字光标 + 识别按钮）、方向标签、三条候选问题（匹配度与进度条）、数据集 / 导师 / 期刊能力卡、底部索引说明；CSS 依次完成打字、标签、候选与进度条入场，`prefers-reduced-motion` 呈现最终状态；页脚 ORCID / 院校数字从 `index.json` 注入。
- **诚实标注**：mock 下方写明「界面预览 · 实际结果由本地离线索引生成，示例内容仅作展示」。
- **修复**：新增的 `.intro-note` 与 `styles.css` 中同名营销区块冲突，显示成白色大卡片，改名为 `.intro-hint`；手机端在真实 390px 仿真下标题与预览宽 358px、无溢出。
- **验收**：`check_site.mjs` 改为校验界面预览、3 条候选、3 张卡片、引语包含「巴别塔 / 桥梁」、无跳过入口、侧栏无首页入口、桌面与手机无横向溢出；本地与公网均 `ALL_CHECKS_PASSED`、`NO_CONSOLE_ERRORS`，截图 42 张、`NO_BROWSER_ERRORS`。
- **发布**：`dist/` 442 个文件 / 29 MB，敏感信息与本地路径复扫无命中；发布动作 `d7580aa3-de70-4073-a84e-62a45c1f03f6`，publish operation `01a1ed17-8ec2-7cc9-a45f-6c2e603084ea`，deployment `01a1ed16-b076-7912-8ac1-cb19d445ff4d`，release `01a1ed17-8ec2-7c70-a72a-7a24d4ac0d30`；验证 `published: true`、`readiness: publication_completed`、`access_mode: public`。
- 公网 `app.js`（`36f86ccf…`）、`intro.css`（`64ebe48a…`）、`styles.css`（`765b775d…`）、`data/index.json`（`45f15e0d…`）、`data/orcid.json` 的 SHA-256 与 `dist/` 一致；`index.html` 仅多出平台水印脚本。

### 6.17 期刊整卡可点与详情说明（第十七轮）

用户反馈：期刊会议页想点这个 venue 去看，却只能点行尾的「主页」；应当整张卡片可点，点进去后像导师详情一样给出说明。

- **整卡可点**：venue 卡片改为 `role="button"` + `tabindex="0"`，点击卡片任意位置（列表视图整行）打开详情；行尾「官网」使用独立 `data-action`，点击只外跳官网，不再同时打开详情；Enter / Space 打开，Esc / 背景 / 关闭按钮关闭。
- **详情弹层**：复用导师详情的 `advisor-modal` 结构，新增 `venueModalHtml()`：CCF 等级徽标与四项数据条、定位说明、CCF 2022 A/B/C 含义、题谱推荐逻辑、数据来源与边界；「按方向推荐」中打开时补充当前方向推荐了该 venue 及该方向 venue 总数。
- **联动**：详情内「在论文库搜索」预填 venue 名称、清空年份 / 类型 / 领域 / 学者筛选并跳 `#/papers`；官网入口显示域名；未收录官网时明确说明不提供外跳。
- **样式**：卡片增加 `cursor: pointer` 与 `:focus-visible` 焦点环，页脚改为「查看详情 → / 官网 ↗」；弹层宽 620px，四项数据条在手机端改为 2×2。
- **验收**：`check_site.mjs` 新增三条断言并在本地源、`dist/`、公网三处运行，均为 `ALL_CHECKS_PASSED`、`NO_CONSOLE_ERRORS`；`capture_screenshots.mjs` 新增 `desktop-venue-modal`，共 43 张、`NO_BROWSER_ERRORS`。
- **发布**：`dist/` 442 个文件 / 30 MB；发布动作 `521a7c90-1131-4d3d-b779-b06fca9aff43`，publish operation `01a1ed61-60d2-7970-9586-4e6a66aa3b23`，deployment `01a1ed60-8666-7d16-9ced-50225bdfff19`，release `01a1ed61-60d2-78f9-a020-0f33ae7045a0`；验证 `published: true`、`readiness: publication_completed`、`access_mode: public`。
- 公网 `app.js`（`88a79bf9…`）、`styles.css`（`11f39ea6…`）、`intro.css`（`64ebe48a…`）、`data/index.json`（`45f15e0d…`）、`data/venues.json`（`cd5bbe50…`）与 `dist/` 哈希一致；`index.html` 仅多出平台水印脚本。

### 6.18 期刊 / 导师 / 方向 / 素材库全面扩库（第十八轮）

用户指出四块数据仍然太少，要求继续增加、更全面。

- **期刊会议**：以 CCF 2026 年第七版推荐目录（2026-03-31 发布）重建 `venues.json`，从 126 个扩到 **701 个**：677 个目录内条目（A 95 / B 243 / C 339）+ 24 个目录外 venue；会议 400 个、期刊 301 个；529 个条目使用 DBLP 目录页链接，并新增 `linkLabel` 字段区分「官网 / DBLP 目录页」，前端卡片与详情弹层按字段显示，不再把 DBLP 页写成官网。
- **导师**：新增 `build_combined_advisor_source.mjs`，把 15,952 条目录记录与 5,846 条旧缓存中缺失的学者合并为 21,798 条；导出时按 ORCID（无 ORCID 时姓名 + 机构）去重为 **18,296 位**，其中 941 位有 CSRankings / ORCID 个人主页、13,247 位有院校官网；院校按规范化机构名聚合为 **2,547 所**。无法确认真实地埋的 1,543 位明确标为「地区待核验」，不再强行归入「其他国家/地区」。
- **研究方向**：`expand_applications.mjs` 新增 78 个领域方向（计算病理、蛋白质设计、端到端自动驾驶、工业质检、气候极端事件、漏洞挖掘、后量子迁移、人形机器人、核聚变控制等），并为部分方向指定学科大类；方向库从 423 扩到 **501 个**，仍为 24 个有效学科大类（另设「应用领域」聚合）与 37 个应用标签。
- **素材库**：`dataset_expansion.mjs` 新增 146 个公开数据集（MIMIC-IV、UK Biobank、MTEB、DROID、CMIP6、PDEBench、ZINC、SpaceNet 等），`dataset_expansion` 合计 326 条；合并后数据集从 365 扩到 **502 个**，全部附官方主页，354 个附来源或代表论文，148 个按「以官方数据集页为准」如实标注，不虚构引用。
- **统计与文案**：`build_materials.mjs` 改为直接读取 `venues.json`，`sync_web_stats.mjs` 输出 venues=701、directions=501、datasets=502、scholars_exported=18,296、schools_exported=2,547；开场页、首页、关于页与期刊页的硬编码数字同步更新，CCF 文案统一为 2026 年第七版。
- **验收**：`check_site.mjs` 的期刊目录断言从 126 更新为 701，并新增「待核验分组可筛选并逐卡标注」断言；本地源、`dist/` 与公网三处回归均输出 `ALL_CHECKS_PASSED`、`NO_CONSOLE_ERRORS`；截图脚本重新生成 43 张并输出 `NO_BROWSER_ERRORS`。
- **发布**：`dist/` 520 个文件 / 34 MB；发布动作 `9e62e3f2-1b32-47f7-93dc-019c5dcbec82`，验证 operation `01a1ed9e-1ca4-741a-8cb3-712de0c17693`，publish operation `01a1ed9e-bcd7-7ad2-bf78-ef3138f558a7`；验证 `published: true`、`readiness: publication_completed`、`access_mode: public`。
- 公网 `assets/app.js`（`f8226889…`）、`data/index.json`（`77b0b571…`）、`data/venues.json`（`9fc7a043…`）、`data/benchmarks.json`（`52ba3ff2…`）、`data/materials.json`（`aa2ffa14…`）的 SHA-256 与 `dist/` 一致；`index.html` 仅多出平台注入的水印脚本。

### 6.19 移除独立工作台首页并直接进入选题工坊（第十九轮）

用户指出进入系统后出现的独立「工作台首页」不需要保留；开场页仍要保留，但「进入系统」后应直接落到可操作的工坊。

- **路由收敛**：从 `ROUTES` / `ROUTE_META` 删除 `start`，`currentRoute()` 对未知或旧版 `#/start` 统一回落到 `workshop`；`enterSystem()` 与开场页「进入系统」、侧栏品牌链接都改为 `#/workshop`，开场页仍是独立全屏层。
- **页面与样式**：删除 `startView()`、`startLaunch()` 及 `start-*` 点击 / 输入 / 键盘分支，删除 `assets/start.css` 与 `index.html` 中的引用；工坊保留原有方向输入、实时联想、三种入口、501 / 502 / 18,296 / 701 数据快照和识别→确认→候选→体检流程。
- **验收**：`check_site.mjs` 把进入系统断言改为 `#/workshop` 与工坊标题，并新增「旧版 #/start 地址自动回到选题工坊」；截图脚本的 `desktop-home` 改为工坊首屏，原 `desktop-start-suggest` 改为 `desktop-workshop-suggest`，重新生成 43 张并输出 `NO_BROWSER_ERRORS`。本地源、`dist/` 与公网回归均为 `ALL_CHECKS_PASSED`、`NO_CONSOLE_ERRORS`。
- **发布**：`dist/` 519 个文件 / 34 MB；发布动作 `eb49abe9-5353-4f30-aa0e-507ffa1d89c4`，验证 operation `01a1edac-7dcb-7de6-ad10-bc2b1ff337a4`，publish operation `01a1edad-1fe4-7e26-85a1-f449deb7df96`；验证 `published: true`、`readiness: publication_completed`、`access_mode: public`。
- 公网 `assets/app.js`（`4566bcb6…`）、`index.html`（`254be108…`）、`styles.css`（`11f39ea6…`）、`refine.css`（`24b86371…`）、`intro.css`（`64ebe48a…`）与 `dist/` 一致；`assets/start.css` 已返回 404，公网 `index.html` 仅多出平台注入的水印脚本。

### 6.20 去除页面标题区与候选连续加入（第二十轮）

用户要求两点：每个页面顶部的编号页头、标题、说明与页级按钮全部去掉；工坊里搜到的候选要能保存，“加入后返回还能回到同一份结果继续加”，并让左侧计数真正有意义，同时优化左侧栏排版。

- **页头移除**：`pageHead()` 改为只输出 `h1.sr-only`，八个路由的编号 kicker、页面大标题、描述与页级操作按钮统一不再渲染；隐藏标题保留，路由器语义与回归选择器不受影响；面包屑与页面内卡片标题保持不变。
- **侧栏计数修正**：删除「选题工坊」右侧那个静态快捷键徽标（此前容易被误读成收藏数）；「研究计划」的 `#savedCount` 成为唯一的计划计数，加入选题后实时更新。
- **候选连续加入**：每条候选右下角新增独立「+ 加入」按钮，加入后变成「已加入」且不再跳转；候选标题旁出现「已加入 N 个 · 查看计划」；右侧选题卡的「加入计划」同样原地保存并显示「查看计划」入口；重复加入只提示不重复写入。
- **返回不丢检索**：研究计划页顶部增加工具栏「已加入 N 个选题」与「返回候选继续添加」，返回后方向、筛选与同一份 12 条候选原样保留，可继续加入下一条。
- **侧栏排版**：导航项间距、分组标题上下留白、行高与计划计数徽标尺寸重新调整；移动端候选卡为「加入」按钮预留底部空间，修复按钮压住「可行」指标的问题，计划工具栏按钮在窄屏占满一行。
- **验收**：`check_site.mjs` 的路由断言改为「无页头且渲染正常」，并新增「计划计数紧跟导航且提供返回候选入口」「计划页返回后保留同一次检索（12 条）」「候选列表可直接加入第二条且不离开检索页（2 条）」；本地源、`dist/` 与公网三处均为 `ALL_CHECKS_PASSED`、`NO_CONSOLE_ERRORS`；重新生成 43 张截图，`NO_BROWSER_ERRORS`。
- **发布**：`dist/` 519 个文件 / 34 MB；发布动作 `216c023e-51b2-4c13-8a15-5747ce3487b7`，验证 operation `01a1edc1-5f8a-79e8-aa46-c6fff9dd95a8`，publish operation `01a1edc1-d65e-7044-a18c-7129149f373e`；验证 `published: true`、`readiness: publication_completed`、`access_mode: public`。
- 公网 `assets/app.js`（`0cd50731…`）、`styles.css`（`aa39c3c2…`）、`refine.css`（`24b86371…`）、`intro.css`（`64ebe48a…`）与 `dist/` 哈希一致；公网 `index.html` 仅多出平台注入的水印脚本。

### 6.21 已加入候选可再次点击取消（第二十一轮）

用户反馈：候选卡上的「已加入」再次点击没有任何反应，应当可以取消。

- **切换逻辑**：新增 `toggleCandidate()` 与 `unsaveIdea()`，候选卡的「加入 / 已加入」和详情卡的保存按钮都改为切换；取消时从计划移除、重写 `localStorage`、若取消的是当前计划项则自动切到下一条、候选列表 / 计数 / 「已加入 N 个」提示同步刷新。
- **可发现性**：「已加入」按钮悬停或键盘聚焦时变为红色「取消」，并带「再次点击取消加入」的 title / aria-label；详情卡在已保存时按钮直接显示「取消加入」，旁边保留「查看计划」。
- **计划页**：保留原有带确认的「删除」，与候选页的快速取消互不影响。
- **验收**：`check_site.mjs` 新增「再次点击已加入按钮可取消加入（剩 1 条）」与「取消全部加入后计划计数与提示同步消失」；本地源、`dist/` 与公网三处均为 `ALL_CHECKS_PASSED`、`NO_CONSOLE_ERRORS`；重新生成 43 张截图，`NO_BROWSER_ERRORS`。
- **发布**：`dist/` 519 个文件 / 34 MB；发布动作 `e7dc2bdb-3698-4889-9bef-ea8cbac89be0`，验证 operation `01a1edcc-23b2-7ea6-87a6-7394d0f48ddf`，publish operation `01a1edcc-a1e1-733e-a0de-adc1c9347ba9`；验证 `published: true`、`readiness: publication_completed`、`access_mode: public`。
- 公网 `assets/app.js`（`9f64f97b…`）、`styles.css`（`d41a34c9…`）与 `dist/` 哈希一致；公网 `index.html` 仅多出平台注入的水印脚本。

### 6.22 手机端开场页只保留标题（第二十二轮）

用户要求手机端开场界面只保留「知识是人类缔造巴别塔的阶梯，思想是构建未来的桥梁」这一段话，其余内容先全部去掉看效果。

- **隐藏范围**：≤620px 时隐藏顶部品牌与元信息、眉标、说明句、进入按钮与提示、数据快照、界面预览与图注、页脚，以及「谱」水印；背景渐变、网格与光晕保留，标题仍逐行浮起并保留「巴别塔」下划线。
- **版式**：开场页改为垂直居中，标题居中排三行、按屏宽缩放；移除移动端原有的按钮与统计网格样式。
- **进入方式**：手机端隐藏按钮后，轻触屏幕任意非链接区域即可进入选题工坊；桌面端仍用「进入系统」与回车。`enterSystem()` 原有的防重复进入保护继续生效。
- **验收**：`check_site.mjs` 的手机端开场断言改为「只保留标题段」并检查六类区块均为 `display: none`，新增「手机端轻触标题段进入选题工坊」；本地源、`dist/` 与公网三处均为 `ALL_CHECKS_PASSED`、`NO_CONSOLE_ERRORS`；重新生成 43 张截图，`NO_BROWSER_ERRORS`。
- **发布**：`dist/` 519 个文件 / 34 MB；发布动作 `248efd4b-6334-46d4-9e96-96ed16195eb6`，验证 operation `01a1ee00-f5e3-7224-aad9-40598a040907`，publish operation `01a1ee01-6f48-72d6-97d4-46eba6b00ba7`；验证 `published: true`、`readiness: publication_completed`、`access_mode: public`。
- 公网 `assets/app.js`（`f8e5a2fe…`）、`intro.css`（`09427c95…`）与 `dist/` 哈希一致；公网 `index.html` 仅多出平台注入的水印脚本。

### 6.23 手机端开场标题不拆字并恢复进入入口（第二十三轮）

真机截图显示：窄屏下第三行「思想是构建未来的桥梁」被拆成「…桥 / 梁」，单字掉到下一行；同时上一轮隐藏按钮后页面上没有任何可见的进入入口。

- **防拆字**：手机端标题改为 `white-space: nowrap` 的三行独立行，字号收紧为 `clamp(26px, 8vw, 36px)`，并设置 `text-size-adjust: 100%`，避免浏览器字体放大导致再次溢出；390px 下三行均单行显示，320px 仍有余量。
- **进入入口**：手机端恢复「进入系统」按钮（隐藏 ENTER 键帽），按钮下增加「轻触屏幕任意位置也可进入」提示；桌面端仍用原按钮与回车，移动端继续支持全屏轻触进入。
- **验收**：`check_site.mjs` 新增逐行 `getClientRects().length === 1` 与标题 `scrollWidth` 适配断言、按钮与轻触提示可见断言，以及「点击进入系统」「轻触标题段」两条进入路径；本地源、`dist/` 与公网三处均为 `ALL_CHECKS_PASSED`、`NO_CONSOLE_ERRORS`；重新生成 43 张截图，`NO_BROWSER_ERRORS`。
- **发布**：`dist/` 519 个文件 / 34 MB；发布动作 `9804e3c5-70b4-469d-bde2-b5febd983cec`，验证 operation `01a1ee0b-550f-7304-963d-8cb6d8e2bc2b`，publish operation `01a1ee0b-ca68-7770-9207-30b5e4c96c14`；验证 `published: true`、`readiness: publication_completed`、`access_mode: public`。
- 公网 `assets/intro.css`（`0671ad01…`）与 `dist/` 哈希一致；公网 `index.html` 仅多出平台注入的水印脚本。

### 6.24 交互、提示词与数据面的集中优化（第二十四轮）

按用户五点反馈逐项处理：方向联想键盘操作、顶栏瘦身、科研提示词生成、知识库扩量、研究计划改版，以及首页右侧换用塞莎特（Seshat）主题插画。

- **方向联想键盘操作**：输入框保持焦点，`ArrowDown` / `ArrowUp` 循环高亮候选项（`.is-active`），`Enter` 直接选中当前高亮项，`Escape` 关闭联想并把焦点交还输入框；高亮项用 `scrollIntoView({ block: "nearest" })` 跟随滚动，列表头提示改为「↑↓ 选择 · Enter 确认」。导师与期刊方向两个联想框共用同一套逻辑。
- **顶栏瘦身**：移除 OFFLINE 状态胶囊、静态日期和右上「关于」链接，只保留实时时钟（`HH:MM:SS`）、日期（`YYYY.MM.DD 周X`）与主题切换，并整体放大；时钟每秒刷新，主题按钮在明暗之间即时切换并写入 `localStorage`。
- **科研提示词工作台**：方法页新增提示词生成区，按「所选方向 + 8 项科研准备勾选 + 5 个研究阶段 + 约束备注」组合离线提示词，包含工作规则、科研准备状态（已完成 / 待补）、方法步骤、阶段任务、8 个创新维度、质量门槛、输出格式与反编造要求；准备度按 `/8` 实时显示，未勾选项在提示词中明确标为「待补」；约束备注（如算力、数据审批）逐字进入提示词。
- **知识库扩量**：新增 30 个方向（d502–d531，覆盖 VLA、GUI 智能体、推理与测试时计算、长上下文、机制可解释性、扩散语言模型、时序 / 图 / 表格基础模型、AI 气象、单细胞与空间组学、语音全双工、世界模型、3DGS、内容取证与水印、端侧推理、形式数学、医学多模态、法律大模型、科学文献智能体等），并为每个新方向配置 4–6 个真实公开基准与指标；数据集目录新增 50 个已核验基准（MMLU-Pro、GPQA、SWE-bench Verified、tau-bench、RULER、ARC-AGI、Monash、OGB、TGB、SimplerEnv、ProteinGym、CELLxGENE、LegalBench、QASPER 等）。总量增至 **531 个方向 / 552 个数据集 / 701 个期刊会议 / 18,296 位学者**；无来源链接的条目保留空链接并在备注中写明「待核验 / 以官方仓库为准」，不编造 URL。
- **研究计划改版**：新增概览区（已存选题、待办完成度、距截止天数、整体进度）、进度轨道与「下一步」建议；倒推阶段按截止日期均分，四个里程碑区分已完成 / 当前 / 待开始，日期统一显示为 `YYYY.MM.DD – YYYY.MM.DD`（修复此前把 `Date` 对象传给字符串格式化函数导致的英文长日期）；待办勾选状态与 9 项结构体检继续保存在本机。
- **首页右侧插画**：工作台预览替换为塞莎特主题原创插画（`assets/seshat-atlas.webp`），配「塞莎特 · SESHAT」标签与画面说明，保留三行主标题与「进入系统」入口；插画经 WebP 压缩后随静态站点发布。
- **验收**：`check_site.mjs` 新增顶栏时钟 / 日期 / 主题切换、联想框方向键循环与 Enter 选中、Escape 关闭、提示词准备度与待补标记、研究计划概览 / 里程碑 / 日期、首页塞莎特插画等断言；本地源、`dist/` 与公网三处均为 `ALL_CHECKS_PASSED`、`NO_CONSOLE_ERRORS`；重新生成 43 张截图，`NO_BROWSER_ERRORS`，1440 / 1024 / 390 三档无横向溢出。
- **发布**：`dist/` 550 个文件 / 32 MB；发布动作 `a6ae546c-884d-401c-8502-60d196952667`，验证 operation `01a1eee5-33d9-76a6-9dfc-2c6fc955560b`，publish operation `01a1eee5-c2a7-7200-a7e0-7253551297c0`；验证 `published: true`、`readiness: publication_completed`、`access_mode: public`。
- 公网 `assets/app.js`（`55f1ffac…`）、`assets/intro.css`（`6074c148…`）、`assets/seshat-atlas.webp`、`data/index.json`、`data/benchmarks.json`、`data/materials.json` 均与 `dist/` 哈希一致；公网 `index.html` 仅多出平台注入的水印脚本。

### 6.25 开场页去装饰、logo 水印与三端品牌统一（第二十五轮）

- **开场页减法**：删除底部 `LOCAL INDEX READY` 状态行与整块 `intro-foot`；删除插画下方的说明文字、`SESHAT` 标签、编号角标与画框描边。右侧只保留一张无边框线稿，说明文字不再重复标题已表达的内容。
- **插画融入纸面**：改用透明底 WebP（1005×1274，190 KB），浅色主题 `mix-blend-mode: multiply`、深色主题 `screen` 配合暖色反相滤镜；去掉矩形外框后不再像「贴上去的插画」。背后加一圈细线浑仪式表盘，与页面网格同色，只做构图锚点。
- **背景换成品牌标记**：把原来的巨大「谱」字替换为内联六边形节点 SVG（56vw，8% 赭墨色，旋转 -9°）。标记与 favicon、应用图标同源，不再是与项目无关的字符水印。
- **验收**：`check_site.mjs` 的开场断言改为「无 footer / 无说明 / 无贴纸 / 有 logo SVG 水印 / 有表盘 / 线稿已加载」，手机端断言同步改为 `footerAbsent`；本地源、`dist/` 与公网三处均为 `ALL_CHECKS_PASSED`、`NO_CONSOLE_ERRORS`；重新生成 43 张截图，`NO_BROWSER_ERRORS`。
- **发布**：`dist/` 550 个文件 / 32 MB；发布动作 `ae034e75-5efa-4275-96c2-f0c0115a5376`，验证 operation `01a1ef11-f298-7730-be6e-0bde206fdf27`，publish operation `01a1ef13-7a9f-7c27-89c9-c6078d8f88d5`；验证 `published: true`、`readiness: publication_completed`、`access_mode: public`。公网 `assets/intro.css`（`b8242346…`）与 `assets/seshat-atlas.webp`（`f2bfb1c6…`）与 `dist/` 哈希一致；`index.html` 仅多出平台注入的水印脚本。
- **本地应用品牌统一**：重写 `make_logo.py`，三端共用「棕底圆角方块 + 奶白六边形节点 + 金色中心」标记；32px 以上保留描边与三节点，28px 以下改为实心六边形 + 深色中心点，保证 16px 任务栏图标仍可辨认。重新生成 `logo_*.png`、`win*.png`、`kb_widget_v2.ico` 与 PWA 图标；`make_icon_v2.py`、`tools_build_icons.py` 改为调用同一生成器，避免以后又分叉成「KB / 550W / 六边形」三套图标。
- **本地网页体验端**：顶栏的「550W」文字方块换成真实图标，品牌改为「题谱 / RESEARCH QUESTION ATLAS · 本地体验端」，页面标题、PWA 名称、主题色与 Service Worker 缓存版本（`kb-v2`）同步更新；`tools_test_web.py` 新增图标断言，28 项全部通过；`tools_check_mobile.py` 在 390px 下无横向溢出、输入框 16px、触控高度 52px。

### 6.26 开场页计算机 / AI 主题与三端科技线层（第二十六轮）

- **插画主题替换**：保留塞莎特人物与细线刻版语言，把周围对象换成差分机（上左）、神经网络星座与芯片节点（上右）、损失曲面等高线与矩阵（下左）、决策树（中右）、GPU 芯片罗盘（下右）。透明底 WebP 1043×1271 / 144 KB，浅色 `multiply`、深色反相滤镜下均无白底。
- **去掉神经网络背后的纸色多边形**：首版生成的神经网络群背后是一整块不透明纸色填充，浅色主题下与纸面同色看不出来，深色反相后变成一大片亮斑。按区域做纸色透明化，只保留细线与节点，深色下恢复为细金线。
- **背景科技线层**：在 aura 与 logo 水印之间加入内联 SVG 科技层——边缘电路走线、神经网络节点、大圆轨道刻度、点阵、芯片封装、损失曲线与数据刻线；中心区仍由椭圆蒙版留白，不与标题和稿件争视线。浅色 26% 赭墨、深色 38%，桌面、平板、手机三档检查无溢出。
- **验收**：`check_site.mjs` 开场断言新增 `intro-tech` 存在且可见；源目录、`dist/` 与公网均为 `ALL_CHECKS_PASSED`、`NO_CONSOLE_ERRORS`；43 张截图重新生成，`NO_BROWSER_ERRORS`。
- **发布**：发布动作 `bd1b3dd6-262b-49ee-996e-7ca2602d7fb9`，验证 operation `01a1ef2a-e712-7bfe-8a98-85ebb6fabb6d`，publish operation `01a1ef2b-c729-74a6-b1f8-6f3028a06976`；`published: true`、`readiness: publication_completed`、`access_mode: public`。公网 `assets/intro.css`（`7c813676…`）与 `assets/seshat-atlas.webp`（`c3958512…`）与 `dist/` 哈希一致；`index.html` 仅多出平台注入的水印脚本。
- **本地网页端**：新增固定科技线层（`bg-tech`，边缘蒙版，11% 品牌色）与页头右侧走线标记（170px，42%）；桌面端截图确认卡片区不受干扰，390px 下无溢出，页头标记在 1180px 以下隐藏。
- **桌面端**：侧栏页脚加一条 42px 高的电路走线——中性灰线 + 唯一品牌色节点 + 六边形终点，沿用「灰阶为主、品牌色只给要点」的既定配色。`tools_smoke_app.py` 11 项全部通过（总览 / 选题 / 创新点 / 图谱 / 导师 / 期刊 / 文献库 / 方法论 / 设置与数据），开始选题生成 18 个候选、导师 60 位、venue 15 个、本地 PDF 345 篇。
- **环境**：本机 Python 3.9 补装 `scikit-learn 1.6.1`（此前缺失，`kb_vector.py` 导入失败导致桌面端无法启动）；预置语义索引由 1.8.0 生成，加载时有版本警告，功能验证通过。

### 6.27 开场插画四角重绘、水印左移与桌面端暖纸体系（第二十七轮）

- **开场插画四角重绘**：保留塞莎特人物、细线刻版语言与中右决策树，把四角对象换成用户指定的四组——上左机器人解剖图（爆炸视图）、下左三层神经网络架构、上右人脑解剖、下右由代码符号组成的放射状概念图。输出 1024×1280 透明 WebP（253,736 字节）；神经网络背后残留的纸色区域按区域键除，浅色 `multiply` 与深色反相下都没有白块或白边。
- **水印左移**：`.intro-watermark` 从右上改到左下（桌面 `left: -12vw; bottom: -20vh`，手机 `left: -18vw`），右上方只留插画与极淡的科技线层；插图 alt 文案同步为四组新对象。
- **桌面端对齐网页视觉**：`design_tokens.py` 第 27 版改为暖纸 / 墨色 / 铜色（浅色 `#f6efe3 / #1f2438 / #5a3f2a`，深色 `#17120e / #f3e9d8 / #e2c28e`），默认浅色；`app_theme.py` 引入 Noto Serif SC，页面大标题与侧栏品牌改用衬线；徽章、主按钮、列表选中态统一使用 `on_primary_fg` 与色调混合，修掉浅色下白字压浅底、勾选块发黑等对比度问题。
- **其余桌面表面**：桌面小部件 `kb_widget.py` 由深青玻璃改为浅纸玻璃（保留无边框与淡入），开机小窗改为墨色底 + 金字的启动卡；备用面板 `dashboard.py` 同步暖纸 CSS；本地网页 `style.css` 的兜底令牌、滚动条与主按钮 hover 改为同一套色，`theme-color` / manifest 改为 `#f6efe3`，Service Worker 版本升到 `kb-v3`，避免已安装的 PWA 继续用旧缓存。
- **修掉一直显示「数据加载中…」**：导师页的 `FoldMetrics` 创建后从未调用 `set_values`，指标行始终停在占位文案；补上本批命中 / 匹配度中位 / 院校 / 本方向真实人数四项，副标题恢复为可读的一行摘要。
- **期刊会议详情窄栏**：详情栏的「类型 · 国家 · 领域」一行和官网链接原本不随容器换行，1200px 左右会被窗口边缘直接切掉；改用 `T.fill_wrap` 按列宽重算。
- **截图工具**：`tools_shot.py` 用 DWM 可见边界裁掉 Win11 的不可见拖拽边框（PrintWindow 会把那圈画成 12px 纯黑，屏幕截图则会带进桌面背景）；判断「是否截到别的窗口」从「侧栏必须纯色」改为主色占比（浅色侧栏实测 83%，阈值 55%），旧规则会把每张正确截图都判成失败。独立运行截图时补上 `SetProcessDpiAwareness(2)`：系统 125% 缩放下未声明 DPI 感知的进程会把 1338 宽的真实窗口报成 1070，位图按 1070 建，右侧整块界面（含窗口按钮）消失，看起来像 UI 被裁，实际界面完好。
- **验收**：`tools_smoke_app.py` 11 项全部通过（18 个候选、1 条创新点、24 个大类、60 位导师、126 个 venue、345 篇 PDF），桌面截图重新生成且逐张检查；`tools_test_web.py` 28/28；390px 移动端无横向溢出、输入字号 16px、6 项底部导航不挤出；`check_site.mjs` 输出 `ALL_CHECKS_PASSED`、`NO_CONSOLE_ERRORS`；43 张竞赛截图随新插画重生成。截图脚本日志里出现过一次 `ERR_NO_BUFFER_SPACE`（本地 `http.server` 在连续快速请求下的连接缓冲报错，非页面脚本错误），全部截图仍正常产出。
- **发布**：发布动作 `22f12a3e-d4c5-495d-a4d0-780257983c7c`，验证 operation `01a1ef44-958b-79e9-853a-18e436a97122`，publish operation `01a1ef45-214f-79a1-97cf-39c98eb58515`；`published: true`、`readiness: publication_completed`、`access_mode: public`。公网 `assets/intro.css`（`e369b9ca…`）与 `assets/seshat-atlas.webp`（`d831c3b7…`）与 `dist/` 哈希一致；`index.html` 仅多出平台注入的 `data-qoder-watermark` 脚本。公网重跑 `check_site.mjs` 输出 `ALL_CHECKS_PASSED`、`NO_CONSOLE_ERRORS`。

### 6.28 古埃及开场重绘、题谱更名与桌面素材库（第二十八轮）

- **开场插画重绘**：用户指出原插画四角风格不统一。按指定重画为古埃及纸草刻版语言——左上是中世纪维萨里式机械人体解剖图（齿轮关节 + 编号引线），左下是低饱和青铜浑仪，右上是人脑解剖，右下是无数编程字符汇聚成的无限符号（∞），中右侧决策树整块移除。输出 1024×1280 透明 WebP（234,376 字节）；浅色用 `multiply`、深色反相 + `screen`，四角与人物在同一刻版风格下不再突兀；`index.html` 的 alt 同步重写。
- **桌面端更名**：主窗口标题、侧栏品牌、运行小部件、备用面板与截图工具查找关键字统一为「题谱」；侧栏底部那块无名电路纹 Canvas 整块删除，只保留版本与「本地运行」。
- **桌面新增素材库**：`page_materials.py` 读取与网页共用的 `materials.json` 快照（552 个数据集、401 个有来源论文链接），提供名称 / 任务搜索、24 个分类与 37 个应用领域筛选、条数实时计数、详情（任务、简介、场景、指标、基线、相关方向、官网与来源论文）；文档说明改为 401 个有链接、72 个只有标题、79 个只有官方页面。首页数据概览扩为 5 项，新增「素材库 552 个」；`build_client.spec` 把 `materials.json` 打进 `site_data/`，打包版也能读。
- **知识库数量补齐**：网页目录里 149 个只存在于站点快照的方向（含 36 个应用领域方向）合并进桌面方向库，桌面从 387 个领域 / 24 类目升到 **536 个领域 / 25 类目**；网页 `stats.directions` 改为目录实际条数（536），分类胶囊计数按目录重算（计算机视觉 30→32、安全与隐私 45→46），`materials.stats.directions` 修正为 534（数据集实际关联 534 个方向，2 个目录方向暂无数据集）。`autocomplete.py` 的写死计数同步。
- **界面细节**：首页过程指标行与方向图谱「推荐投稿」行改为按容器宽度换行；应用领域大类没有 venue 时显示「按方向名到期刊会议页检索」，不再是空的「推荐投稿：」。
- **截图工具两个真问题**：① 打开文献库后进程里多出一个 175×34、同样叫「题谱」的小窗，`FindWindowW` 按 Z 序先返回它，尺寸检查把它当空壳跳过，冒烟从第 7 页起全部「未找到窗口」——改为枚举所有同名顶层窗再按面积取最大；② Windows 前台锁让 `SetForegroundWindow` 静默失败，屏幕截图截到的是前面打开的其他应用（实测把 DeepSeek 窗口存成了 12 张题谱截图）——补 `AttachThreadInput` 抢焦点，且不在前台时不再抓屏幕像素；冒烟截图新增侧栏底色抽查，内容不对直接判失败。
- **测试不再动用户数据**：冒烟结束后把「测试开始前就存在」的画像 / 失败清单排除在泄漏之外并比对大小与 mtime，避免把用户真实 `researcher_profile.json` 当测试产物删掉；`tools_shot_pages_all.py` 增加素材库深 / 浅色两页。
- **验收**：`tools_smoke_app.py` 12 项全部通过（含素材库；18 个候选、1 条创新点、25 个大类、60 位导师、15 个 venue、345 篇 PDF、素材库筛选 90 条）；`check_site.mjs` 输出 `ALL_CHECKS_PASSED`、`NO_CONSOLE_ERRORS`；43 张竞赛截图随新插画与 536 计数重生成，`NO_BROWSER_ERRORS`。
- **发布**：用新 action `8b6f2c41-7d3a-4e58-9a10-2c5f6d84b7e3` 发布到 https://topic-compass-jzkhsw942zj.qoder.website（`published: true`）；公网 `app.js`、`data/index.json`、`data/materials.json`、`assets/seshat-atlas.webp` 与本地 dist 的 SHA-256 完全一致，`index.html` 仅多出平台注入的 Qoder 水印脚本；对公网地址重跑 `check_site.mjs` 仍是 `ALL_CHECKS_PASSED` / `NO_CONSOLE_ERRORS`。
- **演示脚本同步**：`DEMO.md` 的 531 全部改为 536，插画描述改为古埃及刻版（机械人体解剖、青铜星盘、人脑解剖、编程字符无限符号），素材库口径改为 401 个有链接 / 72 个只有标题 / 79 个只有官方页面。

### 6.29 左上角机器人换成黄铜差分机（第二十九轮）

- 按用户要求移除左上角的机械人体解剖机器人，换成另一件科技产物，体量与另外三个角一致。左上角整块改为黄铜差分机（机械计算机）：立柱框架、阶梯计算鼓、齿轮组、手摇柄、输出刻度盘，底部有象形文字铭带，沿用同一套纸草刻版线稿与低饱和铜色。
- 新机器重画为低饱和铜色线刻，外框 259×272px，高度与右上人脑（272px）完全一致，顶边和底边也对齐；不再用亮金色实底，视觉重量与其他三处线稿一致。
- 抠底：从画布边界做洪水填充去掉纸色背景，再单独清掉无限符号两个内孔和机器内部的白块；输出 1024×1280 透明 WebP（214,618 字节），浅色 `multiply` 与深色反相 `screen` 下均无白边或白块。
- `index.html` 的 alt、`DEMO.md`、`COMPETITION.md` 同步改为黄铜差分机。
- **验收与发布**：`check_site.mjs` 本地与公网均为 `ALL_CHECKS_PASSED` / `NO_CONSOLE_ERRORS`；43 张截图重生成、`NO_BROWSER_ERRORS`；用新 action `c4d9a7e2-3b61-4f0a-8e57-9d2f1a6b8c04` 发布（`published: true`），公网 `seshat-atlas.webp` 与 dist 的 SHA-256 一致。

### 6.30 左上角换成古埃及水钟；修联想浮层残留（第三十轮）

- 左上角差分机仍被判为突兀，按要求整块换掉。新对象为古埃及水钟（clepsydra）：收口陶瓶、瓶身刻度、象形文字铭带、底部出水口与承接水盘，沿用同一套纸草刻版细线语言，低饱和棕墨、无实底金。
- 体量：抠底后缩放到 173×272px，放在 (52,144)–(225,416)，高度与右上人脑（272px）完全一致、顶边与底边对齐；宽度随器物本身比例，不再用矩形外框撑面积。
- 抠底：清掉与画布边界连通的纸白，以及器身内部与水盘里的封闭纯白块；输出 1024×1280 透明 WebP（200,954 字节），浅色 `multiply` 与深色反相下均无白边。
- 桌面端「卡住」的浮层：截图里盖在「科研方法论」上的候选列表是搜索框的联想下拉。它是 `overrideredirect` 独立窗口，以前只靠 Entry 的 `FocusOut` 收起；点无焦点的画布/文字时焦点不转移，切页后浮层就留在新页面上。
  - 改为 `transient` 从属主窗，去掉全局置顶，切到其他应用时不再压在最前；
  - 点任意空白、滚轮、主窗移动/缩放、最小化、输入框卸载或销毁时统一收起；
  - 500ms 巡检：输入框被页面隐藏、祖先容器不可见时自动关闭；
  - `goto()` 切页时显式 `close_all()`，不再依赖焦点事件。
- **验收与发布**：`tools_smoke_app.py` 12 项通过（含素材库）；本地与公网 `check_site.mjs` 均为 `ALL_CHECKS_PASSED` / `NO_CONSOLE_ERRORS`；43 张截图重生成、`NO_BROWSER_ERRORS`；用新 action `51e3c545-fe99-45cc-914b-63c085178010` 发布（`published: true`），公网 `seshat-atlas.webp` 与 dist 的 SHA-256 一致（`422c5d7f…`）。

## 7. 诚实边界

- 桌面原型与核心算法来自用户已有项目；Qoder 中完成的是 Web 化、数据导出、浏览器验收、发布和材料。
- Web 版没有 53.8 万篇 arXiv 向量检索，没有 PDF 下载，没有在线大模型，没有后端数据库。
- 候选分数是结构性估计，不是文献新颖性结论。
- Web 学者目录显示按 ORCID 去重后的全部记录；个人主页只采用 CSRankings 与 ORCID 的公开链接，未收录时不跳转搜索引擎，改由院校官网与 ORCID 核验。机构字段可能滞后或合并错误；ORCID 修正只采用没有结束日期的任职记录，仍建议以 ORCID 原页复核。
- 地区按院校所在机构库（OpenAlex 机构地理字段 + ROR）归档到省市或国家，18,296 位学者中 16,753 位已归档，1,543 位因机构地理字段缺失明确标为「地区待核验」；这是离线快照而非实时定位，机构本身标注错误时会跟着错。院校目录按规范化英文机构名聚合为 2,547 所学校，同名或译名差异仍可能造成合并偏差。
- ORCID 快照覆盖 9,730 个标识（来自 9,774 个学者 ORCID）：8,602 位姓名匹配、5,322 位有公开作品；625 个仅含海外任职、484 个姓名不一致与 19 个弱匹配记录不自动合并，详情页写明原因；其余学者仍展示引用、论文、地区与院校 / DBLP 入口。
- 论文库收录 883 位方向推荐学者的 8,412 篇 ORCID 公开作品（按 DOI / 标题去重，覆盖 25 个领域且全部有分类），不是全部 18,296 位学者，也不是全站检索；非方向推荐学者不自动进入论文库；晚于快照年份（2026）的提前登记年份不计入。
- ORCID 与 ROR 都是 2026-11-18 的离线快照，页面打开时不调用外部接口；学者详情的发表柱状图只统计该 ORCID 下的公开作品，不代表全部成果。
- 素材库的数字来自离线导出与公开基准整理，是演示与核对入口，不是实时全量数据库；552 个条目里 401 个有来源论文链接、72 个只记录论文标题、79 个只有官方页面，目录中的 536 个方向有 534 个被至少一个数据集关联。
- 没有用户调研、留存或转化数据；参赛材料不编造这些指标。

## 8. 产物清单

```text
competition/
  COMPETITION.md          规则映射、作品说明、提交清单
  forum-post.md           天池论坛帖草稿（含占位符）
  DEMO.md                 演示脚本与截图索引
  QODER_LOG.md            本文件
  scripts/
    export_web_data.py    真实数据导出
    export_scholars.mjs   学者去重与主页 / 院校导出
    build_combined_advisor_source.mjs  合并目录与缓存学者记录
    build_materials.mjs   素材库统计
    enrich_direction_links.mjs  方向推荐学者的离线链接补全
    enrich_orcid.mjs     ORCID / ROR 公开记录快照与论文导出（可断点续跑）
    enrich_institution_regions.mjs  院校地区与 ROR 补齐（OpenAlex institutions，可断点续跑）
    expand_applications.mjs     应用标签与方向扩库（幂等）
    expand_venues.mjs           CCF 2026 推荐目录与目录外 venue 合并
    dataset_expansion.mjs       人工整理的公开基准与来源链接
    expand_datasets.mjs         校验分类并幂等合并数据集
    paper_sources.mjs           人工核对的论文标题与链接
    resolve_papers.mjs          arXiv 批量解析来源论文
    resolve_papers_crossref.mjs Crossref DOI 解析来源论文
    sync_web_stats.mjs          对齐 index.json 统计口径
    check_site.mjs        自动化回归
    capture_screenshots.mjs
  screenshots/            43 张验收截图
  site/
    index.html
    assets/               app.js / core.js / styles.css / refine.css / intro.css
    data/
    dist/                 发布产物（被 .gitignore 排除）
    .选题智库.qoder.site  当前 Qoder Sites 描述文件（页面清单与发布信息由平台维护）
```

仓库根目录另有本次发布生成的 `G:\Qoder\workers\.题谱.qoder.site`，由 Qoder Sites 维护，不手工编辑。
