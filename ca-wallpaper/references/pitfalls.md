# 踩坑记录

真实遇到过的坑，按类别整理。每条都附了错误信息原文，方便搜索。

---

## 一、包格式类

### 1.1 `.tendies` 不一定是 zip

**错误信息**
```
无法解压 .tendies 压缩包（代码 3）
ZIPFoundation.Archive.ArchiveError 错误 13
unzip: short read
```

**诊断**
```bash
head -c 9 file.tendies
# 正常: "PK\x03\x04"
# 异常: "WALLIVE3P" ← 某 App 的加密容器
```

**WALLIVE3P 特征**
- 文件头 9 字节 `WALLIVE3P`
- 熵值 7.999 bits/byte（完全随机）
- 全文除 magic 外无可读字符串
- 无任何 ZIP 签名（PK\x03\x04 / PK\x05\x06 / PK\x01\x02）

**结论**：加密私有容器，**无密钥无法解开**。
让来源方重新导出为标准 `.tendies`，或用对应 App 打开再导出。

### 1.2 descriptors 根目录不能有垃圾

**错误信息**
```
⚠️ 容器根目录不可直接写入，将按 descriptor 目录逐一尝试
```

**原因**：`descriptors/` 下除了 UUID 目录还放了：
- `LICENSE.txt` / `NOTICE.txt` / `STATEMENT.json`
- `.DS_Store`（macOS 残留，常见 5 个）

**处理**：全部剔除，`descriptors/` 下只留 UUID 目录。

### 1.3 plist 里的 .ca 目录名必须真实存在

**错误信息**
```
ATC manifest read error: read length: channel closed
```

**原因**：把 `Wallpaper.plist` 的 `family` 改了、目录没跟着改（或反过来），
`backgroundAnimationFileName` 等指向的 `.ca` 目录在包里不存在，iOS 找不到。
（`family=WWDC22` 而目录叫 `7400.WWDC_2022-…` 本身是正常的。）

**处理**（三处必须同步）：
```
family: "Clownfish"
目录:   7400.Clownfish-390w-844h@3x~iphone.wallpaper
      └── 7400.Clownfish_Background-390w-844h@3x~iphone.ca
plist:  backgroundAnimationFileName = "7400.Clownfish_Background-...ca"
```

### 1.4 zip 不需要目录条目

实测能正常导入的包，zip 里**只有文件条目，没有空目录条目**。
用 Python `zipfile` 逐个 `write()` 文件即可，不必 `mkdir`。

---

## 二、CAML 类

### 2.1 图片引用是两层标签

```xml
<!-- 正确 -->
<contents><CGImage src="assets/bg.png"/></contents>

<!-- 错误：不会有任何报错，但图不显示 -->
<contents src="assets/bg.png"/>
```

### 2.2 y 轴方向

Core Animation 原生 **y 轴朝上**（`geometryFlipped="0"`）。
自己写渲染器合成图片时如果按"y 向下"处理，会得到**上下颠倒**或**断枝**的画面。

第一次做「枯木逢春」静态树时就是这样出的断枝。

### 2.3 只给 opacity 没有视差

`LKState` 里如果只有 `opacity`，三态之间的切换就是纯淡入淡出，
不会有位移/缩放的分层感。

要有视差，必须同时给：
```
position.x / position.y / bounds.size.width / bounds.size.height / opacity
```

### 2.4 浮点数与整数

`bounds` 用整数更稳（`bounds="0 0 390 844"`），
`position` 可以是浮点（`position="156.87304999999998 421.8249536"`）。
生成时把 `206.0` 这类整数浮点格式化成 `206`。

---

## 三、状态与变体类

### 3.1 删 dark 变体 → 深浅色切换按钮消失

**现象**：壁纸编辑界面右侧那排「深色 / 浅色 / 自动」按钮整排不见了。

**原因**：`appearanceAware: true` 依赖 `assets.lockAndHome.dark` 存在。
删掉 dark 后系统认为不支持外观切换。

**恢复**：
```python
d['appearanceAware'] = True
# 保留 d['assets']['lockAndHome']['dark']
```

**教训**：任何"精简结构"的尝试都要先想清楚这个副作用。用户对此非常敏感。

### 3.2 景深与深浅色可以并存 ✅

v9 是单外观（景深 ✅）；v10（景深 + 深浅色 + 叶子动态）用户真机确认全部可用。
不要再说"只能二选一"。做法见 `SKILL.md` §3 的 C 方案。

---

## 四、环境类（iSH / Alpine）

### 4.1 shutil.copy2 / copytree 在深层路径失败

**错误信息**
```
FileNotFoundError: [Errno 2] No such file or directory
shutil.copytree(...) → 每个文件都报 ENOENT
```

**原因**：iSH 文件系统在「深层路径 + 中文目录名」下 `copystat` 失败。

**处理**：自己写拷贝，用 open/read/write：
```python
def copy_tree(src, dst):
    os.makedirs(dst, exist_ok=True)
    for root, _d, files in os.walk(src):
        rel = os.path.relpath(root, src)
        t = dst if rel == '.' else os.path.join(dst, rel)
        os.makedirs(t, exist_ok=True)
        for fn in files:
            with open(os.path.join(root, fn), 'rb') as f:
                data = f.read()
            with open(os.path.join(t, fn), 'wb') as f:
                f.write(data)
```

### 4.2 out of memory

**错误信息**
```
sh: out of memory        ← 连 echo 都跑不了
MemoryError
```

**原因**：同时处理多个 20MB 级壁纸包 + 大 PNG，iSH 内存耗尽。

**处理**：
1. `rm -rf` 清理临时目录 / 中间产物
2. 等 40 秒以上再重试
3. workspace 总量控制在 120MB 以内
4. 大图处理完立即 `im.close()` + `gc.collect()`

### 4.3 PIL floodfill 在 1254² 图上 MemoryError

纯 Python 逐像素 + `ImageDraw.floodfill` 处理 1.5M 像素会爆。

**处理**：用 numpy 向量化（`scripts/` 目录里有 `fast_cut.py` 参考），
或先把图缩到 700px 处理再把 alpha 放大回去。

### 4.4 中文文字渲染成小点

Pillow 默认字体不支持中文且字号被限制。

**处理**：`apk add font-noto-cjk`，然后用
`/usr/share/fonts/noto/NotoSansCJK-Regular.ttc`。

---

## 五、素材处理类

### 5.1 表情包白底

白底表情包直接当"透明立绘"用会盖住背景。

**处理**：
1. 从图像边缘做 flood fill 标记"外部白"
2. 只把与边缘连通的白色设为透明（保留角色内部的白色，如白裙子、米饭）
3. numpy 迭代传播比纯 Python 快 10 倍

### 5.2 表情包自带大字

放大后文字会喧宾夺主。

**处理**：
- 裁掉文字区域（在**原图**上按比例裁，不要在抠图后的 bbox 上裁——
  bbox 已经变过，比例对不上）
- 或者改用无字素材

### 5.3 合成图层 = 毁掉动态

有的壁纸靠「清晰图 ↔ 模糊图」在状态间切换做动态效果
（如太空保时捷：`cargood` / `carblurbetter` / `rock` / `rockblurred`）。

把它们合成成一张静态图，动态就没了。**用户会立刻发现**。

**处理**：保留图层和 opacity 切换；如果要压平主体（景深需要），
只压平主体本身，装饰和切换层保留。

---

## 六、判断与沟通类

### 6.1 别把深浅色按钮认成景深按钮

壁纸编辑界面右侧那个「圆分成两半」的按钮 = **深色/浅色/自动切换**。

已犯过一次，用户纠正。

### 6.2 别在原包上打补丁

反复给原包加字段、改 UUID、改 appearanceAware，全部无效。
**正确做法是拿能用的包当模板重做**，不是在坏包上修。

### 6.3 先确认"能用"的具体含义

用户说"这个包能用景深"时，要确认是：
- 时间被主体遮挡（真景深）
- 还是能看到某个按钮（可能是深浅色）
- 还是只是视差效果（所有壁纸都有）

否则会朝错误方向努力很久。


---

## 七、本次会话新增的坑

### 7.1 手写 main.caml → 壁纸库一直转圈
缺 `<states>`/`<modules>` 等块。**改模板自己的 caml 文本**，不要从头拼。`tendies.py validate` 会提示"缺 `<states>`"。

### 7.2 自己写渲染器，y 轴方向写反
症状：渲染出的树细枝被切断、错位、重复。Core Animation y 轴朝上。
**防再犯**：渲染结果必须和原版截图并排目视对比，再交付。

### 7.3 状态选错，把"开花后"烘进主图
`Unlock*` 状态下叶子可见。压平必须用锁屏态（`Locked` / `Locked Light`）。

### 7.4 用"可见图层数量"判断有没有景深
错。模板（有景深）锁屏态也有 9 个可见图层。别再用这个当判据。

### 7.5 把没验证的当事实
"景深与深色二选一"（后被 v10 证伪）、"Foreground 在时间上"、"根层 contents 挂主体图"都曾被写进旧文档，后经核对不准确或未验证。
文档里**每条结论必须带证据级别**。

### 7.6 一次给用户太多文件/改动太多
用户要逐个测、逐个截图。一次一个变量，版本编号，写清期望现象。

### 7.7 导入前没删旧壁纸
旧配置可能被缓存，现象是"明明改了却没变化"。每次提醒先删后装。

### 7.8 把深浅色按钮 ◐ 当成景深按钮
已犯过。景深没有按钮，看的是"时间被遮住"。

### 7.9 `time` 之类的 shell 内置在 `/bin/sh` 下不存在
在受限沙箱里用 `time` 前缀会让整条命令不执行且无明显报错。需要计时就用 Python。
