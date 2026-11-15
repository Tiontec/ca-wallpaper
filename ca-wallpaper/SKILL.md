---
name: ca-wallpaper
description: 制作、诊断、修复 iOS 锁屏 Core Animation 分层壁纸（.tendies / .ca 包）。用户提到"景深/深度效果/主体遮挡时间/修复景深/交互壁纸/动态壁纸/导入失败/壁纸库一直转圈/深浅色按钮消失/.tendies/.ca/DynWall/Nugget/GestaltX"，或想把图片做成可交互的 iOS 锁屏壁纸时使用。Fix and build iOS lock-screen layered (Core Animation) wallpapers, especially the Depth Effect (subject covers the clock).
---

# ca-wallpaper — iOS 锁屏分层壁纸（.tendies）

**TL;DR (English).**
A `.tendies` file is a ZIP holding iOS poster descriptors with up to three Core Animation layers
(`Background`, `Floating`, `Foreground`). *Depth effect* = the subject covers the lock-screen clock.
Patching config fields on a package that lacks depth **did not work in 5 attempts**. What worked:
take a package that is *known* to have depth as a **template**, keep all of its files untouched, and only swap in a
**flattened full-screen transparent PNG of the subject** (plus, optionally, the original decorative layers).
`scripts/tendies.py graft` automates exactly that. Depth can only be confirmed on a real iPhone — never claim success before the user confirms.

---

## 1. 先记住这 8 条事实（按证据强度标注）

图例：✅ 在用户真机上验证过　🟡 有间接证据/推测　❓未查明

| # | 事实 | 级别 |
|---|---|---|
| 1 | `.tendies` = ZIP（文件头 `PK`）。头是 `WALLIVE3…` 的是加密私有容器，**无密钥解不开**，别浪费时间 | ✅ |
| 2 | **景深 = 锁屏时间被主体遮住**。壁纸编辑页的 **◐（圆分两半）按钮是深浅色切换，不是景深**；本案例里景深生效时编辑页也没有任何"景深按钮" | ✅ |
| 3 | `Floating` 层**画在时间之上**（树干挡住了时钟），`Background` 在时间之下。`Foreground` 没验证过（所有能用的包里它都是空的） | ✅ |
| 4 | 在"没景深"的包上**打补丁无效**：补 `renderingConfiguration.plist`、补 `preferredRenderingConfiguration`、补 `contentVersion`、改 `appearanceAware`、去 dark 变体、统一状态名、删光动画、换 `index.xml`、统一根图层 id——枯木逢春 v1→v5 全部叠加，仍然没景深 | ✅ |
| 5 | **有效办法**：用一个"确认有景深"的包当模板，配置**一字不改**；把主体渲染成**一张全屏透明 PNG** 放进 Floating 层；原版的叶子/花瓣等装饰图层可以原样保留（含 800 多个图层、7000 多条动画）仍然有景深（v9） | ✅ |
| 6 | 手写 `main.caml` 会让壁纸库**一直转圈**（v6）。要在**模板自己的 caml 文本上改**，保留 `<modules>`/`<states>`/`<stateTransitions>` | ✅ |
| 7 | 深浅色自适应壁纸：`Wallpaper.plist` 里 `appearanceAware=True` + `assets.lockAndHome.dark`；CAML 状态名带后缀 `Locked Light/Locked Dark…`（共 6 个）。去掉 dark → ◐ 按钮整排消失。**深浅色自适应与景深可以并存**（v10） | ✅ |
| 7b | 原版深色 = 只改 Background（纸色淡出、夜空/月亮云淡入），前景树不变；照原版状态表加回即可 | ✅ |
| 8 | **原包没景深的原因：锁在"Floating 里可见主体由原图层拼成"这一点上（v10 已排除 appearanceAware 与 Background）**，但具体机制（小图块？嵌套在摆动父层下？）仍未查明。"图层多"不是判据：李诗雅包锁屏态也有 9 个可见图层（大图、嵌套深度 2–3），失败的原包是 8 块小碎片+整树（嵌套深度 2–5） | 🟡 |

> v10（深浅色自适应 + 景深 + 保留叶子 + 夜空背景）**已由用户真机确认全部功能可用**，并作为模板 B 内置。详见 `references/cases.md`。

---

## 2. 决策树：用户要什么？

```
用户给你一个 .tendies / 描述需求
│
├─ 文件打不开 / 解压失败 / "代码 3" ──► python3 scripts/tendies.py inspect X.tendies
│     头是 WALLIVE3… → 告诉用户这是加密容器，请对方用原 App 导出标准 .tendies。结束。
│
├─ 导入后壁纸库一直转圈 ──► tendies.py validate X.tendies  （看缺 <states>/悬空 targetId/资源缺失）
│
├─ 要【修复景深】（最常见）──► 第 3 节「景深修复标准流程」
│
├─ 要【恢复深色模式 / 保留叶子动画】──► 第 3 节 + 选项 --appearance keep / --keep-layers
│
├─ 要【从图片从零做壁纸】──► scripts/ca_wallpaper.py（见 README）；注意：从零生成的景深成功率不稳，
│                           最稳仍是"套模板"（references/cases.md 案例 1.2）
│
└─ 只是想看看包里有什么 ──► tendies.py inspect / render / diff
```

---

## 3. 景深修复标准流程（照做，不要发明新办法）

**前置：必须有一个"模板"** = **确认在用户手机上有景深**的 `.tendies`。
本技能包已内置两个（见 `templates/README.md`）：
- `templates/template_A_lishiya_depth_ok.tendies`（默认；结构最简单）
- `templates/template_B_kumu_v10_all_ok.tendies`（**深浅色自适应 + 景深 + 叶子动态**，用户确认全部可用）

**先让用户在自己手机上单独导入模板确认景深正常**，再用。画布仅限 390×844；其它机型需要用户提供该机型上验证过的模板。
不要拿"补字段"硬凑。

```bash
T=scripts/tendies.py

# ① 体检：模板和待修包各跑一次，确认格式是 zip、了解结构
python3 $T inspect 模板.tendies
python3 $T inspect 待修.tendies

# ② 对比（可选，用于解释"为什么原包不行"）
python3 $T diff 模板.tendies 待修.tendies

# ③ 看看压平后的主体长什么样（肉眼验收：不能有断枝/错位/空白）
python3 $T flatten 待修.tendies -o /tmp/subject.png --list
#    如果是断枝 → 渲染器坐标系/状态选错了，先查 --state；不要把坏图交给用户

# ④ 嫁接：模板骨架 + 压平主体
#   A. 最保守（先出这版，只有一张树图）
python3 $T graft --source 待修.tendies -o v1_静态.tendies --preview /tmp/pv.png      # 省略 --template = 内置模板 A
#   B. 保留原版叶子/花瓣/动画（v9 的做法，已验证有景深）
python3 $T graft --template 模板.tendies --source 待修.tendies -o v2_动态.tendies --keep-layers
#   C. 再加深色夜景（v10 的做法，用户已真机确认：景深+深色+叶子都正常）
python3 $T graft --template 模板.tendies --source 待修.tendies -o v3_深色.tendies \
        --keep-layers --background source --appearance keep --preview /tmp/pv.png

# ⑤ 交付前自检（graft 会自动跑一次）
python3 $T validate v2_动态.tendies
```

**每次只改一个变量，并按 v1、v2、v3 编号交付。** 顺序建议 A → B → C：
- A 成功 → 配置/模板没问题；B 失败而 A 成功 → 问题在保留的装饰图层；C 失败而 B 成功 → 问题在深浅色自适应或 Background。
- 在枯木逢春上 A/B/C 实际都成功（v7/v9/v10），所以**新项目可以直接出 C**，只有失败时才回头二分。

`graft` 选项速查

| 选项 | 作用 |
|---|---|
| `--template` / `--source` | 骨架（能出景深；省略则用内置 A）/ 画面来源（待修） |
| `--keep-layers` | 保留源包 Floating 里**不可见**的其它图层（叶子、花瓣、动画），只把锁屏态下**可见**的图层压平 |
| `--background solid:#f7f4ec` \| `source` \| `template` | 背景：纯色（默认）/ 用源包（含夜空等）/ 保持模板 |
| `--appearance light-only` \| `keep` | 单外观（默认）/ 深浅色自适应（需配合 `--keep-layers --background source`；该组合在 v10 已验证） |
| `--state "Locked Light"` | 压平时用源包的哪个状态，默认自动选锁屏态 |
| `--exclude 正则` | 压平时排除某些图层（如不想把霜效果烘进去：`--exclude winterFrost`） |
| `--subject-png` | 直接用你自己做好的全屏透明 PNG（尺寸 = 屏幕点数×3，如 1170×2532） |

---

## 4. 铁律（违反就会重蹈覆辙）

1. **别在坏包上打补丁。** 5 次补丁全部无效（事实 4）。用模板重做。
2. **模板里的配置文件、plist、目录名一字不改**；只替换画面（`assets/` 与图层 caml）。
3. **不要手写 `main.caml`。** 改模板自己的文本，或用 `graft`。缺 `<states>` 就会一直转圈。
4. **不要删 dark 变体来"精简"**——◐ 按钮会整排消失，用户很在意。v10 已证明深色与景深可以并存，不要再说"只能二选一"。
5. **渲染器必须按 y 轴朝上处理**，否则断枝/上下颠倒。交付前用 `flatten`/`render` 自己看一眼图。
6. **不要把有状态切换的动态图层合成静态**（例如清晰车↔模糊车），只压平"主体"。
7. **不要声称"已经有景深"**。你没有真机。说"结构自检通过，请在锁屏上看时间是否被主体遮住"。
8. **一次一个变量、版本编号、说清每版改了什么、期望看到什么、失败时发什么截图**。
9. 提醒用户：**导入前先删掉旧版本**（系统/导入工具可能缓存旧配置）。
10. 别把深浅色按钮（◐）当成景深按钮；也别承诺"会出现景深按钮"。

---

## 5. 给用户的测试说明（复制即用）

> 1. 在壁纸库/导入工具里**先删掉**之前导入的同名壁纸，再导入 `vN.tendies` 并应用。
> 2. 回到锁屏（不是编辑页），看**时间数字有没有被树/人物等主体遮住一部分**。有 = 景深生效。
> 3. 如果是深色版：把系统切到深色模式，再看一次锁屏。
> 4. 把锁屏截图发我；如果导入报错，把完整报错文字/截图发我。

---

## 6. 报错对照

| 现象 / 报错 | 原因 | 处理 |
|---|---|---|
| `无法解压 .tendies（代码 3）` / `ArchiveError 13` | 不是 zip。常见：`WALLIVE3…` 加密容器 | `inspect` 看文件头；加密的无解，请来源方重导 |
| 壁纸库缩略图**一直转圈** | 图层 caml 缺 `<states>`/`<modules>`，或悬空 targetId | `validate`；用 `graft` 重做，别手写 caml |
| `ATC manifest read error: read length: channel closed` | `Wallpaper.plist` 里写的 `.ca` 目录名在包里不存在 | `inspect` 会报"plist 引用不存在" |
| `容器根目录不可直接写入` | `descriptors/` 下除 UUID 目录外还有 `LICENSE.txt`/`.DS_Store` 等 | `pack`/`graft` 自动剔除 |
| 有 ◐ 按钮但没景深 | 原包 Floating 的可见主体是原图层拼的（v10 证明与深浅色自适应无关） | 走第 3 节压平主体 |
| 景深有了但 ◐ 按钮没了 | 去掉了 dark 变体 | 用 `--keep-layers --background source --appearance keep`（v10 已验证可与景深并存） |
| 树/主体断枝、错位 | 渲染 y 轴搞反 | 用本工具的渲染器；不要自己写 |
| 动态效果没了 | 把有切换的图层合成了静态图 | 用 `--keep-layers` |

---

## 7. 没有代码执行环境时（纯聊天 AI）

你无法生成二进制包。不要假装能。做法：
1. 把本技能的 `scripts/tendies.py` 和第 3 节命令交给用户，说明在**电脑（Python 3 + Pillow）、iSH/Termux、Pythonista、或任意在线 Python 沙箱**里运行；
2. 让用户把 `inspect`、`diff` 的输出贴回来，你根据输出判断；
3. 你负责：解释结果、选择选项（A/B/C 顺序）、解读用户的截图和报错、起草沟通话术；
4. 绝不让用户手动改 XML 去"补字段"——这条路已被证明无效。

---

## 8. 文件结构速览（详见 `references/format-spec.md`）

```
x.tendies (ZIP)
└── descriptors/<UUID>/
    ├── com.apple.posterkit.provider.descriptor.identifier   "7400"
    ├── com.apple.posterkit.role.identifier                  "PRPosterRoleLockScreen"
    └── versions/1/
        ├── com.apple.posterkit.provider.instance.renderingConfiguration.plist
        ├── contents/
        │   ├── .com.apple.posterkit.provider.contents.configurableOptions.plist
        │   └── 7400.<Family>-390w-844h@3x~iphone.wallpaper/
        │       ├── Wallpaper.plist         ← 清单：变体、appearanceAware、各 .ca 的目录名
        │       ├── 7400.<Family>_Background-….ca/   ┐ 每个 .ca：main.caml + index.xml
        │       ├── 7400.<Family>_Floating-….ca/     │            + assetManifest.caml
        │       └── 7400.<Family>_Foreground-….ca/   ┘            + assets/
        └── supplements/0/…
```

## 9. 参考资料
- `references/playbook.md` — 一步步操作手册 + 分叉排错（含"二分法定位"）
- `references/depth-effect.md` — 景深：证据账本、实验记录、假设与待验证项
- `references/format-spec.md` — 格式规范、坐标系与变换数学、状态命名
- `references/pitfalls.md` — 全部踩坑（含错误原文）
- `references/cases.md` — 真实案例时间线（枯木逢春 v1→v10、大肥鱼、太空保时捷）
- `PROMPT_FOR_ANY_AI.md` — 可直接粘贴给任意 AI 的自包含提示词
