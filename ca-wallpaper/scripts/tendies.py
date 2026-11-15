#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tendies.py —— iOS 锁屏 Core Animation 壁纸（.tendies）一站式工具
Single-file CLI for iOS lock-screen CA wallpapers.  Needs: Python>=3.8, Pillow.  No numpy.

子命令 / subcommands
  inspect  <pkg>                      体检：格式、结构、图层复杂度、配置、可疑点
  diff     <good> <bad>               对比两个包（找出"能用"和"不能用"的差别）
  render   <pkg> [--layer L] [--state S] -o out.png [--bg '#hex']
                                      忠实渲染（y 轴朝上、旋转/缩放/锚点/状态覆盖都支持）
  flatten  <pkg> -o subject.png [--layer Floating] [--state auto]
                                      把某一层"可见部分"压平成一张全屏透明 PNG（景深主体）
  graft    --template GOOD --source SRC -o out.tendies [选项]
                                      景深修复主流程：用能出景深的包当骨架，换入压平后的主体
  validate <pkg>                      交付前自检（引用是否悬空、plist 是否对得上…）
  pack     <dir> -o out.tendies       安全打包（剔除垃圾文件）

pkg 可以是 .tendies（zip）也可以是已解压的目录。
"""
import argparse
import collections
import glob
import math
import os
import re
import shutil
import sys
import tempfile
import zipfile
import plistlib
import xml.etree.ElementTree as ET

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    sys.exit('需要 Pillow：pip install pillow  (Alpine: apk add py3-pillow)')

NS = '{http://www.apple.com/CoreAnimation/1.0}'
ROLES = ('Background', 'Floating', 'Foreground')
JUNK_NAMES = {'.DS_Store', 'Thumbs.db', '.AppleDouble'}
JUNK_ROOT = {'license.txt', 'notice.txt', 'statement.json', 'readme.md'}
KNOWN_MAGIC = {
    b'WALLIVE3': 'Wallive 私有加密容器（不是 zip，无密钥无法解开，请让来源方用原 App 重新导出标准 .tendies）',
    b'Rar!': 'RAR 压缩包（不是 zip）',
    b'7z\xbc\xaf': '7z 压缩包（不是 zip）',
}


# ───────────────────────────────────────────────────────── 通用 I/O（不用 shutil.copy2，兼容受限文件系统）
def read_bytes(p):
    with open(p, 'rb') as f:
        return f.read()


def write_bytes(p, data):
    os.makedirs(os.path.dirname(p) or '.', exist_ok=True)
    with open(p, 'wb') as f:
        f.write(data)


def read_text(p):
    with open(p, encoding='utf-8') as f:
        return f.read()


def write_text(p, s):
    write_bytes(p, s.encode('utf-8'))


def copy_tree(src, dst, skip_junk=True):
    for root, _d, files in os.walk(src):
        rel = os.path.relpath(root, src)
        for fn in files:
            if skip_junk and fn in JUNK_NAMES:
                continue
            t = os.path.join(dst, '' if rel == '.' else rel, fn)
            write_bytes(t, read_bytes(os.path.join(root, fn)))


class Pkg:
    """打开 .tendies 或目录；with 语句结束自动清理临时目录。"""

    def __init__(self, path):
        self.path, self.tmp = path, None
        if os.path.isdir(path):
            self.root = path
        else:
            head = read_bytes(path)[:16]
            if head[:2] != b'PK':
                for magic, desc in KNOWN_MAGIC.items():
                    if head.startswith(magic):
                        raise SystemExit('✗ %s' % desc)
                raise SystemExit('✗ 不是 zip（文件头 %r）。.tendies 必须以 PK 开头。' % head[:9])
            self.tmp = tempfile.mkdtemp(prefix='tendies_')
            with zipfile.ZipFile(path) as z:
                for info in z.infolist():
                    if info.filename.endswith('/'):
                        continue
                    write_bytes(os.path.join(self.tmp, info.filename), z.read(info))
            self.root = self.tmp
        if not os.path.isdir(os.path.join(self.root, 'descriptors')):
            subs = [d for d in glob.glob(os.path.join(self.root, '*')) if os.path.isdir(d)]
            if len(subs) == 1 and os.path.isdir(os.path.join(subs[0], 'descriptors')):
                self.root = subs[0]

    def __enter__(self):
        return self

    def __exit__(self, *a):
        if self.tmp:
            shutil.rmtree(self.tmp, ignore_errors=True)

    # --- 定位
    def wallpaper_dir(self):
        hits = glob.glob(os.path.join(self.root, 'descriptors', '*', 'versions', '*', 'contents', '*.wallpaper'))
        if not hits:
            raise SystemExit('✗ 找不到 *.wallpaper 目录（结构不是标准 .tendies）')
        return sorted(hits)[0]

    def ca_dirs(self):
        wp = self.wallpaper_dir()
        out = {}
        for d in sorted(glob.glob(os.path.join(wp, '*.ca'))):
            for r in ROLES:
                if r.lower() in os.path.basename(d).lower():
                    out[r] = d
        return out

    def wallpaper_plist(self):
        return plistlib.loads(read_bytes(os.path.join(self.wallpaper_dir(), 'Wallpaper.plist')))


# ───────────────────────────────────────────────────────── 3x3 仿射矩阵（纯 Python）
def mm(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def tr(x, y):
    return [[1, 0, x], [0, 1, y], [0, 0, 1]]


def sc(x, y):
    return [[x, 0, 0], [0, y, 0], [0, 0, 1]]


def rot(a):
    c, s = math.cos(a), math.sin(a)
    return [[c, -s, 0], [s, c, 0], [0, 0, 1]]


def inv3(m):
    a, b, c = m[0]
    d, e, f = m[1]
    g, h, i = m[2]
    det = a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)
    if abs(det) < 1e-12:
        return None
    return [[(e * i - f * h) / det, (c * h - b * i) / det, (b * f - c * e) / det],
            [(f * g - d * i) / det, (a * i - c * g) / det, (c * d - a * f) / det],
            [(d * h - e * g) / det, (b * g - a * h) / det, (a * e - b * d) / det]]


def fnum(s, default=0.0):
    try:
        return float(s)
    except (TypeError, ValueError):
        return default


# ───────────────────────────────────────────────────────── CAML 场景 / 渲染器
def pick_state(root_layer, wanted):
    """返回 (状态名, {targetId:{keyPath:value}})。wanted='auto' 优先 'Locked Light' > 'Locked' > 以 Locked 开头。"""
    st = root_layer.find(NS + 'states')
    states = {}
    if st is not None:
        for s in st.findall(NS + 'LKState'):
            d = {}
            for v in s.iter(NS + 'LKStateSetValue'):
                val = v.find(NS + 'value')
                if val is not None and val.get('value') is not None:
                    n = fnum(val.get('value'), None)
                    if n is not None:
                        d.setdefault(v.get('targetId'), {})[v.get('keyPath')] = n
            states[s.get('name')] = d
    if not states or wanted in (None, 'none'):
        return None, {}
    names = list(states)
    if wanted == 'auto':
        for cand in ('Locked Light', 'Locked'):
            if cand in states:
                return cand, states[cand]
        for n in names:
            if n.lower().startswith('locked'):
                return n, states[n]
        return names[0], states[names[0]]
    if wanted in states:
        return wanted, states[wanted]
    for n in names:
        if n.lower() == wanted.lower() or n.lower().startswith(wanted.lower()):
            return n, states[n]
    raise SystemExit('✗ 没有状态 %r，可选: %s' % (wanted, ', '.join(names)))


class Scene:
    def __init__(self, ca_dir, state='auto', scale=3):
        self.dir, self.scale = ca_dir, scale
        self.tree = ET.parse(os.path.join(ca_dir, 'main.caml')).getroot()
        self.root = self.tree.find(NS + 'CALayer')
        self.state_name, self.ov = pick_state(self.root, state)
        b = (self.root.get('bounds') or '0 0 390 844').split()
        self.W, self.H = fnum(b[2], 390), fnum(b[3], 844)
        self.items = []
        self._walk(self.root, tr(0, 0), 1.0, 0)

    def _walk(self, el, M_parent_child_space, op, depth=0):
        ov = self.ov.get(el.get('id'), {})
        if el.get('hidden') == '1':
            return
        o = ov.get('opacity', fnum(el.get('opacity'), 1.0)) * op
        if o <= 0.001:
            return
        b = (el.get('bounds') or '0 0 0 0').split()
        bw = ov.get('bounds.size.width', fnum(b[2]))
        bh = ov.get('bounds.size.height', fnum(b[3]))
        p = (el.get('position') or '0 0').split()
        px, py = ov.get('position.x', fnum(p[0])), ov.get('position.y', fnum(p[1]))
        a = (el.get('anchorPoint') or '0.5 0.5').split()
        ax, ay = fnum(a[0], .5), fnum(a[1], .5)
        ang = ov.get('transform.rotation.z', fnum(el.get('transform.rotation.z'), 0.0))
        sm = re.search(r'scale\(\s*([-\d.eE+]+)\s*,\s*([-\d.eE+]+)', el.get('transform') or '')
        sx, sy = (fnum(sm.group(1), 1), fnum(sm.group(2), 1)) if sm else (1.0, 1.0)
        if 'transform.scale' in ov:
            sx = sy = ov['transform.scale']
        T = mm(mm(mm(tr(px, py), rot(ang)), sc(sx, sy)), tr(-ax * bw, -ay * bh))
        M_up = mm(M_parent_child_space, T)           # 本层 y-up 局部坐标 → 画布 y-up
        flipped = el.get('geometryFlipped') == '1'
        F = [[1, 0, 0], [0, -1, bh], [0, 0, 1]] if flipped else tr(0, 0)
        cg = el.find(NS + 'contents/' + NS + 'CGImage')
        if cg is not None and cg.get('src'):
            self.items.append({'id': el.get('id'), 'name': el.get('name'), 'src': cg.get('src'),
                               'M': M_up, 'bw': bw, 'bh': bh, 'op': o, 'depth': depth})
        sub = el.find(NS + 'sublayers')
        if sub is not None:
            Mc = mm(M_up, F)                         # 子层坐标空间 → 画布 y-up
            for c in sub.findall(NS + 'CALayer'):
                self._walk(c, Mc, o, depth + 1)

    def render(self, exclude=None, only=None, bg=None):
        S = self.scale
        cw, ch = int(round(self.W * S)), int(round(self.H * S))
        canvas = Image.new('RGBA', (cw, ch), bg or (0, 0, 0, 0))
        cache = {}
        toscreen = mm(sc(S, S), [[1, 0, 0], [0, -1, self.H], [0, 0, 1]])   # y-up 点 → y-down 像素
        drawn = []
        for it in self.items:
            key = '%s %s %s' % (it['id'], it['name'], it['src'])
            if exclude and re.search(exclude, key):
                continue
            if only and not re.search(only, key):
                continue
            path = os.path.join(self.dir, it['src'])
            if not os.path.exists(path):
                continue
            if path not in cache:
                cache[path] = Image.open(path).convert('RGBA')
            im = cache[path]
            iw, ih = im.size
            Iup = [[it['bw'] / iw, 0, 0], [0, -it['bh'] / ih, it['bh']], [0, 0, 1]]
            P = mm(toscreen, mm(it['M'], Iup))       # 图片像素 → 画布像素
            inv = inv3(P)
            if inv is None:
                continue
            xs, ys = [], []
            for u, v in ((0, 0), (iw, 0), (0, ih), (iw, ih)):
                xs.append(P[0][0] * u + P[0][1] * v + P[0][2])
                ys.append(P[1][0] * u + P[1][1] * v + P[1][2])
            x0, y0 = max(0, int(math.floor(min(xs)))), max(0, int(math.floor(min(ys))))
            x1, y1 = min(cw, int(math.ceil(max(xs)))), min(ch, int(math.ceil(max(ys))))
            if x1 <= x0 or y1 <= y0:
                continue
            coef = (inv[0][0], inv[0][1], inv[0][0] * x0 + inv[0][1] * y0 + inv[0][2],
                    inv[1][0], inv[1][1], inv[1][0] * x0 + inv[1][1] * y0 + inv[1][2])
            src = im
            if it['op'] < 0.999:
                src = im.copy()
                src.putalpha(im.getchannel('A').point(lambda v, o=it['op']: int(v * o)))
            out = src.transform((x1 - x0, y1 - y0), Image.AFFINE, coef, resample=Image.BICUBIC)
            canvas.alpha_composite(out, (x0, y0))
            drawn.append(it)
        return canvas, drawn


def parse_color(s):
    s = s.lstrip('#')
    if len(s) == 3:
        s = ''.join(c * 2 for c in s)
    return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4)) + (255,)


# ───────────────────────────────────────────────────────── 子命令：render / flatten
def cmd_render(a):
    with Pkg(a.pkg) as p:
        cas = p.ca_dirs()
        layers = ROLES if a.layer == 'all' else (a.layer,)
        base = None
        for r in layers:
            if r not in cas:
                continue
            sc_ = Scene(cas[r], a.state, a.scale)
            img, drawn = sc_.render(exclude=a.exclude)
            print('%-10s 状态=%s  绘制 %d 个图片图层' % (r, sc_.state_name, len(drawn)))
            if base is None:
                base = Image.new('RGBA', img.size, parse_color(a.bg) if a.bg else (0, 0, 0, 0))
            base.alpha_composite(img)
        if base is None:
            raise SystemExit('✗ 包里没有 %s 层' % a.layer)
        (base.convert('RGB') if a.bg else base).save(a.out)
        print('已保存', a.out, base.size)


def cmd_flatten(a):
    with Pkg(a.pkg) as p:
        cas = p.ca_dirs()
        if a.layer not in cas:
            raise SystemExit('✗ 没有 %s 层，可选 %s' % (a.layer, list(cas)))
        s = Scene(cas[a.layer], a.state, a.scale)
        img, drawn = s.render(exclude=a.exclude)
        if a.list:
            for it in drawn:
                print('  %-28s op=%.2f %s' % (it['id'], it['op'], it['src']))
        img.save(a.out)
        print('压平 %s 层（状态 %s）：%d 个可见图片图层 → %s %s' % (a.layer, s.state_name, len(drawn), a.out, img.size))


# ───────────────────────────────────────────────────────── 子命令：inspect
def caml_stats(path):
    t = read_text(path)
    root = ET.fromstring(t.encode('utf-8'))
    n = depth = 0

    def walk(el, d):
        nonlocal n, depth
        for c in el.findall(NS + 'sublayers/' + NS + 'CALayer'):
            n += 1
            depth = max(depth, d + 1)
            walk(c, d + 1)

    top = root.find(NS + 'CALayer')
    if top is not None:
        n += 1
        walk(top, 1)
    states = []
    st = top.find(NS + 'states') if top is not None else None
    if st is not None:
        states = [s.get('name') for s in st.findall(NS + 'LKState')]
    return {'layers': n, 'depth': depth, 'anims': t.count('<animation '), 'setvalues': t.count('<LKStateSetValue'),
            'states': states, 'root_id': top.get('id') if top is not None else None,
            'has_modules': '<modules' in t, 'has_states': '<states' in t}


def nsk_keys(path):
    try:
        d = plistlib.loads(read_bytes(path))
        o = d['$objects'][1]
        return sorted(k for k in o if not k.startswith('$')) if isinstance(o, dict) else []
    except Exception:
        return None


def cmd_inspect(a):
    path = a.pkg
    print('=' * 64)
    print('检查:', path)
    if os.path.isfile(path):
        print('大小: %.1f MB' % (os.path.getsize(path) / 1048576))
    warn = []
    with Pkg(path) as p:
        root = p.root
        desc = os.path.join(root, 'descriptors')
        entries = os.listdir(desc)
        uuids = [e for e in entries if os.path.isdir(os.path.join(desc, e))]
        junk = [e for e in entries if e not in uuids]
        print('descriptor UUID:', ', '.join(uuids))
        if junk:
            warn.append('descriptors/ 下有杂物 %s → 会导入失败，必须删除' % junk)
        ds = glob.glob(os.path.join(root, '**', '.DS_Store'), recursive=True)
        if ds:
            warn.append('发现 %d 个 .DS_Store，建议删除' % len(ds))
        wp = p.wallpaper_dir()
        d = p.wallpaper_plist()
        lh = d.get('assets', {}).get('lockAndHome', {})
        print('wallpaper 目录:', os.path.basename(wp))
        print('family=%s  appearanceAware=%s  变体=%s  contentVersion=%s' % (
            d.get('family'), d.get('appearanceAware'), '+'.join(sorted(lh)), d.get('contentVersion')))
        print('Wallpaper.plist 其他字段:', {k: d[k] for k in d if k in ('disableAdaptiveTime', 'maximumAdaptiveTimeMultiplier', 'identifier', 'logicalScreenClass')})
        if d.get('appearanceAware') and 'dark' not in lh:
            warn.append('appearanceAware=True 但没有 dark 变体')
        if not d.get('appearanceAware') and 'dark' in lh:
            warn.append('appearanceAware=False 却有 dark 变体（矛盾）')
        for v, cfg in lh.items():
            for k in ('backgroundAnimationFileName', 'floatingAnimationFileNameKey', 'foregroundAnimationFileName'):
                fn = cfg.get(k)
                if fn and not os.path.isdir(os.path.join(wp, fn)):
                    warn.append('plist 引用的 %s/%s 在包里不存在 → 会 "read length: channel closed"' % (v, fn))
        vdir = os.path.dirname(os.path.dirname(wp))
        print('\n配置文件:')
        rc = glob.glob(os.path.join(vdir, '*renderingConfiguration.plist'))
        print('  renderingConfiguration.plist:', '有 %s' % nsk_keys(rc[0]) if rc else '无')
        co = glob.glob(os.path.join(vdir, 'contents', '.com.apple.posterkit.provider.contents.configurableOptions.plist'))
        print('  configurableOptions:', '有 %s' % nsk_keys(co[0]) if co else '无')
        print('\n图层包:')
        total_vis = 0
        fl_items = []
        for r, ca in p.ca_dirs().items():
            st = caml_stats(os.path.join(ca, 'main.caml'))
            assets = len(glob.glob(os.path.join(ca, 'assets', '*')))
            try:
                sc_ = Scene(ca, 'auto', 1)
                vis = len([i for i in sc_.items])
                sname = sc_.state_name
            except Exception as e:  # noqa
                vis, sname = -1, '?'
            print('  %-10s assets=%-4d 图层=%-4d 深度=%d 动画=%-5d 状态值=%-5d 根id=%s' % (
                r, assets, st['layers'], st['depth'], st['anims'], st['setvalues'], st['root_id']))
            print('             状态=%s ｜ 锁屏态(%s)下实际可见的图片图层: %d' % (st['states'], sname, vis))
            if r == 'Floating':
                total_vis = vis
                fl_items = sc_.items
            if not st['has_states']:
                warn.append('%s 缺 <states> 块 → 导入后壁纸库会一直转圈' % r)
            if not st['has_modules'] and r != 'Foreground':
                warn.append('%s 缺 <modules> → 与能用的包不一致' % r)
            if not os.path.exists(os.path.join(ca, 'index.xml')):
                warn.append('%s 缺 index.xml' % r)
            if st['root_id'] not in (r, '__capRootLayer__', None):
                warn.append('%s 根图层 id=%r（能用的包是 %r）' % (r, st['root_id'], r))
        print('\n体检结论:')
        if fl_items:
            big = [i for i in fl_items if i['bw'] * i['bh'] >= 0.25 * 390 * 844]
            print('  Floating 可见图层 %d 个（其中"大图"≥1/4 屏的 %d 个），嵌套深度 %d–%d，面积最大的一张占屏 %.0f%%' % (
                len(fl_items), len(big), min(i['depth'] for i in fl_items), max(i['depth'] for i in fl_items),
                100 * max(i['bw'] * i['bh'] for i in fl_items) / (390 * 844)))
            print('  （数量本身不是景深的判据：能出景深的李诗雅包也有 9 个可见图层。机制未查明，见 references/depth-effect.md）')
        if not warn:
            print('  未发现明显问题（景深是否生效只能在真机上看，见 SKILL.md）')
        for w in warn:
            print('  ⚠', w)


# ───────────────────────────────────────────────────────── 子命令：diff
def cmd_diff(a):
    with Pkg(a.good) as g, Pkg(a.bad) as b:
        def files(p):
            out = {}
            for r, _d, fs in os.walk(p.root):
                for f in fs:
                    rel = os.path.relpath(os.path.join(r, f), p.root)
                    rel = re.sub(r'descriptors/[^/]+', 'descriptors/<UUID>', rel)
                    rel = re.sub(r'7400\.[A-Za-z0-9_]*?(?=-390w|_(?:Background|Floating|Foreground)-)', '7400.<FAMILY>', rel)
                    out[rel] = os.path.join(r, f)
            return out
        fg, fb = files(g), files(b)
        nonasset = lambda k: '/assets/' not in k  # noqa
        print('仅 GOOD 有（非资源）:', sorted(k for k in fg if k not in fb and nonasset(k)))
        print('仅 BAD  有（非资源）:', sorted(k for k in fb if k not in fg and nonasset(k)))
        print('\n同名但内容不同（非资源）:')
        for k in sorted(fg):
            if k in fb and nonasset(k) and read_bytes(fg[k]) != read_bytes(fb[k]):
                print('  ≠', k)
        print('\nWallpaper.plist 字段对比:')
        pg, pb = g.wallpaper_plist(), b.wallpaper_plist()
        for k in sorted(set(pg) | set(pb)):
            if pg.get(k) != pb.get(k) and k != 'assets':
                print('  %-26s GOOD=%r  BAD=%r' % (k, pg.get(k), pb.get(k)))
        print('  变体 GOOD=%s BAD=%s' % (sorted(pg['assets']['lockAndHome']), sorted(pb['assets']['lockAndHome'])))
        print('\n各层 CAML 复杂度:')
        for r in ROLES:
            cg, cb = g.ca_dirs().get(r), b.ca_dirs().get(r)
            if not (cg and cb):
                print('  %-10s GOOD=%s BAD=%s' % (r, bool(cg), bool(cb)))
                continue
            sg, sb = caml_stats(os.path.join(cg, 'main.caml')), caml_stats(os.path.join(cb, 'main.caml'))
            print('  %-10s GOOD 图层=%d 动画=%d 状态=%s' % (r, sg['layers'], sg['anims'], sg['states']))
            print('  %-10s BAD  图层=%d 动画=%d 状态=%s' % ('', sb['layers'], sb['anims'], sb['states']))


# ───────────────────────────────────────────────────────── graft（景深主流程）
COMMON = ('zPosition="0" geometryFlipped="0" masksToBounds="0" opacity="1" transform.rotation.z="0" '
          'transform.rotation.x="0" transform.rotation.y="0" '
          'transform="rotate(0deg) rotate(0deg, 0, 1, 0) rotate(0deg, 1, 0, 0)" cornerRadius="0" '
          'allowsEdgeAntialiasing="1" allowsGroupOpacity="1" contentsFormat="RGBA8" cornerCurve="circular"')


def inner_sublayers_span(t):
    """返回模板 caml 里 name="Root Layer" 那一层的 <sublayers>…</sublayers> 内部区间 (start,end)。找不到则用根层的。"""
    i = t.find('name="Root Layer"')
    s = t.find('<sublayers>', i if i >= 0 else 0)
    if s < 0:
        raise SystemExit('✗ 模板 main.caml 里没有 <sublayers>')
    depth, pos = 0, s
    for m in re.finditer(r'<sublayers>|</sublayers>', t[s:]):
        depth += 1 if m.group() == '<sublayers>' else -1
        if depth == 0:
            return s + len('<sublayers>'), s + m.start()
    raise SystemExit('✗ <sublayers> 不配对')


def clear_elements(t):
    return re.sub(r'<elements>.*?</elements>', '<elements/>', t, flags=re.S)


def image_layer_xml(lid, name, src, w=390, h=844):
    return ('<CALayer id="%s" name="%s" bounds="0 0 %s %s" position="%s %s" %s>'
            '<contents><CGImage src="%s"/></contents></CALayer>' % (lid, name, w, h, w / 2, h / 2, COMMON, src))


def swap_inner(template_caml, new_inner_xml, root_id):
    t = read_text(template_caml)
    s, e = inner_sublayers_span(t)
    t = t[:s] + '\n' + new_inner_xml + '\n' + t[e:]
    t = clear_elements(t)                      # 模板里指向旧图层的状态值必须清空，否则悬空引用
    t = re.sub(r'(<CALayer id=")[^"]*(" name="CAPlayground Root Layer")', r'\g<1>%s\2' % root_id, t, count=1)
    return t


def drop_layers(t, ids):
    """从 caml 文本里删掉指定 id 的"叶子"图层，并清除状态/过渡里对它们的引用。返回新文本。"""
    if not ids:
        return t
    alt = '|'.join(re.escape(i) for i in ids)
    t = re.sub(r'<CALayer id="(?:%s)"[^>]*>\s*<contents>.*?</contents>\s*</CALayer>\s*' % alt, '', t, flags=re.S)
    t = re.sub(r'<LKStateSetValue targetId="(?:%s)"[^>]*>.*?</LKStateSetValue>\s*' % alt, '', t, flags=re.S)
    t = re.sub(r'<LKStateTransitionElement targetId="(?:%s)"[^>]*?(?:/>|>.*?</LKStateTransitionElement>)\s*' % alt, '', t, flags=re.S)
    return t


def make_light_only(t):
    """深浅色自适应 caml → 单外观：删 Dark 状态/过渡，Light 后缀去掉。"""
    t = re.sub(r'<LKState name="[^"]* Dark">.*?</LKState>\s*', '', t, flags=re.S)
    t = re.sub(r'<LKStateTransition [^>]*Dark[^>]*>.*?</LKStateTransition>\s*', '', t, flags=re.S)
    return re.sub(r'(Locked|Unlock|Sleep) Light', r'\1', t)


def pack_dir(src, out, dir_entries=True):
    if os.path.exists(out):
        os.remove(out)
    entries = []
    for r, ds, fs in os.walk(src):
        ds.sort()
        for f in sorted(fs):
            if f in JUNK_NAMES:
                continue
            full = os.path.join(r, f)
            rel = os.path.relpath(full, src).replace(os.sep, '/')
            if rel.startswith('descriptors/') and rel.count('/') == 1 and f.lower() in JUNK_ROOT:
                continue
            entries.append((full, rel))
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        if dir_entries:
            dirs = sorted({os.path.dirname(rel) + '/' for _f, rel in entries if os.path.dirname(rel)} |
                          {d for _f, rel in entries for d in ('/'.join(rel.split('/')[:i]) + '/' for i in range(1, rel.count('/') + 1))})
            for d in dirs:
                z.writestr(d, b'')
        for full, rel in entries:
            z.write(full, rel)
    return len(entries)


def cmd_pack(a):
    n = pack_dir(a.dir, a.out)
    print('已打包 %d 个文件 → %s (%.1f MB)' % (n, a.out, os.path.getsize(a.out) / 1048576))


def default_template():
    here = os.path.dirname(os.path.abspath(__file__))
    hits = sorted(glob.glob(os.path.join(here, '..', 'templates', 'template_A_*.tendies')))
    if not hits:
        raise SystemExit('✗ 没给 --template，且找不到内置模板 templates/template_A_*.tendies')
    return os.path.normpath(hits[0])


def cmd_graft(a):
    if not a.template:
        a.template = default_template()
        print('[0] 未指定模板，使用内置模板:', os.path.basename(a.template), '（请确认用户手机上它的景深是正常的）')
    work = tempfile.mkdtemp(prefix='graft_')
    try:
        with Pkg(a.template) as T, Pkg(a.source) as S:
            copy_tree(T.root, work)
            wk = Pkg(work)
            wp = wk.wallpaper_dir()
            cas = wk.ca_dirs()
            if 'Floating' not in cas or 'Background' not in cas:
                raise SystemExit('✗ 模板必须同时有 Background 和 Floating 层')
            scas = S.ca_dirs()
            if 'Floating' not in scas:
                raise SystemExit('✗ 源包没有 Floating 层')
            # 1) 主体 PNG
            if a.subject_png:
                subject = Image.open(a.subject_png).convert('RGBA')
                baked_ids = []
                print('[1] 使用现成主体图', a.subject_png)
            else:
                scene = Scene(scas['Floating'], a.state, 3)
                subject, drawn = scene.render(exclude=a.exclude)
                baked_ids = [i['id'] for i in drawn]
                print('[1] 压平源包 Floating（状态 %s）：%d 个可见图层 → 1 张 %s' % (scene.state_name, len(drawn), subject.size))
            if subject.getbbox() is None:
                raise SystemExit('✗ 压平结果是全透明，检查 --state / --exclude')
            fl, bg = cas['Floating'], cas['Background']
            for f in glob.glob(os.path.join(fl, 'assets', '*')):
                os.remove(f)
            os.makedirs(os.path.join(fl, 'assets'), exist_ok=True)
            subject.save(os.path.join(fl, 'assets', 'tree.png' if not a.subject_name else a.subject_name))
            sname = a.subject_name or 'tree.png'
            subj_xml = image_layer_xml('subject1', sname, 'assets/' + sname)

            # 2) Floating caml
            if a.keep_layers:
                t = read_text(os.path.join(scas['Floating'], 'main.caml'))
                if not a.subject_png:
                    t = drop_layers(t, baked_ids)
                s, e = inner_sublayers_span(t)
                t = t[:s] + '\n' + subj_xml + '\n' + t[s:]
                t = re.sub(r'(<CALayer id=")[^"]*(" name="CAPlayground Root Layer")', r'\g<1>Floating\2', t, count=1)
                kept = 0
                for f in glob.glob(os.path.join(scas['Floating'], 'assets', '*')):
                    n = os.path.basename(f)
                    if ('assets/' + n) in t and n != sname:
                        write_bytes(os.path.join(fl, 'assets', n), read_bytes(f))
                        kept += 1
                print('[2] Floating：保留源包的其余图层（叶子/花瓣/动画），复制 %d 个资源' % kept)
            else:
                t = swap_inner(os.path.join(fl, 'main.caml'), subj_xml, 'Floating')
                print('[2] Floating：模板骨架 + 1 张主体图（无其它图层）')

            # 3) 外观
            pl_path = os.path.join(wp, 'Wallpaper.plist')
            pl = plistlib.loads(read_bytes(pl_path))
            lh = pl['assets']['lockAndHome']
            if a.appearance == 'light-only':
                if a.keep_layers:
                    t = make_light_only(t)
                pl['appearanceAware'] = False
                pl['assets']['lockAndHome'] = {'default': lh['default']}
            else:
                dflt = lh['default']
                dark = dict(dflt)
                dark['identifier'] = int(dflt.get('identifier', 7400)) + 1
                dark['name'] = (dflt.get('name') or 'Wallpaper') + ' Dark'
                pl['appearanceAware'] = True
                pl['assets']['lockAndHome'] = {'default': dflt, 'dark': dark}
                if not (a.keep_layers or a.background == 'source'):
                    print('    ⚠ appearance=keep 但没有带来 Light/Dark 状态（需 --keep-layers 或 --background source），深色不会有变化')
            write_text(os.path.join(fl, 'main.caml'), t)
            ET.fromstring(t.encode('utf-8'))
            pl.setdefault('contentVersion', 1.01)
            write_bytes(pl_path, plistlib.dumps(pl, fmt=plistlib.FMT_XML))
            print('[3] 外观：%s（appearanceAware=%s）' % (a.appearance, pl['appearanceAware']))

            # 4) Background
            if a.background.startswith('solid:'):
                color = parse_color(a.background[6:])
                rgb = ' '.join('%.4f' % (c / 255.0) for c in color[:3])
                for f in glob.glob(os.path.join(bg, 'assets', '*')):
                    os.remove(f)
                inner = ('<CALayer id="paperBg" name="paper" bounds="0 0 390 844" position="195 422" %s '
                         'backgroundColor="%s"/>' % (COMMON, rgb))
                write_text(os.path.join(bg, 'main.caml'), swap_inner(os.path.join(bg, 'main.caml'), inner, 'Background'))
                print('[4] Background：纯色 %s' % a.background[6:])
            elif a.background == 'source':
                if 'Background' not in scas:
                    raise SystemExit('✗ 源包没有 Background')
                for f in glob.glob(os.path.join(bg, 'assets', '*')):
                    os.remove(f)
                for f in glob.glob(os.path.join(scas['Background'], 'assets', '*')):
                    write_bytes(os.path.join(bg, 'assets', os.path.basename(f)), read_bytes(f))
                bt = read_text(os.path.join(scas['Background'], 'main.caml'))
                bt = re.sub(r'(<CALayer id=")[^"]*(" name="CAPlayground Root Layer")', r'\g<1>Background\2', bt, count=1)
                if a.appearance == 'light-only':
                    bt = make_light_only(bt)
                write_text(os.path.join(bg, 'main.caml'), bt)
                am = os.path.join(scas['Background'], 'assetManifest.caml')
                if os.path.exists(am):
                    write_bytes(os.path.join(bg, 'assetManifest.caml'), read_bytes(am))
                print('[4] Background：沿用源包（%s）' % ('含夜空/深色' if a.appearance == 'keep' else '仅浅色'))
            else:
                print('[4] Background：保持模板原样')

            n = pack_dir(work, a.out)
            print('[5] 已打包 %d 个文件 → %s (%.1f MB)' % (n, a.out, os.path.getsize(a.out) / 1048576))
        problems = validate_pkg(a.out, quiet=True)
        if problems:
            print('\n自检发现问题:')
            for x in problems:
                print('  ✗', x)
        else:
            print('\n自检通过。注意：景深是否生效必须在真机上看（锁屏时间是否被主体遮住）。')
        if a.preview:
            print('预览图:', make_previews(a.out, a.preview) or '（无）')
    finally:
        shutil.rmtree(work, ignore_errors=True)


def make_previews(pkg, prefix):
    """按每种外观渲染"锁屏态"预览（不含时钟，仅壁纸三层叠加）。返回生成的文件列表。"""
    made = []
    with Pkg(pkg) as p:
        cas = p.ca_dirs()
        probe = pick_state(ET.parse(os.path.join(cas['Floating'], 'main.caml')).getroot().find(NS + 'CALayer'), 'auto')[0]
        looks = [('Light', 'Locked Light', '#f7f4ec'), ('Dark', 'Locked Dark', '#0b1020')] if probe and 'Light' in probe else [('', 'auto', '#f7f4ec')]
        for tag, st, color in looks:
            base = None
            for r in ROLES:
                if r not in cas:
                    continue
                try:
                    sc_ = Scene(cas[r], st, 2)
                except SystemExit:
                    sc_ = Scene(cas[r], 'auto', 2)
                img, _ = sc_.render()
                if base is None:
                    base = Image.new('RGBA', img.size, parse_color(color))
                base.alpha_composite(img)
            out = prefix.replace('.png', ('_%s.png' % tag) if tag else '.png')
            base.convert('RGB').save(out)
            made.append(out)
    return made


# ───────────────────────────────────────────────────────── validate
def validate_pkg(path, quiet=False):
    errs = []
    try:
        with Pkg(path) as p:
            desc = os.path.join(p.root, 'descriptors')
            for e in os.listdir(desc):
                if not os.path.isdir(os.path.join(desc, e)):
                    errs.append('descriptors/ 下有非目录文件 %s' % e)
            if glob.glob(os.path.join(p.root, '**', '.DS_Store'), recursive=True):
                errs.append('包里有 .DS_Store')
            wp = p.wallpaper_dir()
            pl = p.wallpaper_plist()
            lh = pl.get('assets', {}).get('lockAndHome', {})
            if 'default' not in lh:
                errs.append('Wallpaper.plist 缺 default 变体')
            if pl.get('appearanceAware') and 'dark' not in lh:
                errs.append('appearanceAware=True 但缺 dark 变体')
            for v, cfg in lh.items():
                for k in ('backgroundAnimationFileName', 'floatingAnimationFileNameKey', 'foregroundAnimationFileName'):
                    fn = cfg.get(k)
                    if fn and not os.path.isdir(os.path.join(wp, fn)):
                        errs.append('plist(%s) 引用的 %s 不存在' % (v, fn))
            for r, ca in p.ca_dirs().items():
                cp = os.path.join(ca, 'main.caml')
                try:
                    t = read_text(cp)
                    root = ET.fromstring(t.encode('utf-8'))
                except Exception as e:
                    errs.append('%s main.caml 解析失败: %s' % (r, e))
                    continue
                ids = {el.get('id') for el in root.iter(NS + 'CALayer')}
                for cg in root.iter(NS + 'CGImage'):
                    if not os.path.exists(os.path.join(ca, cg.get('src') or '')):
                        errs.append('%s 引用的图片不存在: %s' % (r, cg.get('src')))
                        break
                dang = {e.get('targetId') for e in list(root.iter(NS + 'LKStateSetValue')) + list(root.iter(NS + 'LKStateTransitionElement'))
                        if e.get('targetId') not in ids}
                if dang:
                    errs.append('%s 状态里有 %d 个悬空 targetId（指向不存在的图层）: %s' % (r, len(dang), sorted(dang)[:3]))
                top = root.find(NS + 'CALayer')
                if top is None or top.find(NS + 'states') is None:
                    errs.append('%s 缺 <states>（会导致壁纸库一直转圈）' % r)
                if not os.path.exists(os.path.join(ca, 'index.xml')):
                    errs.append('%s 缺 index.xml' % r)
    except SystemExit as e:
        errs.append(str(e))
    return errs


def cmd_validate(a):
    errs = validate_pkg(a.pkg)
    if errs:
        for e in errs:
            print('✗', e)
        sys.exit(1)
    print('✓ 自检通过（结构层面）。景深/动画是否生效仍需真机验证。')


# ───────────────────────────────────────────────────────── main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)

    p = sub.add_parser('inspect'); p.add_argument('pkg'); p.set_defaults(f=cmd_inspect)
    p = sub.add_parser('diff'); p.add_argument('good'); p.add_argument('bad'); p.set_defaults(f=cmd_diff)
    p = sub.add_parser('validate'); p.add_argument('pkg'); p.set_defaults(f=cmd_validate)
    p = sub.add_parser('pack'); p.add_argument('dir'); p.add_argument('-o', '--out', required=True); p.set_defaults(f=cmd_pack)

    p = sub.add_parser('render'); p.add_argument('pkg')
    p.add_argument('--layer', default='all', choices=('all',) + ROLES)
    p.add_argument('--state', default='auto', help="状态名；auto=Locked Light/Locked；none=不应用状态")
    p.add_argument('--bg', help="背景色 #rrggbb（不给则透明）")
    p.add_argument('--exclude', help='按 id/name/src 正则排除图层')
    p.add_argument('--scale', type=int, default=3)
    p.add_argument('-o', '--out', default='render.png'); p.set_defaults(f=cmd_render)

    p = sub.add_parser('flatten'); p.add_argument('pkg')
    p.add_argument('--layer', default='Floating', choices=ROLES)
    p.add_argument('--state', default='auto'); p.add_argument('--exclude'); p.add_argument('--scale', type=int, default=3)
    p.add_argument('--list', action='store_true', help='列出被压进去的图层')
    p.add_argument('-o', '--out', required=True); p.set_defaults(f=cmd_flatten)

    p = sub.add_parser('graft', help='景深修复主流程')
    p.add_argument('--template', help='确认能出景深的包（骨架，配置一字不改）。省略则用内置 templates/template_A_*.tendies')
    p.add_argument('--source', required=True, help='要修复的包（提供画面/叶子/夜空）')
    p.add_argument('-o', '--out', required=True)
    p.add_argument('--state', default='auto', help='压平时使用的源包状态（默认锁屏态）')
    p.add_argument('--exclude', help='压平时排除图层的正则')
    p.add_argument('--subject-png', help='直接用现成的全屏透明 PNG 作主体（跳过压平）')
    p.add_argument('--subject-name', help='主体图在 assets 里的文件名（默认 tree.png）')
    p.add_argument('--keep-layers', action='store_true', help='保留源包 Floating 里其余图层（叶子/花瓣/动画），只把"可见部分"压平')
    p.add_argument('--background', default='solid:#f7f4ec', help="solid:#hex | source | template")
    p.add_argument('--appearance', default='light-only', choices=('light-only', 'keep'),
                   help='light-only=单外观(景深已验证)；keep=深浅色自适应(景深未验证！)')
    p.add_argument('--preview', help='输出预览图前缀，如 /tmp/pv.png')
    p.set_defaults(f=cmd_graft)

    a = ap.parse_args()
    a.f(a)


if __name__ == '__main__':
    main()
