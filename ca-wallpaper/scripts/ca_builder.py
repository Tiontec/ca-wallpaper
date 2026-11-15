#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Core Animation 壁纸包生成器
生成 iOS / iPadOS 可直接使用的 .ca 包（Background / Floating / 单包）

格式来源：CAPlayground (https://github.com/roro2239/CAPlayground-zh_CN)
"""
import os
import zipfile
import json
from xml.sax.saxutils import escape

from PIL import Image, ImageFilter, ImageDraw, ImageFont, ImageEnhance

# ---------------------------------------------------------------- 设备尺寸
# (逻辑宽, 逻辑高, scale)
DEVICES = {
    "iphone-se":        (375, 667, 2),
    "iphone-13mini":    (375, 812, 3),
    "iphone-14":        (390, 844, 3),
    "iphone-15":        (393, 852, 3),
    "iphone-16-pro":    (402, 874, 3),
    "iphone-16-promax": (440, 956, 3),
    "iphone-15-promax": (430, 932, 3),
    "ipad-11":          (834, 1194, 2),
    "ipad-13":          (1032, 1376, 2),
}

# .ca 通常按 @3x 像素出图，但 main.caml 里 bounds 用逻辑点
DEFAULT_DEVICE = "iphone-14"


def device_info(name):
    key = name.lower()
    if key not in DEVICES:
        raise SystemExit(
            "未知设备 %r，可选：%s" % (name, ", ".join(DEVICES))
        )
    w, h, s = DEVICES[key]
    return key, w, h, s


# ---------------------------------------------------------------- 图片工具
def fit_cover(img, tw, th, focus=0.5):
    """等比缩放并居中裁剪到目标尺寸（cover）"""
    sw, sh = img.size
    scale = max(tw / sw, th / sh)
    nw, nh = max(1, round(sw * scale)), max(1, round(sh * scale))
    img = img.resize((nw, nh), Image.LANCZOS)
    left = (nw - tw) // 2
    # focus: 0=顶部 0.5=居中 1=底部
    top = int((nh - th) * focus)
    top = max(0, min(nh - th, top))
    return img.crop((left, top, left + tw, top + th))


def fit_contain(img, tw, th):
    """等比缩放并居中放进画布（contain，空白透明）"""
    sw, sh = img.size
    scale = min(tw / sw, th / sh)
    nw, nh = max(1, round(sw * scale)), max(1, round(sh * scale))
    img = img.resize((nw, nh), Image.LANCZOS)
    canvas = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
    canvas.paste(img, ((tw - nw) // 2, (th - nh) // 2), img if img.mode == "RGBA" else None)
    return canvas


def blur_bg(img, radius=40, brightness=0.7, tw=None, th=None):
    """生成模糊背景版（暗化）"""
    base = img.convert("RGB")
    if tw and th:
        base = fit_cover(base, tw, th)
    b = base.filter(ImageFilter.GaussianBlur(radius))
    b = ImageEnhance.Brightness(b).enhance(brightness)
    return b


def add_vignette(img, strength=0.45):
    """加暗角"""
    w, h = img.size
    mask = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(mask)
    # 径向渐变：中心透明，边缘变暗
    steps = 40
    for i in range(steps, 0, -1):
        f = i / steps
        inset_x = int(w * 0.5 * (1 - f))
        inset_y = int(h * 0.5 * (1 - f))
        alpha = int(255 * (1 - f) ** 2)
        d.ellipse([inset_x, inset_y, w - inset_x, h - inset_y], fill=255 - alpha)
    # 用 mask 做暗化
    dark = Image.new("RGB", (w, h), (0, 0, 0))
    return Image.composite(img, Image.blend(img, dark, strength), mask.point(lambda v: 255 - v))


def add_gradient(img, direction="bottom", color=(0, 0, 0), strength=0.55, extent=0.45):
    """加渐变压暗（给锁屏时间留可读性）"""
    w, h = img.size
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    grad = Image.new("L", (1, h), 0)
    for y in range(h):
        t = y / max(1, h - 1)
        if direction == "bottom":
            a = max(0.0, (t - (1 - extent)) / extent)
        else:
            a = max(0.0, ((1 - t) - (1 - extent)) / extent)
        grad.putpixel((0, y), int(255 * a * strength))
    grad = grad.resize((w, h))
    overlay.putalpha(grad)
    overlay.paste(Image.new("RGB", (w, h), color), (0, 0))
    overlay.putalpha(grad)
    return Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")


def add_text(img, text, position="bottom", size_ratio=0.05, color=(255, 255, 255),
             margin_ratio=0.09, shadow=True, font_path=None):
    """在图片上加一行字"""
    w, h = img.size
    fs = max(12, int(min(w, h) * size_ratio))
    font = None
    if font_path:
        try:
            font = ImageFont.truetype(font_path, fs)
        except Exception:
            font = None
    if font is None:
        import glob
        # 优先中文字体，其次任意 ttf/otf/ttc
        cands = []
        for pat in ("/usr/share/fonts/**/NotoSansCJK*.ttc",
                    "/usr/share/fonts/**/NotoSansCJK*.otf",
                    "/usr/share/fonts/**/*CJK*",
                    "/usr/share/fonts/**/*.ttc",
                    "/usr/share/fonts/**/*.ttf",
                    "/usr/share/fonts/**/*.otf",
                    "/System/Library/Fonts/**/*.ttc"):
            cands = glob.glob(pat, recursive=True)
            if cands:
                break
        for c in cands:
            try:
                font = ImageFont.truetype(c, fs)
                break
            except Exception:
                continue
    if font is None:
        font = ImageFont.load_default()
        # 位图字体不支持大字号，退化为简单提示
        fs = 12

    canvas = img.convert("RGBA")
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    try:
        bbox = d.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    except Exception:
        tw, th = len(text) * fs // 2, fs

    x = (w - tw) // 2
    if position == "bottom":
        y = int(h * (1 - margin_ratio)) - th
    elif position == "center":
        y = (h - th) // 2
    else:
        y = int(h * margin_ratio)

    if shadow:
        sh = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        Sh = ImageDraw.Draw(sh)
        Sh.text((x + 2, y + 2), text, font=font, fill=(0, 0, 0, 160))
        sh = sh.filter(ImageFilter.GaussianBlur(3))
        layer = Image.alpha_composite(layer, sh)
        d = ImageDraw.Draw(layer)

    d.text((x, y), text, font=font, fill=color + (255,))
    return Image.alpha_composite(canvas, layer).convert("RGB")


# ---------------------------------------------------------------- CAML 生成
CAML_NS = "http://www.apple.com/CoreAnimation/1.0"

INDEX_XML = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>rootDocument</key>
  <string>main.caml</string>
</dict>
</plist>"""

ASSET_MANIFEST = """<?xml version="1.0" encoding="UTF-8"?>

<caml xmlns="http://www.apple.com/CoreAnimation/1.0">
  <MicaAssetManifest>
    <modules type="NSArray"/>
  </MicaAssetManifest>
</caml>"""


def layer_attrs(id_, name, w, h, x=0.0, y=0.0, opacity=None, hidden=None):
    a = [
        'id="%s"' % id_,
        'allowsEdgeAntialiasing="1"',
        'allowsGroupOpacity="1"',
        'bounds="0 0 %s %s"' % (_n(w), _n(h)),
        'contentsFormat="RGBA8"',
        'cornerCurve="circular"',
        'geometryFlipped="1"',
        'hidden="%s"' % ("1" if hidden else "0"),
        'name="%s"' % escape(name),
        'position="%s %s"' % (_n(w / 2 + x), _n(h / 2 + y)),
    ]
    if opacity is not None:
        a.append('opacity="%s"' % _n(opacity))
    return " ".join(a)


def _n(v):
    if isinstance(v, float):
        return ("%.6g" % v)
    return str(v)


def build_caml(device_w, device_h, images, states=None, transitions=None,
               scripts=None, bg_color=None):
    """
    images: [{"id","name","src","w","h","x","y","opacity","hidden","scale"}]
    states: {"Unlock": {"#1": {"speed": 1.4, "transform.scale.x": 1.05}}, ...}
    """
    states = states or {}
    lines = []
    A = lines.append
    A('<?xml version="1.0" encoding="UTF-8"?>')
    A('')
    A('<caml xmlns="%s">' % CAML_NS)
    A('  <CALayer %s speed="1">' % layer_attrs("#1", "Root Layer", device_w, device_h))

    if bg_color:
        A('    <backgroundColor value="%s"/>' % bg_color)

    A('    <sublayers>')
    for im in images:
        a = layer_attrs(im.get("id", "#2"), im.get("name", "Layer"),
                        im.get("w", device_w), im.get("h", device_h),
                        im.get("x", 0), im.get("y", 0),
                        im.get("opacity"), im.get("hidden"))
        A('      <CALayer %s>' % a)
        A('        <contents type="CGImage" src="%s"/>' % escape(im["src"]))
        if im.get("scale") and im["scale"] != 1.0:
            s = im["scale"]
            A('        <transform value="%s 0 0 %s 0 0"/>' % (_n(s), _n(s)))
        A('      </CALayer>')
    A('    </sublayers>')

    if scripts:
        for s in scripts:
            A('    <scriptObject relativePath="/assets/%s" src="assets/%s"/>' % (s, s))
    A('    <scriptComponents/>')

    A('    <states>')
    for st in ("Locked", "Unlock", "Sleep"):
        A('      <LKState name="%s">' % st)
        els = states.get(st) or {}
        if not els:
            A('        <elements/>')
        else:
            A('        <elements>')
            for target, kv in els.items():
                for key, val in kv.items():
                    vtype = "real" if isinstance(val, float) else "integer"
                    A('          <LKStateSetValue targetId="%s" keyPath="%s">' % (target, key))
                    A('            <value type="%s" value="%s"/>' % (vtype, _n(val)))
                    A('          </LKStateSetValue>')
            A('        </elements>')
        A('      </LKState>')
    A('    </states>')

    A('    <stateTransitions>')
    for st in ("Unlock", "Locked", "Sleep"):
        A('      <LKStateTransition fromState="*" toState="%s">' % st)
        A('        <elements/>')
        A('      </LKStateTransition>')
        A('      <LKStateTransition fromState="%s" toState="*">' % st)
        A('        <elements/>')
        A('      </LKStateTransition>')
    A('    </stateTransitions>')
    A('  </CALayer>')
    A('</caml>')
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- 打包
def write_ca(out_dir, main_caml, assets, extra=None):
    """把 .ca 写成目录（iOS 原生格式）"""
    os.makedirs(os.path.join(out_dir, "assets"), exist_ok=True)
    with open(os.path.join(out_dir, "main.caml"), "w", encoding="utf-8") as f:
        f.write(main_caml)
    with open(os.path.join(out_dir, "index.xml"), "w", encoding="utf-8") as f:
        f.write(INDEX_XML)
    with open(os.path.join(out_dir, "assetManifest.caml"), "w", encoding="utf-8") as f:
        f.write(ASSET_MANIFEST)
    for name, path in assets.items():
        dst = os.path.join(out_dir, "assets", name)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(dst, "wb") as f:
            with open(path, "rb") as src:
                f.write(src.read())
    for name, content in (extra or {}).items():
        p = os.path.join(out_dir, name)
        os.makedirs(os.path.dirname(p) or out_dir, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(content)
    return out_dir


def zip_dir(src_dir, zip_path):
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for root, _dirs, files in os.walk(src_dir):
            for fn in files:
                full = os.path.join(root, fn)
                rel = os.path.relpath(full, src_dir)
                z.write(full, rel)
    return zip_path
