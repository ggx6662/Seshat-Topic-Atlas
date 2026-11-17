---
version: alpha
name: 知识库助手-科研选题工作台-design-analysis
description: "A deep-navy research workstation built around #061220 canvas with a four-step surface ladder (#08182A sidebar → #0C2135 card → #0E2539 raised → #10304A overlay). Cyan #6BE7FF is the single brand accent, reserved for interactive affordances, key numbers, and the active navigation state — never used as a surface fill. Text runs a five-step cool-gray ladder from #EDF8FF ink down to #7794AB tertiary. The system reads as laboratory instrument: dense, technical, information-first, with hairline borders instead of shadows for hierarchy."
colors:
  primary: "#6BE7FF"
  on-primary: "#04222E"
  primary-hover: "#8FEEFF"
  primary-muted: "#0E4B63"
  ink: "#EDF8FF"
  ink-secondary: "#B4CFE0"
  ink-tertiary: "#8AA8BF"
  ink-quaternary: "#7794AB"
  canvas: "#061220"
  surface-nav: "#08182A"
  surface-card: "#0C2135"
  surface-raised: "#0E2539"
  surface-overlay: "#10304A"
  hairline: "#1B3A53"
  hairline-soft: "#14304A"
  semantic-success: "#43FFC9"
  semantic-warning: "#FFD166"
  semantic-danger: "#FF6F91"
  semantic-info: "#B69CFF"
  semantic-orange: "#FFB37A"
  semantic-neutral: "#8E9BB0"

typography:
  display:
    fontFamily: Microsoft YaHei UI
    fontSize: -32px
    fontWeight: bold
    lineHeight: 1.25
    letterSpacing: 0
  page-title:
    fontFamily: Microsoft YaHei UI
    fontSize: -24px
    fontWeight: bold
    lineHeight: 1.30
  section:
    fontFamily: Microsoft YaHei UI
    fontSize: -18px
    fontWeight: bold
    lineHeight: 1.35
  body:
    fontFamily: Microsoft YaHei UI
    fontSize: -16px
    fontWeight: normal
    lineHeight: 1.55
  body-sm:
    fontFamily: Microsoft YaHei UI
    fontSize: -15px
    fontWeight: normal
    lineHeight: 1.55
  caption:
    fontFamily: Microsoft YaHei UI
    fontSize: -13px
    fontWeight: normal
    lineHeight: 1.45
  label:
    fontFamily: Microsoft YaHei UI
    fontSize: -13px
    fontWeight: bold
    lineHeight: 1.35
  metric:
    fontFamily: Consolas
    fontSize: -26px
    fontWeight: bold
    lineHeight: 1.20
  mono:
    fontFamily: Consolas
    fontSize: -13px
    fontWeight: normal
    lineHeight: 1.50

rounded:
  xs: 4px
  sm: 6px
  md: 8px
  lg: 10px
  xl: 14px
  pill: 9999px

spacing:
  xxs: 4px
  xs: 6px
  sm: 8px
  md: 12px
  lg: 16px
  xl: 24px
  xxl: 32px
---

## Overview

这是一个**科研工具**，不是营销页。用户是研究生和本科生，会在上面停留很久、读大量文字、比较多个候选。

因此视觉原则与消费级产品相反：

- **信息密度优先**，不追求大留白
- **层级靠描边和色阶**，不靠投影和装饰
- **彩色只服务于语义**：青色 = 可交互 / 关键数字，绿黄红紫 = 状态

画布 `{colors.canvas}` (#061220) 是深海军蓝，四个台阶承载层级：

```
canvas #061220 → sidebar #08182A → card #0C2135 → raised #0E2539 → overlay #10304A
```

**Key Characteristics:**
- 单一品牌色 `{colors.primary}` 青色 #6BE7FF，只用于：导航选中态、主按钮、可点击链接、关键数字
- 四阶表面梯子，每阶 +2~3% 亮度，1px 描边 `{colors.hairline}`
- 文字五阶冷灰，最低阶在卡片上仍 ≥4.5:1（WCAG AA）
- 等宽字体 Consolas 只用于数字、编号、代码 —— 让数值对齐、可扫读
- 状态色四个：绿=通过、黄=待补、红=风险、紫=创新/方法论

## Colors

### Brand & Accent
- **Cyan** ({colors.primary} #6BE7FF): 唯一品牌色。导航选中、主按钮文字、可点击元素、关键指标。
- **Cyan Hover** ({colors.primary-hover} #8FEEFF): 悬停提亮。
- **Cyan Muted** ({colors.primary-muted} #0E4B63): 青色按钮的底色、选中行的背景。

### Surface
- **Canvas** ({colors.canvas}): 页面底。
- **Surface Nav** ({colors.surface-nav}): 左侧导航栏。
- **Surface Card** ({colors.surface-card}): 卡片默认。
- **Surface Raised** ({colors.surface-raised}): 列表行、次级卡片。
- **Surface Overlay** ({colors.surface-overlay}): 模态、悬浮层。

### Text
- **Ink** ({colors.ink}): 主文字 —— 标题、正文强调。
- **Ink Secondary** ({colors.ink-secondary}): 正文。
- **Ink Tertiary** ({colors.ink-tertiary}): 说明、注释。
- **Ink Quaternary** ({colors.ink-quaternary}): 占位符、最弱信息（仍 ≥4.5:1）。

### Semantic
- **Success** ({colors.semantic-success}): 已具备、匹配、通过。
- **Warning** ({colors.semantic-warning}): 待补、需注意。
- **Danger** ({colors.semantic-danger}): 风险、失效、错误。
- **Info** ({colors.semantic-info}): 创新点、方法论、跨领域。
- **Orange** ({colors.semantic-orange} #FFB37A): 第五个语义色，只用于「跨源/外部」标签（如从 arXiv 补进来的学者、非本库来源的论文）。它与 Info 的紫色分开，是为了让「外部来源」和「方法论」不混在一起。

## Typography

### 为什么用像素值

Tk 的 `pt` 字号会乘上 `tk scaling`（本机 1.333），9pt 被渲染成 17px —— **非整数倍拉伸，字形发虚**。
全部改用负值像素单位，字形落在整数网格上。

| Token | 像素（125% 缩放） | 用途 |
|---|---|---|
| `{typography.display}` | 32px | 总览页问候语 |
| `{typography.page-title}` | 24px | 各页面标题 |
| `{typography.section}` | 18px | 区块标题、卡片标题 |
| `{typography.body}` | 16px | 正文、列表主文字 |
| `{typography.body-sm}` | 15px | 次要正文 |
| `{typography.caption}` | 13px | 说明、标签、注释 |
| `{typography.label}` | 13px 粗 | 字段名、小标题 |
| `{typography.metric}` | 26px 粗 等宽 | 统计数字 |
| `{typography.mono}` | 13px 等宽 | 编号、分数、路径 |

### 原则

- **只有 5 个字号档位**（13 / 15 / 16 / 18 / 24/32），不再随手写 F(7)…F(21)
- **最小 12px**：12px 以下的中文笔画会粘连
- 等宽字体只出现在「需要对齐比较」的地方：分数、引用量、编号

## Layout

### Spacing System
- 基础单位 4px
- 卡片内边距 16px；页面边距 16px；区块间距 24px
- 左侧导航固定 208px

### 布局原则
- 三栏工作台（列表 / 详情 / 资源）用于选题工坊
- 两栏（列表 / 详情）用于创新点库、导师、期刊会议
- 单栏 + 筛选器用于文献库、方向图谱

## Components

### Buttons
- **primary**: 底 `{colors.primary-muted}`，字 `{colors.primary}`，圆角 `{rounded.sm}`
- **ghost**: 底 `{colors.surface-raised}`，字 `{colors.ink-secondary}`
- **danger**: 底深红，字 `{colors.semantic-danger}`

### Cards
- 圆角 `{rounded.lg}` 10px，1px `{colors.hairline}` 描边，无投影
- 卡片标题用 `{typography.section}`，说明用 `{typography.caption}`

### Lists
- 行高至少 34px，斑马纹用 `{colors.surface-card}` / `{colors.surface-raised}` 交替
- 悬停时背景提到 `{colors.hairline-soft}`

### Badges / Pills
- 状态徽章：`{rounded.xs}` 4px，`{typography.caption}`，底色取对应语义色的暗版

## Three Surfaces（客户端 / 网页 / 手机）

同一套设计系统跑在三个形态上。**色彩、字号档位、圆角、语义色、卡片描边、等宽数字全部共享**，
只有三个维度按形态调整 —— 这就是「看得出是同一个产品，但各自适合自己的设备」的做法。

| 维度 | 客户端（Tkinter） | 网页版（浏览器） | 手机（≤860px） |
|---|---|---|---|
| `pad` 内边距 | 16px | 24px | 14px |
| `row_h` 行高 | 34px | 42px | 48px |
| `gap` 区块间距 | 12px | 18px | 14px |
| `line_h` 行距 | 1.5 | 1.65 | 1.75 |
| 首屏列数 | 1 | 2 | 1 |
| 导航形态 | 左侧固定 208px 竖栏 | 顶部横排 tab | 顶部横滑 tab（带右缘渐隐遮罩） |

**为什么只有这三个维度**：
- **密度**跟着输入设备走。鼠标点击目标 34px 就够；手指要 44px 以上，所以手机行高 48px、触控目标 ≥44px。
- **导航**跟着屏幕比例走。桌面宽、可以常驻竖栏；手机窄，竖栏会吃掉 1/3 屏宽，改横排。
- **首屏列数**跟阅读距离走。手机一行放两栏，每栏不到 160px，中文 6 个字就折行。

**共享的部分一个都不许分叉**：色值从 `design_tokens.py` 单一来源取，网页端由 `web_server._token_style()`
注入 `<!-- DESIGN_TOKENS -->` 占位符，客户端由 `app_theme.py` 从 `_DT.COLORS` 取。改配色只改一个文件。

### 三端刻意保留的一致细节
- 卡片圆角统一 10px，描边统一 1px `{colors.hairline}`，**任何一端都不加投影**
- 数字统一等宽字体，单位紧贴数字（`1.8万` 而不是 `1.8 万`）
- 零值不画条形（避免把「没有」看成「有一点」）
- 长尾数据用对数刻度，并在脚注写「对数刻度」
- 手机端 `#q` 输入框字号固定 16px —— 低于 16px 时 iOS Safari 会在聚焦时自动放大页面

## Do's and Don'ts

### Do
- 青色只用在「可点的」和「关键数字」上
- 层级用表面阶梯 + 描边，不要加投影
- 数字一律用等宽字体
- 说明文字不低于 13px
- 三端改样式先改 `design_tokens.py`，再各端取用
- 图表没有数据时画居中的「暂无数据」，不要画一个空坐标轴

### Don't
- 不要用青色做大面积背景
- 不要引入除四个状态色之外的颜色
- 不要用 12px 以下的字号
- 不要在一个页面里出现 5 种以上的字号
- 不要给某一端单独发明一套配色或字号
- 不要把 0 值画成一个短条
- 不要在卡片上放 >1px 的彩色左边框
- 不要用 Unicode 符号充当图标系统