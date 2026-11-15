<div align="center">

# ca-wallpaper

**让 iOS 锁屏壁纸出现「景深」——时间被主体挡住的那种效果**

一个写给 AI 的技能包（Skill），也是一套能直接跑的命令行工具。

</div>

---

## 这个技能解决什么问题

iOS 的锁屏壁纸有一种很帅的效果叫 **景深（Depth Effect）**：锁屏时间数字被照片里的主体（树、人、动物）挡住，形成前后层次。

但如果你自己做一张分层壁纸（`.tendies` 包）导入 iPhone，**大概率没有这个效果**，而且——这是最坑的地方——**你根本看不出来哪里错了**：

- 壁纸能正常导入，也能显示
- 编辑界面里找不到任何「景深」开关
- 各项配置字段看起来都对

我在做一个「枯木逢春」动态壁纸时，**连续 5 次尝试全部失败**。这个技能包就是那 5 次失败换来的结论。

---

## 核心发现（一句话版）

> **在一个没有景深的包上打补丁，永远不会成功。**
>
> 正确做法：拿一个**确认能出景深**的包当模板，配置一字不改，只把主体替换成一张全屏透明 PNG。

具体来说，这些「看起来该改」的字段，实测**全部无效**：

| 试过的操作 | 结果 |
|---|---|
| 补 `renderingConfiguration.plist` | ❌ 无变化 |
| 补 `preferredRenderingConfiguration` | ❌ 无变化 |
| 改 `contentVersion` | ❌ 无变化 |
| 改 `appearanceAware` | ❌ 无变化 |
| 删掉 dark 变体 | ❌ 无变化，还导致**深浅色按钮消失** |
| 统一图层 id / index.xml | ❌ 无变化 |
| 删光动画 | ❌ 无变化 |
| 手写 `main.caml` | ❌ 壁纸库**一直转圈** |

而这一条，一次就成了：

| 做法 | 结果 |
|---|---|
| 用能出景深的包当模板 + 主体压成单张透明 PNG 放进 Floating 层 | ✅ 成功，且**保留 800 多个图层动画仍然可用** |

---

## 怎么用

### 方式一：让 AI 帮你修（推荐）

把 [`ca-wallpaper/PROMPT_FOR_ANY_AI.md`](ca-wallpaper/PROMPT_FOR_ANY_AI.md) 整个复制，粘贴给任意 AI（Claude / ChatGPT / Cursor / DeepSeek），然后附上你的 `.tendies` 文件，说：

> 我的壁纸没有景深，按这个提示词帮我修。

这份提示词是**自包含**的：包含全部事实、决策树、操作步骤和常见坑，AI 不需要额外查资料。

### 方式二：自己跑命令行

```bash
# 唯一依赖
pip install pillow          # Alpine 用户：apk add py3-pillow

# 1. 体检：看看包的结构、图层、状态
python3 ca-wallpaper/scripts/tendies.py inspect 你的壁纸.tendies

# 2. 修复：用内置模板 A 重新嫁接
python3 ca-wallpaper/scripts/tendies.py graft \
    --source 你的壁纸.tendies \
    -o 修复后.tendies \
    --preview /tmp/preview.png

# 3. 把 修复后.tendies 发到 iPhone 上打开导入
```

`graft` 会自动：解包源文件 → 用模板的配置骨架 → 把你的画面压成单张透明 PNG → 塞进 Floating 层 → 重新打包。

### 方式三：只想要个能用的成品

`templates/` 里有两个**真机验证过**的模板，可以直接导入试试：

| 模板 | 特性 |
|---|---|
| `template_A_lishiya_depth_ok.tendies` | 景深可用（最简结构） |
| `template_B_kumu_v10_all_ok.tendies` | 景深 + 深浅色自适应 + 叶子动态 + 夜空背景 |

---

## 目录结构

```
ca-wallpaper/
├── SKILL.md                主文档：8 条带证据级别的事实 + 决策树 + 标准流程
├── PROMPT_FOR_ANY_AI.md    ← 复制给 AI 用的自包含提示词
├── AGENTS.md               给 Cursor / Codex / Aider 的入口
├── references/
│   ├── playbook.md         一步步操作手册 + 分叉排错
│   ├── depth-effect.md     景深证据账本：每次实验、结论、未知
│   ├── format-spec.md      .tendies / .ca / CAML 格式规范
│   ├── pitfalls.md         踩过的坑清单
│   └── cases.md            完整案例复盘
├── scripts/
│   ├── tendies.py          主工具：inspect / graft / pack / unpack
│   ├── ca_wallpaper.py     底层 CAML 读写
│   ├── ca_builder.py       分层包构建
│   ├── fast_cut.py         快速抠图辅助
│   └── legacy/             早期失败的实现（保留作反面教材）
└── templates/              两个真机验证过的模板
```

---

## 几条必须知道的硬限制

**1. 景深只能在真机上确认。**
工具只能保证结构自检通过，**不能保证**系统真的出景深。任何声称"已修复"的说法，都必须等你在 iPhone 锁屏上看过才算数。

**2. 编辑页那个 ◐ 按钮不是景深开关。**
它是深色/浅色切换。真正出景深的时候，编辑页里**任何景深按钮都没有**。

**3. `.tendies` 本质是 ZIP。**
但文件头是 `WALLIVE3…` 的是加密私有容器，**没有密钥解不开**，别浪费时间。

**4. 模板只有 390×844 一种尺寸。**
其它机型需要自己调整，或者等你提供对应机型的模板。

---

## 适用与不适用

| 适用 | 不适用 |
|---|---|
| 自己做的 `.tendies` 导入后没有景深 | 想破解加密的官方壁纸 |
| 想把静态图做成可交互锁屏壁纸 | 越狱插件相关（本工具不涉及） |
| 想搞懂 `.ca` / CAML 格式怎么组织 | 需要 macOS 的 Xcode 工程类问题 |

---

## 协议

本项目由 **雾峥奕** 创作，采用《澄影非商业开源许可协议 1.0》。

| | |
|---|---|
| ✅ 允许 | 学习、研究、修改、非商业分享 |
| ✅ 必须 | 保留作者署名；衍生作品沿用同一协议 |
| ❌ 禁止 | **商业用途**、**倒卖转售**、冒充原创 |

详见 [LICENSE](LICENSE)。

---

<div align="center">
<sub>5 次失败换来的 1 条结论，比 5 条看起来对的猜测值钱。</sub>
</div>
