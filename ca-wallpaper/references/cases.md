# 案例库

> 记录原则：**写清谁验证的、在哪验证的；没验证的写"未验证"。**
> 级别：✅ 用户真机确认　🟡 间接证据　❓ 未验证

---

## 案例 1：大肥鱼系列（用户确认能用景深，来源：先前会话记录）

### 1.1 `dafeiyu-wallpaper.tendies`（从零生成的双包）✅
- 只有 Background + Floating（无 Foreground），`appearanceAware=False`，只有 `default` 变体。
- Background：星空渐变；Floating：中央大圆贴纸 + 椭圆环 8 张小贴纸。
- 没有 `renderingConfiguration.plist`（来源：当时的文件清单，未复核）。
- 结论：主体是**整块**，系统识别出来 → 有景深。

### 1.2 `大肥鱼-套用版.tendies`（套李诗雅模板）✅
- 整包复制李诗雅，只替换 12 张图片（保持原文件名与尺寸）。
- 结论：**照抄能用模板、只换图，最稳。** 这是 `graft` 的思路来源之一。

---

## 案例 2：太空保时捷（景深未成功，来源：先前会话记录）

| 版本 | 做法 | 结果 |
|---|---|---|
| 景深版 | 自己写 CAML 双包 + 背景虚化 | ❌ 无景深 |
| 景深动态版 | 保留 6 层原结构，追加 position/bounds 视差 | ❌ 动态保住，无景深 |
| fix_depth 版 | 原包补配置 + family 改名 | ❌ 壁纸库多出"iPhone 14 Pro 专用"分类 |

动态机制（必须保留）：`cargood/rock`（清晰）↔ `carblurbetter/rockblurred`（模糊），Locked 清晰，Unlock 交叉切到模糊。
待办：用模板重做（压平"车+陨石"为静态主体，保留切换层）。❓ 未做。

---

## 案例 3：枯木逢春（DynWall 导出）—— 完整时间线（本技能的主要实验来源）

原包：16 MB，Floating 828 个图层 / 7274 条动画 / 419 个资源；Background 夜空+月亮云+纸色；深浅色自适应。
Floating 锁屏态可见的只有：树干 `tree-base.png` + 8 块 `twig-family*.png` 细枝图块 + `winterFrost`（25%）。
其余 800 多个图层是"开花"用的（`bloom/dayLeaf/nightLeaf/snow`），锁屏态 opacity=0，解锁时才出现。

结果见 `depth-effect.md` 第 3 节表格。要点：

1. v1–v5 把"能想到的配置差异"全对齐了，**仍然没有景深**。
2. v6 手写 caml → 转圈。
3. v7 起：**模板骨架 + 在模板 caml 文本上替换内层图层 + 压平树图** → 景深出现。
4. v7 的树断裂：不是素材问题，是我自己渲染器的 **y 轴方向写反**（Core Animation y 轴朝上）。
   对比方法：把渲染结果和用户给的原版截图并排看，一眼就能发现。
5. v9：把"开花叶子/动画"原样放回去（只删可见碎片），**景深仍在** ✅。用户评价"已经很可以了"。
6. 用户反馈"深色模式下没有效果"。查原版状态表：**深色只改 Background**（纸色 opacity→0，nightSky→1，moonCloud→0.17），
   树本身不变。→ v10 把 Background 与 Light/Dark 状态加回，`appearanceAware=True` + dark 变体。
   ✅ **用户真机确认：景深、深色模式、叶子动态全部可用。** v10 已作为模板 B 内置。

### 具体到 v9 的结构（图层位置的修正）
- 压平后的树图是 **一个名为 `tree1`/`subject1` 的子图层**，放在 Floating 内层 `Root Layer` 的 `<sublayers>` **最前面**（最底下），
  不是挂在 Floating 根图层自己的 `<contents>` 上。（旧文档写错了。）
- Background 在 v9 里是**一个纯色图层**（`backgroundColor="0.9686 0.9569 0.9255"`），0 个资源。
- Wallpaper.plist：模板原样 + `appearanceAware=False` + 仅 `default`；`contentVersion=1.01`。
- （v10 差异：`appearanceAware=True`，`lockAndHome` 有 `default` 与 `dark`（同一组 .ca，identifier 相差 1）；Background 用源包的纸色/夜空/月亮云；Floating/Background 保留 Light/Dark 六个状态。）
- 保留了的 Floating 图层：~790 个（bloom/leaf/snow），动画/状态原样（Light/Dark 后缀的状态已改名为 Locked/Unlock/Sleep，Dark 状态已删）。
- 被删的图层：`tree`、`winterFrost`、`familyTexture0–7`（已压进主图）以及状态/过渡里对它们的引用。

### 对"为什么"的诚实评价
现在知道：**把 Floating 里可见主体换成一张压平图，景深出现；其余复杂度（800 个图层、7000 条动画、深浅色自适应、夜空背景）都不碍事**——v10 同时包含这些且景深正常。
仍不知道：是"碎片"本身、"嵌套在摆动父层下的小图块"、还是别的细节。见 `depth-effect.md` §3。

---

## 通用规律（带置信度）

| 规律 | 置信度 |
|---|---|
| 套已知有景深的模板、只换画面，成功率最高 | ✅（大肥鱼套用版、枯木逢春 v7/v9） |
| 在没景深的包上补字段/改配置，几乎无效 | ✅（枯木逢春 v1–v5） |
| 手写 main.caml 容易转圈 | ✅（v6） |
| 主体是一整块比碎片更稳 | 🟡（案例 1、3 一致；但模板本身有 9 个可见图层，机制不明） |
| 深浅色自适应与景深可并存 | ✅（v10） |
| 深色模式 = 只改 Background | ✅（原版状态表 + v10） |
| 层数多/动画多会毁掉景深 | ❌ 已被 v9 证伪（保留了 790 个图层与全部动画仍有景深） |
