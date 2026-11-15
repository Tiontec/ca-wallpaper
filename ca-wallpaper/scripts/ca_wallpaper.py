#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ca_wallpaper.py — 一条命令把图片变成 iOS Core Animation 壁纸包

用法示例：
  # 单张，iPhone 14，加模糊背景 + 底部渐变 + 视差放大
  python3 ca_wallpaper.py bg.jpg -o MyWall --device iphone-14 --blur --gradient --parallax

  # 加一行文字
  python3 ca_wallpaper.py bg.jpg -o MyWall --text "保持热爱"

  # 批量：整个文件夹每张图各出一套
  python3 ca_wallpaper.py ./photos --batch -o ./out --blur --gradient

  # 只出单个 .ca（不拆 Background/Floating）
  python3 ca_wallpaper.py bg.jpg -o MyWall --single

  # 额外打包成 .tendies（Nugget / Pocket Poster 用）
  python3 ca_wallpaper.py bg.jpg -o MyWall --tendies
"""
import argparse
import os
import shutil
import sys
import uuid

from PIL import Image

from ca_builder import (
    DEVICES, DEFAULT_DEVICE, device_info, fit_cover, blur_bg, add_vignette,
    add_gradient, add_text, build_caml, write_ca, zip_dir,
)

DEFAULT_DESC_DIR = "09E9B685-7456-4856-9C10-47DF26B76C33"
DESC_UUID_WALLPAPER = "99990000-0000-0000-0000-000000000000"


def log(msg):
    print("[ca] " + msg, flush=True)


def copy_tree(src, dst):
    """稳定的目录拷贝（避免 shutil.copytree 在深层路径上的怪问题）"""
    os.makedirs(dst, exist_ok=True)
    for root, dirs, files in os.walk(src):
        rel = os.path.relpath(root, src)
        target = dst if rel == "." else os.path.join(dst, rel)
        os.makedirs(target, exist_ok=True)
        for fn in files:
            with open(os.path.join(root, fn), "rb") as f:
                data = f.read()
            with open(os.path.join(target, fn), "wb") as f:
                f.write(data)
    return dst


def process_image(src, opts, out_root, dev_key):
    name, w, h, scale = device_info(dev_key)
    pw, ph = w * scale, h * scale
    log("设备 %s  →  %dx%d 点  @%dx  = %dx%d 像素" % (name, w, h, scale, pw, ph))

    img = Image.open(src).convert("RGB")

    # 1) 背景层：模糊 + 暗化（可选）
    bg_path = os.path.join(out_root, "_tmp_bg.png")
    if opts.blur:
        bg = blur_bg(img, radius=opts.blur_radius, brightness=opts.blur_bright,
                     tw=pw, th=ph)
    else:
        bg = fit_cover(img, pw, ph, focus=opts.focus)

    if opts.vignette:
        bg = add_vignette(bg, opts.vignette_strength)
    if opts.gradient:
        bg = add_gradient(bg, direction=opts.gradient_dir,
                          strength=opts.gradient_strength)
    if opts.text:
        bg = add_text(bg, opts.text, position=opts.text_pos,
                      size_ratio=opts.text_size, color=tuple(opts.text_color))
    bg.save(bg_path, "PNG", optimize=True)

    # 2) 前景层：清晰主体（可选，居中 contain）
    fg_path = None
    if opts.floating:
        fg = img.copy()
        # 前景按比例缩小一点，做出悬浮感
        fw = int(pw * opts.floating_scale)
        fh = int(ph * opts.floating_scale)
        fg = fit_cover(fg, fw, fh, focus=opts.focus)
        canvas = Image.new("RGBA", (pw, ph), (0, 0, 0, 0))
        canvas.paste(fg, ((pw - fw) // 2, (ph - fh) // 2))
        fg_path = os.path.join(out_root, "_tmp_fg.png")
        canvas.save(fg_path, "PNG", optimize=True)

    base = os.path.splitext(os.path.basename(src))[0]
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in base) or "wallpaper"
    proj = opts.name or safe

    # ---------- 单包模式 ----------
    if opts.single:
        layers = [{
            "id": "#2", "name": "Background", "src": "assets/bg.png",
            "w": w, "h": h,
        }]
        if fg_path:
            layers.append({
                "id": "#3", "name": "Floating", "src": "assets/fg.png",
                "w": w, "h": h, "opacity": 1.0,
            })
        states = {}
        if opts.parallax:
            # 解锁时轻微放大 + 加速，形成视差
            states["Unlock"] = {
                "#2": {"speed": 1.4, "transform.scale.x": 1.06, "transform.scale.y": 1.06},
            }
            if fg_path:
                states["Unlock"]["#3"] = {
                    "speed": 1.4, "transform.scale.x": 1.10, "transform.scale.y": 1.10,
                }
        caml = build_caml(w, h, layers, states=states, bg_color="0 0 0")
        ca_dir = os.path.join(out_root, proj + ".ca")
        if os.path.isdir(ca_dir):
            shutil.rmtree(ca_dir)
        assets = {"bg.png": bg_path}
        if fg_path:
            assets["fg.png"] = fg_path
        write_ca(ca_dir, caml, assets)
        log("已生成 %s" % ca_dir)
        result = [ca_dir]
    else:
        # ---------- 双包模式：Background.ca + Floating.ca ----------
        bundle = os.path.join(out_root, proj + ".ca")
        if os.path.isdir(bundle):
            shutil.rmtree(bundle)

        bg_caml = build_caml(w, h, [{
            "id": "#2", "name": "Background", "src": "assets/bg.png", "w": w, "h": h,
        }], states=({"Unlock": {"#2": {"speed": 1.4, "transform.scale.x": 1.04,
                                       "transform.scale.y": 1.04}}} if opts.parallax else None),
            bg_color="0 0 0")
        write_ca(os.path.join(bundle, "Background.ca"), bg_caml, {"bg.png": bg_path})

        if fg_path:
            fl_caml = build_caml(w, h, [{
                "id": "#2", "name": "Floating", "src": "assets/fg.png", "w": w, "h": h,
            }], states=({"Unlock": {"#2": {"speed": 1.4, "transform.scale.x": 1.12,
                                           "transform.scale.y": 1.12}}} if opts.parallax else None))
            write_ca(os.path.join(bundle, "Floating.ca"), fl_caml, {"fg.png": fg_path})

        log("已生成 %s" % bundle)
        result = [bundle]

    # ---------- .tendies ----------
    if opts.tendies:
        import plistlib
        td = os.path.join(out_root, "_tendies")
        if os.path.isdir(td):
            shutil.rmtree(td)
        dev_str = "%dw-%dh@%dx~iphone" % (w, h, scale)
        wn      = "7400.WWDC_2022-" + dev_str + ".wallpaper"
        bg_ca   = "7400.WWDC_2022_Background-" + dev_str + ".ca"
        fl_ca   = "7400.WWDC_2022_Floating-" + dev_str + ".ca"

        # 1) 铺官方骨架（providerInfo 等元数据）
        skel = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tpl_skeleton")
        desc_skel = os.path.join(skel, "descriptors", DEFAULT_DESC_DIR)
        if os.path.isdir(desc_skel):
            copy_tree(desc_skel, os.path.join(td, "descriptors", DEFAULT_DESC_DIR))
            # 骨架里的 wallpaper 目录名是固定的，改成本次设备
            skel_wp = os.path.join(td, "descriptors", DEFAULT_DESC_DIR, "versions", "1",
                                   "contents", "7400.WWDC_2022-390w-844h@3x~iphone.wallpaper")
            p2 = os.path.join(td, "descriptors", DEFAULT_DESC_DIR, "versions", "1",
                              "contents", wn)
            if os.path.isdir(skel_wp) and skel_wp != p2:
                os.rename(skel_wp, p2)
        else:
            p2 = os.path.join(td, "descriptors", DEFAULT_DESC_DIR, "versions", "1",
                              "contents", wn)
        os.makedirs(p2, exist_ok=True)

        # 2) 生成 Wallpaper.plist
        entry = {
            "name": "CAPlay",
            "type": "LayeredAnimation",
            "identifier": 7400,
        }
        if opts.single:
            entry["wallpaperAnimationFileName"] = wn
            entry["type"] = "LayeredAnimation"
            entry["backgroundAnimationFileName"] = wn
        else:
            entry["backgroundAnimationFileName"] = bg_ca
            if os.path.isdir(os.path.join(out_root, proj + ".ca", "Floating.ca")):
                entry["floatingAnimationFileNameKey"] = fl_ca
        pl = {
            "assets": {"lockAndHome": {"default": entry}},
            "family": "WWDC22",
            "logicalScreenClass": dev_str,
            "appearanceAware": False,
            "identifier": 7400,
            "version": 1,
            "name": "CAPlay",
        }
        with open(os.path.join(p2, "Wallpaper.plist"), "wb") as f:
            plistlib.dump(pl, f)

        # 3) 塞入 .ca
        if opts.single:
            copy_tree(os.path.join(out_root, proj + ".ca"),
                      os.path.join(p2, wn.replace(".wallpaper", ".ca")))
        else:
            src_b = os.path.join(out_root, proj + ".ca", "Background.ca")
            src_f = os.path.join(out_root, proj + ".ca", "Floating.ca")
            if os.path.isdir(src_b):
                copy_tree(src_b, os.path.join(p2, bg_ca))
            if os.path.isdir(src_f):
                copy_tree(src_f, os.path.join(p2, fl_ca))

        tendies_path = os.path.join(out_root, proj + ".tendies")
        zip_dir(td, tendies_path)
        shutil.rmtree(td, ignore_errors=True)
        log("已生成 %s" % tendies_path)
        result.append(tendies_path)

    for tmp in (bg_path, fg_path):
        if tmp and os.path.exists(tmp):
            os.remove(tmp)
    return result


def main():
    ap = argparse.ArgumentParser(
        description="图片 → iOS Core Animation 壁纸包 (.ca / .tendies)")
    ap.add_argument("input", help="图片文件，或 --batch 时的文件夹")
    ap.add_argument("-o", "--out", default="./ca_out", help="输出目录")
    ap.add_argument("--name", help="项目名（默认用文件名）")
    ap.add_argument("--device", default=DEFAULT_DEVICE,
                    help="设备：%s（默认 %s）" % (", ".join(DEVICES), DEFAULT_DEVICE))
    ap.add_argument("--batch", action="store_true", help="输入是文件夹，批量处理")
    ap.add_argument("--single", action="store_true", help="只出一个 .ca 包")
    ap.add_argument("--tendies", action="store_true", help="同时打包 .tendies")
    ap.add_argument("--floating", action="store_true", help="额外生成悬浮层（前景）")
    ap.add_argument("--floating-scale", type=float, default=0.82, help="悬浮层占比")
    ap.add_argument("--parallax", action="store_true", help="解锁时放大视差")

    ap.add_argument("--blur", action="store_true", help="背景高斯模糊")
    ap.add_argument("--blur-radius", type=float, default=40)
    ap.add_argument("--blur-bright", type=float, default=0.72)
    ap.add_argument("--focus", type=float, default=0.5, help="裁切焦点 0顶/1底")
    ap.add_argument("--vignette", action="store_true", help="加暗角")
    ap.add_argument("--vignette-strength", type=float, default=0.45)
    ap.add_argument("--gradient", action="store_true", help="加渐变压暗")
    ap.add_argument("--gradient-dir", default="bottom", choices=["bottom", "top"])
    ap.add_argument("--gradient-strength", type=float, default=0.55)

    ap.add_argument("--text", help="叠加一行文字")
    ap.add_argument("--text-pos", default="bottom",
                    choices=["top", "center", "bottom"])
    ap.add_argument("--text-size", type=float, default=0.05, help="字号占短边比例")
    ap.add_argument("--text-color", type=int, nargs=3, default=[255, 255, 255],
                    metavar=("R", "G", "B"))

    opts = ap.parse_args()
    os.makedirs(opts.out, exist_ok=True)

    files = []
    if opts.batch:
        if not os.path.isdir(opts.input):
            sys.exit("--batch 需要一个文件夹")
        for fn in sorted(os.listdir(opts.input)):
            if fn.lower().endswith((".jpg", ".jpeg", ".png", ".webp", ".bmp", ".heic")):
                files.append(os.path.join(opts.input, fn))
        if not files:
            sys.exit("文件夹里没有图片")
        log("批量：%d 张图" % len(files))
    else:
        files = [opts.input]

    ok = 0
    for i, f in enumerate(files, 1):
        if opts.batch:
            log("(%d/%d) %s" % (i, len(files), os.path.basename(f)))
        try:
            process_image(f, opts, opts.out, opts.device)
            ok += 1
        except Exception as e:
            print("[ca] 失败 %s: %s" % (f, e), file=sys.stderr)

    log("完成 %d/%d" % (ok, len(files)))
    log("输出目录：%s" % os.path.abspath(opts.out))


if __name__ == "__main__":
    main()
