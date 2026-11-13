# -*- coding: utf-8 -*-
"""由品牌图「采购合同下单系统.png」生成多尺寸图标（ICO / 网页 favicon / 预览图）

图标源图放在项目根目录，替换这张 PNG 后重新运行本脚本即可换图标。
纯标准库实现，不依赖 Pillow。
"""
import os
import struct
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_PNG = os.path.join(ROOT, '采购合同下单系统.png')
OUT_ICO = os.path.join(ROOT, '采购合同下单系统.ico')
OUT_FAVICON = os.path.join(ROOT, 'web', 'favicon.ico')
OUT_PREVIEW = os.path.join(ROOT, '工具', '_icon_preview.png')

SIZES = (16, 24, 32, 48, 64, 128, 256)


# ---------------------------------------------------------------- PNG 解码
def read_png(path):
    """读取 8 位非隔行 PNG，返回 (宽, 高, RGBA 字节串)"""
    data = open(path, 'rb').read()
    if data[:8] != b'\x89PNG\r\n\x1a\n':
        raise ValueError('不是 PNG 文件: %s' % path)

    pos = 8
    idat = b''
    plte = None
    trns = None
    w = h = depth = ctype = interlace = 0
    while pos < len(data):
        length = struct.unpack('>I', data[pos:pos + 4])[0]
        tag = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + length]
        if tag == b'IHDR':
            w, h, depth, ctype, _cm, _fm, interlace = struct.unpack('>IIBBBBB', body)
        elif tag == b'IDAT':
            idat += body
        elif tag == b'PLTE':
            plte = body
        elif tag == b'tRNS':
            trns = body
        elif tag == b'IEND':
            break
        pos += 12 + length

    if interlace != 0:
        raise ValueError('暂不支持隔行 PNG，请另存为「非隔行」后重试')
    if depth != 8:
        raise ValueError('仅支持 8 位/通道的 PNG（当前 %d 位）' % depth)

    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(ctype)
    if channels is None:
        raise ValueError('不支持的 PNG 颜色类型: %d' % ctype)

    raw = zlib.decompress(idat)
    stride = w * channels
    out = bytearray(stride * h)
    prev = bytearray(stride)

    p = 0
    for y in range(h):
        ft = raw[p]
        p += 1
        line = bytearray(raw[p:p + stride])
        p += stride
        if ft == 1:          # Sub
            for i in range(channels, stride):
                line[i] = (line[i] + line[i - channels]) & 0xFF
        elif ft == 2:        # Up
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 0xFF
        elif ft == 3:        # Average
            for i in range(stride):
                left = line[i - channels] if i >= channels else 0
                line[i] = (line[i] + ((left + prev[i]) >> 1)) & 0xFF
        elif ft == 4:        # Paeth
            for i in range(stride):
                a = line[i - channels] if i >= channels else 0
                b = prev[i]
                c = prev[i - channels] if i >= channels else 0
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[i] = (line[i] + pr) & 0xFF
        elif ft != 0:
            raise ValueError('未知的 PNG 行过滤类型: %d' % ft)
        out[y * stride:(y + 1) * stride] = line
        prev = line

    # 统一转成 RGBA
    rgba = bytearray(w * h * 4)
    if ctype == 6:
        rgba[:] = out
    elif ctype == 2:
        for i in range(w * h):
            rgba[i * 4:i * 4 + 3] = out[i * 3:i * 3 + 3]
            rgba[i * 4 + 3] = 255
    elif ctype == 0:
        for i in range(w * h):
            g = out[i]
            rgba[i * 4] = rgba[i * 4 + 1] = rgba[i * 4 + 2] = g
            rgba[i * 4 + 3] = 255
    elif ctype == 4:
        for i in range(w * h):
            g = out[i * 2]
            rgba[i * 4] = rgba[i * 4 + 1] = rgba[i * 4 + 2] = g
            rgba[i * 4 + 3] = out[i * 2 + 1]
    else:  # 调色板
        for i in range(w * h):
            idx = out[i]
            rgba[i * 4:i * 4 + 3] = plte[idx * 3:idx * 3 + 3]
            rgba[i * 4 + 3] = trns[idx] if trns and idx < len(trns) else 255
    return w, h, bytes(rgba)


# ---------------------------------------------------------------- 缩放
def scale_rgba(sw, sh, rgba, size):
    """按面积平均缩小（带 alpha 预乘，避免边缘发灰）"""
    out = bytearray(size * size * 4)
    fx = sw / float(size)
    fy = sh / float(size)
    for ty in range(size):
        y0 = int(ty * fy)
        y1 = max(y0 + 1, min(sh, int((ty + 1) * fy)))
        for tx in range(size):
            x0 = int(tx * fx)
            x1 = max(x0 + 1, min(sw, int((tx + 1) * fx)))
            ar = ag = ab = aa = 0.0
            n = 0
            for y in range(y0, y1):
                base = (y * sw + x0) * 4
                for x in range(x0, x1):
                    i = base + (x - x0) * 4
                    a = rgba[i + 3]
                    if a:
                        ar += rgba[i] * a
                        ag += rgba[i + 1] * a
                        ab += rgba[i + 2] * a
                    aa += a
                    n += 1
            o = (ty * size + tx) * 4
            if aa > 0:
                out[o] = int(ar / aa + 0.5)
                out[o + 1] = int(ag / aa + 0.5)
                out[o + 2] = int(ab / aa + 0.5)
            out[o + 3] = int(aa / n + 0.5)
    return bytes(out)


# ---------------------------------------------------------------- 编码
def png_from_rgba(w, h, rgba):
    raw = b''.join(b'\x00' + rgba[y * w * 4:(y + 1) * w * 4] for y in range(h))

    def chunk(tag, data):
        return (struct.pack('>I', len(data)) + tag + data
                + struct.pack('>I', zlib.crc32(tag + data) & 0xffffffff))

    return (b'\x89PNG\r\n\x1a\n'
            + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 6, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(raw, 9))
            + chunk(b'IEND', b''))


def build_ico(sizes, sw, sh, rgba):
    images = []
    for s in sizes:
        if s == sw == sh:
            images.append((s, png_from_rgba(sw, sh, rgba)))   # 原图直接嵌入，最保真
        else:
            images.append((s, png_from_rgba(s, s, scale_rgba(sw, sh, rgba, s))))
    head = struct.pack('<HHH', 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries = b''
    body = b''
    for s, data in images:
        dim = 0 if s >= 256 else s
        entries += struct.pack('<BBBBHHII', dim, dim, 0, 0, 1, 32,
                               len(data), offset + len(body))
        body += data
    return head + entries + body


def preview(sizes, sw, sh, rgba):
    """白底并排预览，方便检查小尺寸是否还看得清"""
    pad = 14
    tiles = []
    for s in sizes:
        tiles.append((s, png_from_rgba(s, s, scale_rgba(sw, sh, rgba, s))))
    W = sum(s for s, _ in tiles) + pad * (len(tiles) + 1)
    H = max(s for s, _ in tiles) + pad * 2
    canvas = bytearray(b'\xff' * (W * H * 4))
    x0 = pad
    for s, _ in tiles:
        data = scale_rgba(sw, sh, rgba, s)
        oy = (H - s) // 2
        for y in range(s):
            for x in range(s):
                j = (y * s + x) * 4
                a = data[j + 3] / 255.0
                i = ((y + oy) * W + (x0 + x)) * 4
                canvas[i] = int(data[j] * a + 255 * (1 - a))
                canvas[i + 1] = int(data[j + 1] * a + 255 * (1 - a))
                canvas[i + 2] = int(data[j + 2] * a + 255 * (1 - a))
                canvas[i + 3] = 255
        x0 += s + pad
    return png_from_rgba(W, H, bytes(canvas))


if __name__ == '__main__':
    if not os.path.isfile(SRC_PNG):
        raise SystemExit('缺少图标源图：%s\n请把品牌 PNG 放到项目根目录后再运行。' % SRC_PNG)

    w, h, rgba = read_png(SRC_PNG)
    ico = build_ico(SIZES, w, h, rgba)
    with open(OUT_ICO, 'wb') as f:
        f.write(ico)
    with open(OUT_FAVICON, 'wb') as f:
        f.write(ico)
    with open(OUT_PREVIEW, 'wb') as f:
        f.write(preview((256, 128, 48, 32, 16), w, h, rgba))

    print('源图: %s (%dx%d)' % (os.path.basename(SRC_PNG), w, h))
    print('已生成: %s (%d bytes)' % (OUT_ICO, len(ico)))
    print('已生成: %s' % OUT_FAVICON)
    print('预览图: %s' % OUT_PREVIEW)
