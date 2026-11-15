# 景深（Depth Effect）：证据账本

> 目的：让后来的 AI 清楚**哪些是验证过的、哪些是猜的、哪些根本不知道**，
> 避免把推测当事实传给用户，也避免重走已被证伪的路。

## 1. 先认清"景深"是什么

- 表现：**主体（树/人物/物体）盖在锁屏时间数字上**，时间像嵌在画面里。
- 判断只有一个办法：**看锁屏上时间是否被主体遮住一部分**（编辑页预览也可以，但以锁屏为准）。
- 壁纸编辑页右侧的 **◐（圆分两半）= 深浅色切换**，不是景深。本案例中景深生效时，编辑页**没有出现任何景深按钮**。
  用户可能会说"帮我加景深按钮"——要解释清楚：自定义 CA 壁纸没有观察到这样的按钮，目标是"时间被遮住"。

## 2. 层级与时间的关系

| 层 | 相对时间 | 证据 |
|---|---|---|
| Background | 在时间**之下** | ✅ v9：纸色背景放 Background，树放 Floating，树干盖住时钟 |
| Floating | 在时间**之上**（景深主体放这里） | ✅ 同上 |
| Foreground | 未验证 | 所有"能用景深"的包里它都是空壳 |

> 旧文档曾写"Foreground 在时间上、Floating 在时间下"，与实测相反，已更正。

## 3. 实验记录（枯木逢春，用户真机 + GestaltX 导入）

基线：原包 `枯木逢春.tendies`（DynWall 导出，828 个图层、7274 条动画、深浅色自适应）→ **无景深**。
模板：`李诗雅修复景深.tendies` → **有景深**。

| 版本 | 改动（累积） | 结果 |
|---|---|---|
| v1 | 补 `renderingConfiguration.plist`、模板的 `configurableOptions`（含 role/luminance/preferredRenderingConfiguration）、`contentVersion` | ❌ 无景深 |
| v2 | + `appearanceAware=False`、删 dark 变体、统一 identifier=7400、三层根图层 id 改成 Background/Floating/Foreground | ❌ 无景深；◐ 按钮消失 |
| v3 | + 状态名 `Locked Light`→`Locked` 等，删 Dark 状态 | ❌ |
| v4 | + 删除全部 `<animation>` 与状态值（静态） | ❌ |
| v5 | + 三层 `index.xml` 换成模板的 | ❌ |
| v6 | 改用模板骨架 + **手写** main.caml + 压平树图 | ❌ 导入后**一直转圈** |
| v7 | 模板骨架 + **在模板 caml 文本上替换内层图层** + 压平树图（渲染器 y 轴写反 → 断枝） | ✅ 景深出现（树断裂难看） |
| v8 | 渲染器改成 y 轴朝上 → 树无缝 | 用户未单独反馈 |
| v9 | v8 + 保留原版叶子/开花图层与动画（可见碎片已压平进主图） | ✅ 景深保持；用户评价"已经很可以"；仅缺深色模式 |
| v10 | v9 + 源包 Background（纸色/夜空/月亮云）+ Light/Dark 状态 + `appearanceAware=True` + dark 变体 | ✅ **用户确认：景深 + 深色模式 + 叶子动态全部可用** |

### 能从中得出的结论
1. v1–v5 说明：**配置字段、appearanceAware、状态名、动画、index.xml 都不是（单独或累加的）阻断原因**——因为全改成和模板一致后仍无景深。
2. v7 vs v5 唯一实质差别：**画面内容的组织方式**——v5 沿用原包的 Floating（可见部分由 8 块小碎片 + 整树图组成，嵌套在会摆动的父层下）和 Background（含 nightSky/moonCloud 等 6 层）；v7 是 1 张压平图 + 纯色背景。
3. v9 说明：**不可见的叶子图层、7000 多条动画、819 个图层的复杂结构，本身不阻断景深。**
4. v6 vs v7：**手写 caml 导致转圈**；改模板自己的 caml 文本后恢复。（具体缺哪一块没有逐项隔离，已知 v6 缺 `<states>`/`<modules>`，v7 保留了它们。）

5. **v10 排除了 H2 和 H3**：它同时用着源包的 Background（含夜空等）和 `appearanceAware=True`，景深正常。所以原包没景深，剩下的差别只有——**Floating 里可见主体是否由原图层拼成**。

### 仍然未知（别当成结论）
- **碎片主体为什么没景深？** 候选：
  - H1 可见主体由多块**带 alpha 的小图块**拼成，且嵌套在**带旋转动画**的父层里，系统无法得到稳定的主体蒙版；
  - ~~H2 原包 Background 的某些图层/动画干扰~~ ❌ 已被 v10 排除；
  - ~~H3 `appearanceAware=True` 与景深互斥~~ ❌ 已被 v10 排除。
- 反例：模板（李诗雅）锁屏态有 9 个可见图层，景深正常；它们是 3 张大图 + 6 张小图，嵌套深度 2–3。所以 **"可见图层多 = 没景深"是错的**，`tendies.py inspect` 已删除这条判断，只输出数据。
- 更细的机制（H1 里到底是"小图块"、"带 alpha"还是"嵌套在摆动父层下"）没有隔离实验。若要查，可做对照：只压平 8 块 `twig-family`，保留 `tree-base` 与 `winterFrost` 为独立图层，看景深是否出现。

## 4. 如何验证/二分（推荐流程）

用同一个 `source` 与同一个 `template`，按顺序各出一版，让用户逐个测：

| 版本 | 命令选项 | 测什么 |
|---|---|---|
| A | 默认（静态、纯色背景、单外观） | 模板与压平主体是否 OK |
| B | `--keep-layers` | 保留装饰图层/动画是否破坏景深 |
| C | `--keep-layers --background source --appearance light-only` | 源包 Background（夜空等）是否破坏景深（H2） |
| D | `--keep-layers --background solid:#f7f4ec --appearance keep` | 深浅色自适应是否破坏景深；深色下背景仍是纸色，只用于定位 |
| E | `--keep-layers --background source --appearance keep` | 完整目标版（v10，枯木逢春上已验证） |

> 在枯木逢春上 A/B/E 都已成功，所以新项目直接出 E，失败才回头二分。

首个失败的版本就定位了原因。把结果写回 `cases.md`，别只留在聊天里。

## 5. 已被证伪的路（别再走）

| 方案 | 结果 |
|---|---|
| 补 `renderingConfiguration.plist`（depthEffectDisabled=false） | ❌ 单独/叠加均无效 |
| 补 `preferredRenderingConfiguration`、`role`、`luminance` | ❌ |
| 改 descriptor UUID 为模板的 UUID | ❌（旧记录） |
| 改 `appearanceAware` / 删 dark | ❌ 且丢 ◐ 按钮 |
| 把内容搬到 Foreground | ❌（旧记录） |
| 给 `LKState` 补 position/bounds 做视差 | ❌（旧记录） |
| 在原包上改任何东西 | ❌ 用模板重做 |

> 注：模板自带 `renderingConfiguration.plist`，graft 因为原样保留模板而自然带上它。
> 是否"必要"没有隔离实验（旧记录称有一个能用的包没有它，来源未复核）。不要在文档里声称"它无关紧要"，只说"补它不能让坏包变好"。

## 6. 压平主体时的注意点

- 压平 = 用 `tendies.py flatten`（等价于 graft 内部做的）：把源包 Floating 在**锁屏态**下所有**可见**图层按真实变换合成一张 `屏幕点数×3` 的透明 PNG。
- **状态选择**很重要：深浅色包默认选 `Locked Light`；如果选错（如 `Unlock`），会把"开花"后的状态烘进主图。
- 渲染器已支持：position / bounds / 锚点 / `transform.rotation.z` / `scale` / 透明度逐级相乘 / 状态覆盖 / `geometryFlipped`。**不支持**：`masksToBounds` 裁切、遮罩层、滤镜、渐变层、文本层、`CAReplicatorLayer`。遇到这些，flatten 的结果可能与真机不同——一定先目视检查。
- 主图建议保持 `屏幕点数×3` 且 PNG 3–4 MB 内，过大没有收益。
- 想让主图里不含某些效果（霜、阴影）：`--exclude 正则`。
