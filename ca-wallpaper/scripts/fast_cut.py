#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""numpy 向量化抠图：去白底 + 只保留与中心连通的主体（剔除文字）"""
import numpy as np
from PIL import Image, ImageFilter


def white_mask(arr, thr=228, sat=24):
    r = arr[:, :, 0].astype(np.int16)
    g = arr[:, :, 1].astype(np.int16)
    b = arr[:, :, 2].astype(np.int16)
    mx = np.maximum(np.maximum(r, g), b)
    mn = np.minimum(np.minimum(r, g), b)
    return (r > thr) & (g > thr) & (b > thr) & ((mx - mn) < sat)


def propagate(mask, seed, max_iter=5000):
    cur = seed & mask
    for _ in range(max_iter):
        nxt = cur.copy()
        nxt[1:, :] |= cur[:-1, :]
        nxt[:-1, :] |= cur[1:, :]
        nxt[:, 1:] |= cur[:, :-1]
        nxt[:, :-1] |= cur[:, 1:]
        nxt &= mask
        if np.array_equal(nxt, cur):
            break
        cur = nxt
    return cur


def border_connected(white, max_iter=5000):
    seed = np.zeros_like(white, dtype=bool)
    seed[0, :] = seed[-1, :] = True
    seed[:, 0] = seed[:, -1] = True
    return propagate(white, seed, max_iter)


def cutout(path, work=760, thr=228, sat=24, keep_subject=True, feather=1.0, crop=None):
    """
    1) 白底 → 透明（只去与边缘连通的白色，保留角色内部白色）
    2) keep_subject: 只保留与图像中心连通的主体，剔除飘在边上的文字
    """
    im = Image.open(path).convert("RGB")
    if crop:
        W0, H0 = im.size
        im = im.crop((0, int(H0 * crop[0]), W0, int(H0 * crop[1])))
    W, H = im.size
    small = im.resize((work, work), Image.LANCZOS)
    a = np.array(small)

    wm = white_mask(a, thr, sat)
    outside = border_connected(wm)
    solid = ~outside                     # 非白 = 角色 + 文字 + 装饰
    if keep_subject:
        h = w = work
        seed = np.zeros_like(solid, dtype=bool)
        cy0, cy1 = int(h * 0.42), int(h * 0.62)
        cx0, cx1 = int(w * 0.42), int(w * 0.58)
        seed[cy0:cy1, cx0:cx1] = True
        solid = propagate(solid, seed)

    alpha_small = np.where(solid, 255, 0).astype(np.uint8)
    mask = Image.fromarray(alpha_small, "L").resize((W, H), Image.LANCZOS)
    if feather:
        mask = mask.filter(ImageFilter.GaussianBlur(feather))

    rgba = im.convert("RGBA")
    rgba.putalpha(mask)
    bb = rgba.getbbox()
    return rgba.crop(bb) if bb else rgba
