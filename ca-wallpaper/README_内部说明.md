# ca-wallpaper · iOS 锁屏分层壁纸技能包（v2）

修复/制作 iOS 锁屏 Core Animation 壁纸（`.tendies`），重点是**景深（时间被主体遮住）**。
v2 相对 v1：核心流程自动化（`tendies.py`），并按真机实验**更正了旧文档的错误**、给每条结论标注了证据级别。

## 30 秒上手
```bash
pip install pillow                      # 唯一依赖；Alpine: apk add py3-pillow
T=scripts/tendies.py
python3 $T inspect  待修.tendies         # 体检
python3 $T graft --source 待修.tendies -o v1.tendies --preview /tmp/pv.png   # 默认用内置模板 A
```
- **模板**：已内置两个用户验证过的（`templates/`），`graft` 省略 `--template` 默认用 A。先让用户在手机上单独导入模板确认景深正常。仅 390×844。
- 景深只能在真机锁屏上确认；工具只保证结构自检通过。

## 目录
```
ca-wallpaper/
├── SKILL.md                  主文档：事实表(带证据级别)、决策树、标准流程、铁律
├── PROMPT_FOR_ANY_AI.md      可直接粘贴给任意 AI 的自包含提示词
├── AGENTS.md                 给 Cursor/Codex/Aider 等的入口（指向 SKILL.md）
├── templates/                已验证模板 ×2：李诗雅(景深) 与 枯木逢春v10(深浅色+景深+叶子动态)
├── references/
│   ├── playbook.md           一步步操作手册 + 分叉排错
│   ├── depth-effect.md       景深证据账本：实验、结论、未知、二分法
│   ├── format-spec.md        格式规范、坐标系/变换、状态命名
│   ├── pitfalls.md           踩坑（含错误原文）
│   └── cases.md              案例时间线（枯木逢春 v1→v10 等）
└── scripts/
    ├── tendies.py            主工具：inspect / diff / render / flatten / graft / validate / pack
    ├── ca_wallpaper.py       从图片生成壁纸（景深不保证）
    ├── ca_builder.py         生成器底层库
    ├── fast_cut.py           numpy 去白底抠图
    └── legacy/               旧脚本（fix_depth.py 已证明无效，仅留作记录）
```

## tendies.py 子命令
| 命令 | 用途 |
|---|---|
| `inspect X` | 格式/结构/配置/图层数据体检，识别加密容器 |
| `diff GOOD BAD` | 对比能用与不能用的两个包 |
| `render X --state S --bg '#hex' -o a.png` | 忠实渲染（y 轴朝上、旋转/缩放/锚点/状态） |
| `flatten X -o subject.png [--list]` | 把锁屏态可见部分压成全屏透明 PNG |
| `graft --template T --source S -o out` | 景深修复主流程，选项见 `SKILL.md` §3 |
| `validate X` | 交付前自检：悬空引用/缺 `<states>`/资源缺失/plist 对不上 |
| `pack DIR -o out` | 安全打包（剔除垃圾文件） |

## 给不同 AI 的用法
- **Claude / Minis / 支持 Skills 的环境**：整个目录拷进技能目录（如 `/var/minis/skills/`）。
- **能跑 Python 的聊天 AI**：贴 `PROMPT_FOR_ANY_AI.md`，上传 `tendies.py` 与两个 `.tendies`。
- **纯聊天 AI**：贴提示词，让用户在别处运行脚本并贴回输出。
- **代码助手**：保留 `AGENTS.md` 在项目根。

## 已知局限
- 渲染器不支持 `masksToBounds` 裁切、遮罩层、滤镜、渐变层、文本层、复制层。遇到时先目视检查压平结果。
- 景深机制未完全查明（已锁定在"原 Floating 可见主体由碎片拼成"）；深浅色自适应 + 景深已由 v10 验证可并存。见 `references/depth-effect.md`。
- 默认 390×844 画布；其它机型请用该机型的模板，不要硬缩放。
