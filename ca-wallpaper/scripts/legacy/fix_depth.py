#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
景深修复器
参照「李诗雅修复景深.tendies」的做法，给缺景深的 .tendies 补上：
  1) CAML 状态里缺失的 position.x / position.y / bounds.size.width / bounds.size.height
     （分层位移 + 缩放 = 视差 = 景深）
  2) Wallpaper.plist 的景深开关字段
"""
import os, re, sys, shutil, zipfile, plistlib

NS = 'http://www.apple.com/CoreAnimation/1.0'


def fmt(v):
    if isinstance(v, float):
        if v.is_integer():
            return str(int(v))
        return ("%.4f" % v).rstrip('0').rstrip('.')
    return str(v)


def read_base(caml_path):
    """读每个图层的 base bounds/position"""
    import xml.etree.ElementTree as ET
    NSx = '{' + NS + '}'
    base = {}
    for el in ET.parse(caml_path).getroot().iter(NSx + 'CALayer'):
        lid = el.get('id')
        if not lid:
            continue
        b = (el.get('bounds') or '0 0 0 0').split()
        p = (el.get('position') or '0 0').split()
        try:
            base[lid] = (float(b[2]), float(b[3]), float(p[0]), float(p[1]))
        except Exception:
            pass
    return base


PLAN = {
    # 状态 -> 缩放系数, 纵向位移(点), 横向系数
    'Locked': (1.000, 0.0, 1.000),
    'Unlock': (1.085, -18.0, 1.000),
    'Sleep': (0.975, 9.0, 1.000),
}


def patch_caml(path, depth_scale=1.0):
    """给每个 LKState 补 position / bounds 值"""
    base = read_base(path)
    s = open(path, encoding='utf-8').read()

    for state, (k, dy, kx) in PLAN.items():
        pat = re.compile(
            r'(<LKState name="%s">\s*<elements>)(.*?)(</elements>)' % state, re.S)
        m = pat.search(s)
        if not m:
            continue
        body = m.group(2)
        ids = list(dict.fromkeys(re.findall(r'targetId="([^"]+)"', body)))
        if not ids:
            continue

        blocks = []
        for tid in ids:
            if tid not in base:
                continue
            w, h, cx, cy = base[tid]
            # 越靠前的层动得越多：用图层高度做近似（大层=远景）
            nw, nh = w * k, h * k
            ny = cy + dy * depth_scale
            for key, val in (('position.x', float(cx * kx)),
                             ('position.y', float(ny)),
                             ('bounds.size.width', float(nw)),
                             ('bounds.size.height', float(nh))):
                blocks.append(
                    '          <LKStateSetValue targetId="%s" keyPath="%s">\n'
                    '            <value type="real" value="%s"/>\n'
                    '          </LKStateSetValue>' % (tid, key, fmt(val)))

        newbody = body.rstrip() + '\n' + '\n'.join(blocks) + '\n        '
        s = s[:m.start(2)] + newbody + s[m.end(2):]

    open(path, 'w', encoding='utf-8').write(s)
    return len(base)


def patch_plist(path):
    d = plistlib.load(open(path, 'rb'))
    d['contentVersion'] = 1.01
    d['disableAdaptiveTime'] = True
    d['maximumAdaptiveTimeMultiplier'] = 2.0
    d['family'] = 'Clownfish'
    plistlib.dump(d, open(path, 'wb'))
    return d


def rename_family(out_dir, old='WWDC_2022', new='Clownfish'):
    """把目录名/文件名里的旧 family 前缀换掉，并同步 Wallpaper.plist 引用"""
    renamed = 0
    for root, dirs, files in os.walk(out_dir, topdown=False):
        for d in dirs:
            if old in d:
                src = os.path.join(root, d)
                dst = os.path.join(root, d.replace(old, new))
                os.rename(src, dst)
                renamed += 1
    # 同步 plist 内的文件名字段
    for root, _d, files in os.walk(out_dir):
        if 'Wallpaper.plist' in files:
            p = os.path.join(root, 'Wallpaper.plist')
            d = plistlib.load(open(p, 'rb'))
            d['family'] = new

            def walk_fix(o):
                if isinstance(o, dict):
                    return {k: walk_fix(v) for k, v in o.items()}
                if isinstance(o, list):
                    return [walk_fix(v) for v in o]
                if isinstance(o, str) and old in o:
                    return o.replace(old, new)
                return o

            d = walk_fix(d)
            plistlib.dump(d, open(p, 'wb'))
    return renamed


def write_rendering_config(out_dir):
    """关键：PRPosterRenderingConfiguration，depthEffectDisabled=false 才是景深开关"""
    objs = [
        "$null",
        {"$class": plistlib.UID(2), "depthEffectDisabled": False,
         "motionEffectsDisabled": False},
        {"$classes": ["PRPosterRenderingConfiguration", "NSObject"],
         "$classname": "PRPosterRenderingConfiguration"},
    ]
    data = {"$archiver": "NSKeyedArchiver", "$objects": objs,
            "$top": {"root": plistlib.UID(1)}, "$version": 100000}

    n = 0
    for root, _d, files in os.walk(out_dir):
        # 只在 versions/N 目录下写
        if os.path.basename(root) == '1' and os.path.basename(os.path.dirname(root)) == 'versions':
            p = os.path.join(root, 'com.apple.posterkit.provider.instance.renderingConfiguration.plist')
            with open(p, 'wb') as f:
                plistlib.dump(data, f, fmt=plistlib.FMT_BINARY)
            n += 1
    return n


JUNK_NAMES = {'.DS_Store', '.AppleDouble', 'LICENSE.txt', 'NOTICE.txt',
              'STATEMENT.json', 'Thumbs.db'}
JUNK_PREFIX = ('._', 'LICENSE', 'README', 'NOTICE')


def is_junk(rel_path, fn):
    if fn in JUNK_NAMES or fn.startswith('._'):
        return True
    # descriptors 根目录只允许 UUID 目录
    parts = rel_path.replace(os.sep, '/').split('/')
    if len(parts) == 2 and parts[0] == 'descriptors' and fn.lower() in (
            'license.txt', 'notice.txt', 'statement.json'):
        return True
    return False


def copy_tree(src, dst):
    """复制并剔除 macOS 垃圾文件 / 版权声明"""
    os.makedirs(dst, exist_ok=True)
    dropped = []
    for root, _d, files in os.walk(src):
        rel = os.path.relpath(root, src)
        t = dst if rel == '.' else os.path.join(dst, rel)
        os.makedirs(t, exist_ok=True)
        for fn in files:
            if is_junk(rel, fn):
                dropped.append(os.path.join(rel, fn))
                continue
            with open(os.path.join(root, fn), 'rb') as f:
                data = f.read()
            with open(os.path.join(t, fn), 'wb') as f:
                f.write(data)
    if dropped:
        print('   剔除垃圾文件 %d 个：%s' % (len(dropped), ', '.join(sorted(set(
            os.path.basename(x) for x in dropped)))))


def main():
    src_pkg = sys.argv[1]
    out_dir = sys.argv[2]
    name = sys.argv[3] if len(sys.argv) > 3 else 'depth-fixed'
    skip_caml = '--no-caml' in sys.argv

    if os.path.isdir(out_dir):
        shutil.rmtree(out_dir)
    copy_tree(src_pkg, out_dir)
    print('[1/4] 复制完成')

    if skip_caml:
        print('[2/4] 跳过 CAML 视差（最小修复模式）')
    else:
        cas = []
        for root, _d, files in os.walk(out_dir):
            if 'main.caml' in files:
                cas.append(os.path.join(root, 'main.caml'))
        for p in cas:
            n = patch_caml(p)
            print('   修复 %-52s (%d 层)' % (os.path.basename(os.path.dirname(p))[-52:], n))
        print('[2/4] CAML 已补 position/bounds 视差')

    n = write_rendering_config(out_dir)
    print('[3/4] 写入 renderingConfiguration（depthEffectDisabled=false）× %d' % n)

    n_ren = rename_family(out_dir)
    print('[3.5] 家族名 WWDC_2022 → Clownfish，重命名 %d 个目录' % n_ren)

    wp = None
    for root, _d, files in os.walk(out_dir):
        if 'Wallpaper.plist' in files:
            wp = os.path.join(root, 'Wallpaper.plist')
    if wp:
        d = patch_plist(wp)
        print('   Wallpaper.plist: contentVersion=%s disableAdaptiveTime=%s family=%s'
              % (d.get('contentVersion'), d.get('disableAdaptiveTime'), d.get('family')))

    zp = os.path.join(os.path.dirname(os.path.abspath(out_dir)), name + '.tendies')
    with zipfile.ZipFile(zp, 'w', zipfile.ZIP_DEFLATED) as z:
        for root, _d, files in os.walk(out_dir):
            for fn in files:
                full = os.path.join(root, fn)
                z.write(full, os.path.relpath(full, out_dir))
    print('[4/4] 完成：%s (%.1f MB)' % (zp, os.path.getsize(zp) / 1048576))


if __name__ == '__main__':
    main()
