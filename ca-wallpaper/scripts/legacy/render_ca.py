#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CAML 渲染器 —— 把 .ca 包按某个状态渲染成 PNG，用于肉眼验收。

用法：
    python3 render_ca.py <包目录或.tendies> [状态] [输出.png]
    python3 render_ca.py 枯木逢春.tendies Locked out.png
    python3 render_ca.py ./某壁纸目录                 # 三态对比图

要点：
  * Core Animation 的 y 轴朝上（geometryFlipped=0），本脚本已处理
  * 子图层 position 相对父层 bounds 左上角
  * 支持 LKState 里的 position / bounds / opacity 覆盖
"""
import os
import sys
import glob
import zipfile
import tempfile
import shutil
import xml.etree.ElementTree as ET

from PIL import Image

NS = '{http://www.apple.com/CoreAnimation/1.0}'
SCALE = 3


# ------------------------------------------------------------------ 解包
def ensure_dir(path):
    """如果是 .tendies/zip，先解压到临时目录"""
    if os.path.isdir(path):
        return path, None
    tmp = tempfile.mkdtemp(prefix='ca_')
    with zipfile.ZipFile(path) as z:
        z.extractall(tmp)
    return tmp, tmp


def find_ca_root(pkg_dir):
    """在包里找 .wallpaper 目录"""
    hits = glob.glob(os.path.join(pkg_dir, '**', '*.wallpaper'), recursive=True)
    if not hits:
        raise SystemExit('没找到 .wallpaper 目录')
    return sorted(hits, key=len)[0]


# ------------------------------------------------------------------ 解析
def parse_ca(ca_dir):
    """返回 (图层树, 状态字典)"""
    tree = ET.parse(os.path.join(ca_dir, 'main.caml')).getroot()

    states = {}
    for st in tree.iter(NS + 'LKState'):
        d = {}
        for v in st.iter(NS + 'LKStateSetValue'):
            val = v.find(NS + 'value')
            if val is None:
                continue
            try:
                num = float(val.get('value'))
            except (TypeError, ValueError):
                continue
            d.setdefault(v.get('targetId'), {})[v.get('keyPath')] = num
        states[st.get('name')] = d

    def build(el):
        node = {
            'id': el.get('id'),
            'name': el.get('name') or '',
            'bounds': [float(x) for x in (el.get('bounds') or '0 0 0 0').split()],
            'position': [float(x) for x in (el.get('position') or '0 0').split()],
            'opacity': float(el.get('opacity') or 1),
            'flipped': (el.get('geometryFlipped') or '0') == '1',
            'children': [],
        }
        cg = el.find('.//' + NS + 'CGImage')
        node['src'] = cg.get('src') if cg is not None else None
        sub = el.find(NS + 'sublayers')
        if sub is not None:
            for c in sub.findall(NS + 'CALayer'):
                node['children'].append(build(c))
        return node

    layers = []
    root_layer = tree.find(NS + 'CALayer')
    if root_layer is not None:
        layers.append(build(root_layer))
    return layers, states


def flatten(node, state_override, origin=(0.0, 0.0)):
    """把图层树展开成绝对坐标的绘制列表"""
    ov = state_override.get(node['id'], {})
    w = ov.get('bounds.size.width', node['bounds'][2])
    h = ov.get('bounds.size.height', node['bounds'][3])

    # y 轴：geometryFlipped=0 时，position 原点在左下；转换为屏幕坐标
    px = ov.get('position.x', node['position'][0])
    py = ov.get('position.y', node['position'][1])
    cx = origin[0] + px
    if node['flipped']:
        cy = origin[1] + py
    else:
        # 未翻转：父层高度 - y
        parent_h = node.get('_parent_h', 0)
        cy = origin[1] + (parent_h - py) if parent_h else origin[1] + py

    op = ov.get('opacity', node['opacity'])
    out = [(node['src'], w, h, cx, cy, op)]
    child_origin = (cx - w / 2.0, cy - h / 2.0)
    for c in node['children']:
        c['_parent_h'] = h
        out += flatten(c, state_override, child_origin)
    return out


# ------------------------------------------------------------------ 渲染
def render_ca(ca_dir, state='Locked', scale=SCALE):
    layers, states = parse_ca(ca_dir)
    ov = states.get(state) or {}

    canvas_w = canvas_h = 0
    if layers:
        canvas_w = int(round(layers[0]['bounds'][2]))
        canvas_h = int(round(layers[0]['bounds'][3]))

    items = []
    for l in layers:
        items += flatten(l, ov)

    canvas = Image.new('RGBA', (canvas_w * scale, canvas_h * scale), (0, 0, 0, 0))

    for src, w, h, cx, cy, op in items:
        if not src or op <= 0.001:
            continue
        p = os.path.join(ca_dir, src)
        if not os.path.exists(p):
            continue
        try:
            im = Image.open(p).convert('RGBA')
        except Exception:
            continue
        W = max(1, int(round(w * scale)))
        H = max(1, int(round(h * scale)))
        im = im.resize((W, H), Image.LANCZOS)
        if op < 0.999:
            im.putalpha(im.split()[3].point(lambda v: int(v * op)))
        x = int(round(cx * scale - W / 2))
        y = int(round(cy * scale - H / 2))
        # alpha_composite 要求偏移非负
        if x < 0 or y < 0:
            layer = Image.new('RGBA', canvas.size, (0, 0, 0, 0))
            layer.alpha_composite(im, (max(0, x), max(0, y)))
            canvas.alpha_composite(layer)
            layer.close()
        else:
            canvas.alpha_composite(im, (x, y))
        im.close()
    return canvas


def render_package(pkg, state):
    """渲染整个 .tendies（Background + Floating + Foreground 叠加）"""
    root, tmp = ensure_dir(pkg)
    try:
        wp = find_ca_root(root)
        cas = [d for d in sorted(glob.glob(os.path.join(wp, '*.ca'))) if os.path.isdir(d)]
        if not cas:
            raise SystemExit('包里没有 .ca')

        base = render_ca(cas[0], state) if any('Background' in c for c in cas) else None
        if base is None:
            base = Image.new('RGBA', (390 * SCALE, 844 * SCALE), (0, 0, 0, 0))

        for ca in cas:
            if any('Background' in ca for c in [ca]) and ca == cas[0]:
                continue
            layer = render_ca(ca, state)
            base.alpha_composite(layer)
            layer.close()
        return base
    finally:
        if tmp:
            shutil.rmtree(tmp, ignore_errors=True)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    pkg = sys.argv[1]
    state = sys.argv[2] if len(sys.argv) > 2 else None
    out = sys.argv[3] if len(sys.argv) > 3 else 'preview.png'

    if state:
        img = render_package(pkg, state)
        img.convert('RGB').save(out)
        print('已保存 %s  %s' % (out, img.size))
    else:
        # 三态对比
        imgs = []
        for st in ('Locked', 'Unlock', 'Sleep'):
            c = Image.new('RGBA', (390 * SCALE, 844 * SCALE), (20, 20, 24, 255))
            c.alpha_composite(render_package(pkg, st))
            imgs.append(c.convert('RGB'))
        gap = 20
        W = sum(i.width for i in imgs) + gap * 2
        comb = Image.new('RGB', (W, imgs[0].height), (25, 25, 30))
        x = 0
        for i in imgs:
            comb.paste(i, (x, 0))
            x += i.width + gap
        comb = comb.resize((comb.width // 3, comb.height // 3))
        comb.save(out)
        print('已保存三态对比 %s  %s' % (out, comb.size))


if __name__ == '__main__':
    main()
