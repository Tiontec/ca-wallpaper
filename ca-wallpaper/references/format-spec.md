# .tendies / .ca 格式规范

## 一、容器层级

```
xxx.tendies (ZIP)
└── descriptors/
    └── <UUID>/                          ← 描述符 ID，如 09E9B685-7456-4856-9C10-47DF26B76C33
        ├── com.apple.posterkit.provider.descriptor.identifier    内容: "7400"
        ├── com.apple.posterkit.role.identifier                   内容: "PRPosterRoleLockScreen"
        ├── providerInfo.plist                                    NSKeyedArchiver，记录最后使用时间
        ├── com.apple.posterkit.provider.identifierURL.suggestionMetadata.plist
        └── versions/
            └── 1/
                ├── com.apple.posterkit.provider.instance.renderingConfiguration.plist
                ├── com.apple.posterkit.provider.instance.complicationLayout.plist
                ├── com.apple.posterkit.provider.instance.titleStyleConfiguration.plist
                ├── RuntimeSnapshotMetadata-lock.plist
                ├── RuntimeSnapshotMetadata-home.plist
                ├── contents/
                │   ├── .com.apple.posterkit.provider.contents.configurableOptions.plist
                │   ├── com.apple.posterkit.provider.contents.otherMetadata.plist
                │   ├── com.apple.posterkit.provider.contents.userInfo
                │   └── 7400.<Family>-390w-844h@3x~iphone.wallpaper/
                │       ├── Wallpaper.plist
                │       ├── 7400.<Family>_Background-390w-844h@3x~iphone.ca/
                │       ├── 7400.<Family>_Floating-390w-844h@3x~iphone.ca/
                │       └── 7400.<Family>_Foreground-390w-844h@3x~iphone.ca/   (可选)
                └── supplements/0/
                    └── com.apple.posterkit.provider.supplementURL.homescreenConfiguration.plist
```

> `descriptors/` 目录下**只能有 UUID 目录**。放 LICENSE.txt / NOTICE.txt /
> STATEMENT.json / .DS_Store 会导致导入工具报「容器根目录不可直接写入」。

---

## 二、Wallpaper.plist

二进制或 XML plist 均可，实测二进制更稳。典型内容：

```json
{
  "assets": {
    "lockAndHome": {
      "default": {
        "name": "显示名",
        "type": "LayeredAnimation",
        "identifier": 7400,
        "backgroundAnimationFileName": "7400.<Family>_Background-390w-844h@3x~iphone.ca",
        "floatingAnimationFileNameKey": "7400.<Family>_Floating-390w-844h@3x~iphone.ca",
        "foregroundAnimationFileName": "7400.<Family>_Foreground-390w-844h@3x~iphone.ca"
      },
      "dark": { "...同名结构...": "深色模式用同一组 .ca" }
    }
  },
  "family": "<Family>",
  "logicalScreenClass": "390w-844h@3x~iphone",
  "appearanceAware": true,
  "identifier": 7400,
  "version": 1,
  "name": "项目名"
}
```

### 关键字段

| 字段 | 说明 |
|---|---|
| `family` | 展示/归类用。**真正必须一致的是 plist 里写的 `.ca` 目录名与包里实际目录名**（`WWDC22` 家族的目录叫 `7400.WWDC_2022-…` 是正常的，`family` 与目录名前缀不必逐字相同）。⚠ 用了系统已有家族名（如 `WWDC22`）曾在壁纸库里多出"iPhone 14 Pro 专用"分类（案例 2） |
| `appearanceAware` | true = 支持深色/浅色/自动切换（**需要配套的 `dark` 变体**） |
| `logicalScreenClass` | 屏幕规格，格式 `<宽>w-<高>h@<scale>x~iphone` |
| `lockAndHome.default` | 默认（浅色）配置 |
| `lockAndHome.dark` | 深色配置；**删掉它，系统的深浅色切换按钮会消失** |

### 常见陷阱

- `Wallpaper.plist` 里写的 `backgroundAnimationFileName` 等指向的目录在包里不存在 → `read length: channel closed`。
  改名要三处同步：目录名、plist 引用、（如有）family。`tendies.py inspect/validate` 会检查。
- `appearanceAware: false` + 只有 `default` → 无深浅色切换按钮（但结构简单）。
- `appearanceAware: true` + 有 `dark` → 有切换按钮（推荐）。

---

## 三、单个 .ca 包

```
xxx.ca/
├── main.caml
├── index.xml
├── assetManifest.caml
└── assets/
    ├── xxx.png
    └── Root_Layer.js   (可选，脚本入口，没被 CAML 引用时不生效)
```

### index.xml（固定内容）

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>rootDocument</key>
  <string>main.caml</string>
</dict>
</plist>
```

### assetManifest.caml（固定内容）

```xml
<?xml version="1.0" encoding="UTF-8"?>

<caml xmlns="http://www.apple.com/CoreAnimation/1.0">
  <MicaAssetManifest>
    <modules type="NSArray"/>
  </MicaAssetManifest>
</caml>
```

---

## 四、main.caml 结构

### 4.1 根节点属性

```xml
<CALayer id="Background" name="CAPlayground Root Layer"
         bounds="0 0 390 844" position="195 422"
         zPosition="0" geometryFlipped="0" opacity="1"
         transform="rotate(0deg) rotate(0deg, 0, 1, 0) rotate(0deg, 1, 0, 0)"
         cornerRadius="0" allowsEdgeAntialiasing="1" allowsGroupOpacity="1"
         contentsFormat="RGBA8" cornerCurve="circular">
```

- `bounds="0 0 W H"`：尺寸用**点**（不是像素）
- `position`：图层中心点，`W/2 H/2` 表示铺满
- `geometryFlipped`：`0` = y 轴朝上（Core Animation 原生），`1` = y 轴朝下
  - **写渲染器时必须按这个处理，否则图会上下颠倒或断枝**

### 4.2 图层与内容

```xml
<CALayer id="img1" name="bg" bounds="0 0 390 844" position="195 422"
         masksToBounds="0" opacity="1" cornerRadius="0">
  <contents>
    <CGImage src="assets/bg.png"/>
  </contents>
</CALayer>
```

- **两个标签嵌套**，不能写成 `<contents src="..."/>`
- 图片会被缩放到 `bounds` 的尺寸
- 圆形裁切：`cornerRadius="半径"` + `masksToBounds="1"`

### 4.3 状态（三个必需）

```xml
<states>
  <LKState name="Locked"><elements>...</elements></LKState>
  <LKState name="Unlock"><elements>...</elements></LKState>
  <LKState name="Sleep"><elements>...</elements></LKState>
</states>
```

每个状态里用多条 `LKStateSetValue` 分别设置属性：

```xml
<LKStateSetValue targetId="img1" keyPath="position.x">
  <value type="real" value="195"/>
</LKStateSetValue>
<LKStateSetValue targetId="img1" keyPath="bounds.size.width">
  <value type="real" value="401.7"/>
</LKStateSetValue>
<LKStateSetValue targetId="img1" keyPath="opacity">
  <value type="integer" value="1"/>
</LKStateSetValue>
```

- `type` 取值：`real`（浮点）/ `integer`（整数）
- **必须给全 position.x/y + bounds.size.width/height + opacity**，
  只给 opacity 就只有淡入淡出，没有视差

### 4.4 状态过渡

```xml
<stateTransitions>
  <LKStateTransition fromState="*" toState="Unlock">
    <elements>
      <LKStateTransitionElement targetId="img1" key="position.y">
        <animation type="CASpringAnimation" damping="50" mass="2" stiffness="300"
                   velocity="0" duration="0.8" fillMode="backwards"
                   keyPath="position.y" mica_autorecalculatesDuration="1"/>
      </LKStateTransitionElement>
    </elements>
  </LKStateTransition>
  ...
</stateTransitions>
```

六个过渡都要写：`*→Locked`、`Locked→*`、`*→Unlock`、`Unlock→*`、`*→Sleep`、`Sleep→*`。

---

## 五、设备尺寸表

| 机型 | 逻辑尺寸(点) | @scale | 像素 |
|---|---|---|---|
| iPhone SE | 375×667 | 2x | 750×1334 |
| iPhone 13 mini | 375×812 | 3x | 1125×2436 |
| iPhone 14 / 13 / 12 | 390×844 | 3x | 1170×2532 |
| iPhone 15 / 14 Pro | 393×852 | 3x | 1179×2556 |
| iPhone 16 Pro | 402×874 | 3x | 1206×2622 |
| iPhone 15 Pro Max | 430×932 | 3x | 1290×2796 |
| iPhone 16 Pro Max | 440×956 | 3x | 1320×2868 |
| iPad 11" | 834×1194 | 2x | 1668×2388 |
| iPad 13" | 1032×1376 | 2x | 2064×2752 |

---

## 六、NSKeyedArchiver 格式的几个 plist

`configurableOptions.plist` / `renderingConfiguration.plist` 等是
NSKeyedArchiver 归档，结构：

```json
{
  "$version": 100000,
  "$archiver": "NSKeyedArchiver",
  "$top": {"root": "<UID(1)>"},
  "$objects": ["$null", {根对象}, {类描述}, ...]
}
```

用 `plistlib` 读写时，`UID` 用 `plistlib.UID(n)` 表示。

`renderingConfiguration.plist` 内容（282 字节，与官方样张逐字节相同）：

```python
objs = ['$null',
        {'$class': plistlib.UID(2), 'depthEffectDisabled': False,
         'motionEffectsDisabled': False},
        {'$classes': ['PRPosterRenderingConfiguration', 'NSObject'],
         '$classname': 'PRPosterRenderingConfiguration'}]
data = {'$archiver': 'NSKeyedArchiver', '$objects': objs,
        '$top': {'root': plistlib.UID(1)}, '$version': 100000}
plistlib.dump(data, f, fmt=plistlib.FMT_BINARY)
```

> ⚠️ 这个文件**不是景深的必要条件**（已验证：有的包没有它照样能出景深）。


---

## 七、层级与时间（实测）

```
         ┌──────────────┐
         │ Foreground   │  未验证（能用的包里都是空）
         ├──────────────┤
         │ Floating     │  ← 在时间【之上】，景深主体放这里（✅ v9）
         ├──────────────┤
         │ 时间 / 组件   │
         ├──────────────┤
         │ Background   │  在时间之下
         └──────────────┘
```

## 八、坐标系与变换（写渲染器/生成器必看）

- `geometryFlipped="0"` 时 **y 轴朝上**，原点在左下。`position` 是图层**锚点**在父层坐标系里的位置。
- 图层几何：`bounds="0 0 W H"` 是点（pt），`anchorPoint` 默认 `0.5 0.5`。
  图层局部点 v → 父层：`p + R(θ)·S(sx,sy)·(v − anchor·bounds)`。
- 旋转：`transform.rotation.z` 单位**弧度**，y 轴朝上时正角度 = 逆时针。缩放写在 `transform="… scale(sx, sy, 1)"`。
- 子层的 `position` 相对**父层 bounds 原点**（geometryFlipped=1 的父层则 y 从顶部往下量）。
- 不透明度**逐级相乘**：父层 opacity=0 则整棵子树不可见（"开花"图层就是这样在锁屏态被隐藏的）。
- 状态覆盖：`LKStateSetValue targetId=… keyPath=…` 支持 `opacity` `position.x/y` `bounds.size.width/height`
  `transform.rotation.z` `transform.scale`。渲染某状态时先应用覆盖值再算变换。
- 图片被拉伸到 `bounds` 尺寸（`contentsGravity` 默认 resize）。
- **不要把 y 轴当成朝下**：枯木逢春第一次渲染树就因此断枝。验证方法：渲染结果与原版截图并排对比。

## 九、状态命名

- 单外观壁纸：3 个状态 `Locked` / `Unlock` / `Sleep`，6 个过渡（`*→X`、`X→*`）。
- 深浅色自适应壁纸（DynWall 导出实例）：6 个状态 `Locked Light` / `Unlock Light` / `Sleep Light` /
  `Locked Dark` / `Unlock Dark` / `Sleep Dark`，过渡同理带后缀。
  ✅ 系统在浅色外观下用 `* Light`，深色下用 `* Dark`（v10 在真机上深浅色都正常）。
- 原版"深色"通常只改 Background：纸色 opacity→0，夜空→1，月亮云→0.17；前景主体不变。
- 把深浅色包改成单外观：删 `* Dark` 状态与过渡，`Locked Light`→`Locked`（`graft --appearance light-only` 自动做）。
- 状态值/过渡里的 `targetId` **必须指向存在的图层 id**，删图层时要同步清理（`validate` 会查悬空引用）。

## 十、caml 里必须保留的块

模板的 `main.caml` 根图层下，除 `<sublayers>` 外还有（以李诗雅为例）`<modules>`、`<states>`、`<stateTransitions>`；
Foreground 是 `<scriptComponents/>` + `<states>` + `<stateTransitions>`。
**缺 `<states>`：壁纸库缩略图一直转圈**（v6）。`<elements/>` 可以是空的，但标签必须在。

## 十一、`index.xml` 与 `assetManifest.caml`

- 能用的包每个 `.ca` 都有 `index.xml`（rootDocument=main.caml）和 `assetManifest.caml`。
- DynWall 导出的 Floating/Background 的 `index.xml` 是最简版；换成模板的版本是 v5 的一部分改动（单独无效，但无害）。
- `graft` 以模板的这些文件为准。
