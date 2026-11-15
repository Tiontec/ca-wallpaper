# 操作手册（Playbook）

适用对象：任何 AI（有/无代码执行环境）。照步骤做，每一步都有"通过标准"和"不通过怎么办"。

---

## 阶段 0：接单（1 分钟）

向用户确认或从上下文读出：

| 要确认 | 为什么 |
|---|---|
| 有没有一个**他确认过景深能用**的 `.tendies`？ | 它是模板。没有就先要，没有就说明只能尝试从零生成（成功率不稳） |
| 目标：只要景深？还要保留叶子/花瓣动画？还要深色模式？ | 决定 graft 选项和交付顺序 |
| 用什么导入？（GestaltX / Nugget / Pocket Poster / 其它） | 报错文案不同；提醒先删旧壁纸 |
| 机型？ | 默认 390×844（@3x）。若是 393×852 / 402×874 等，需在模板里选对应机型，别硬缩放 |

> 别问超过 3 个问题；能从文件推断的（机型、family、是否深浅色）自己用 `inspect` 读出来。

---

## 阶段 1：体检

```bash
python3 scripts/tendies.py inspect 待修.tendies
python3 scripts/tendies.py inspect 模板.tendies
```

| 看到 | 说明 | 动作 |
|---|---|---|
| `✗ Wallive 私有加密容器` | 非 zip | 停。告诉用户请来源方用原 App 导出标准 .tendies |
| `⚠ descriptors/ 下有杂物` | 会导入失败 | `pack`/`graft` 会自动剔除 |
| `⚠ plist 引用的 … 不存在` | 目录名对不上 | 别手改；`graft` 以模板为准 |
| `缺 <states>` | 会转圈 | 不要手改；`graft` |
| Floating 可见图层数/嵌套深度 | 仅供参考（不是判据） | 记录到交付说明 |

---

## 阶段 2：看清差别（可选，写交付说明时有用）

```bash
python3 scripts/tendies.py diff 模板.tendies 待修.tendies
```

读结果的方法：
- "仅 GOOD 有"：模板多出的文件（如 `renderingConfiguration.plist`）——**graft 自动带上，不需要你补**。
- "同名但内容不同"：多半是 identifier、configurableOptions——**以模板为准，不要把待修包的值写回去**。
- 各层复杂度：待修包若 Floating 有几百层/几千动画，是"碎片主体"的典型特征（但不是判据）。

---

## 阶段 3：压平主体并目视验收

```bash
python3 scripts/tendies.py flatten 待修.tendies -o /tmp/subject.png --list
```

打开 `/tmp/subject.png`（铺一个浅色背景看）：

| 通过 | 不通过 → 处理 |
|---|---|
| 主体完整、无断枝、无错位、位置和原壁纸一致 | 断枝/错位 → 检查 `--state`；确认没有用到不支持的特性（遮罩/滤镜/裁切） |
| 没有把"开花后"的叶子烘进去 | 烘进去了 → `--state "Locked Light"`（或包里真正的锁屏态名） |
| 不想要的效果（霜、阴影）不在里面 | 在里面 → `--exclude 正则` |

> **不要把没看过的图交给用户。**

---

## 阶段 4：按顺序出版本（每版一个变量）

```bash
# v1  静态（只有一张树图）——验证模板+主体
python3 scripts/tendies.py graft --template 模板.tendies --source 待修.tendies -o v1_静态.tendies --preview /tmp/pv1.png

# v2  保留叶子/花瓣/动画——验证装饰图层不破坏景深
python3 scripts/tendies.py graft --template 模板.tendies --source 待修.tendies -o v2_动态.tendies --keep-layers

# v3  深色模式（夜空等）——验证深浅色自适应
python3 scripts/tendies.py graft --template 模板.tendies --source 待修.tendies -o v3_深色.tendies \
        --keep-layers --background source --appearance keep --preview /tmp/pv3.png
```

- 源包本来带深浅色自适应时可直接发 v3（已验证组合）；不确定就先发 v1，确认景深后再发 v3。别一次扔 5 个文件让用户自己猜。
- 预览图（`--preview`）里 Light/Dark 两张可以先发给用户看"画面对不对"，但要说明：**预览不含时钟，不能证明景深**。

交付话术（模板）：

> 这是 vN。相对上一版只改了【一件事】。导入前请先删掉旧的。
> 期望：锁屏时【时间被树/人物遮住一部分】。
> 如果没有：请发锁屏截图；如果报错：请发完整报错。
> 说明：我这边没有真机，只能保证文件结构自检通过，景深要靠你确认。

---

## 阶段 5：分叉排错

```
用户反馈
├─ 导入报错 ──► 看第 6 节报错对照 → validate → 把报错原文记入 pitfalls.md
├─ 一直转圈 ──► validate；若通过，确认是否真删了旧版；仍转 → 退回上一个能导入的版本，改动缩小一半再试
├─ 导入成功但没景深
│     ├─ 当前是 v1（静态）──► 模板可能并不真有景深（让用户先单独导入模板确认）；或主体图没盖到时间区域
│     │                       （时间在屏幕上部，主体必须有像素落在时间区域上）
│     ├─ v1 有、v2 无 ──► 装饰图层/动画有影响：缩减保留的图层（逐步删）或放弃动画
│     └─ v2 有、v3 无 ──► 深浅色自适应/Background 有影响：用 depth-effect.md 第 4 节 C/D 版二分
├─ 有景深，但 ◐ 按钮没了 ──► 单外观包的必然结果；要保留就走 v3（`--keep-layers --background source --appearance keep`，v10 已验证深色与景深可并存）
├─ 树/主体看起来不对（断枝、偏移）──► 回到阶段 3
└─ 动态效果消失 ──► 用了 v1；改用 --keep-layers
```

**一个重要的自检：时间区域有没有主体像素。**
时间在屏幕上部（约 y=80–330 pt，宽度居中）。如果主体在这块区域几乎是透明的，景深"看起来"就不会有效果——
这不是文件的问题。可以用 `flatten` 出的 PNG 检查那一块的 alpha 是否有内容。

---

## 阶段 6：收尾

- 把结果写进 `references/cases.md`（版本、改动、用户反馈）。**没验证的写"未验证"。**
- 如果发现新坑，加到 `pitfalls.md`，附错误原文。
- 给用户最终文件：文件名带版本号，`.tendies`。

---

## 附：从零用图片做壁纸

```bash
python3 scripts/ca_wallpaper.py photo.jpg -o out --blur --gradient --parallax
```

- 仅用于"没有现成包"的情况；景深不保证（见 cases.md 案例 1 vs 案例 2）。
- 规律：主体是**一整块**（一张圆形贴纸/一张抠好的人像大图）时更容易有景深；多层、多碎片时更危险。
- 有了任何一个"确认有景深"的包，就改走 `graft`，把你做的主体 PNG 用 `--subject-png` 塞进去。

## 附：无代码环境

见 `SKILL.md` 第 7 节。核心：你不能生成二进制包；教用户跑 `tendies.py`，你负责判断、选项选择、读截图、起草话术。
