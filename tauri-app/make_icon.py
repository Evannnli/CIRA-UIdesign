import struct, zlib, math, os

W = H = 1024
px = bytearray(W * H * 4)  # RGBA, 初始全透明


def set_px(x, y, r, g, b, a):
    if 0 <= x < W and 0 <= y < H:
        i = (y * W + x) * 4
        px[i] = r
        px[i + 1] = g
        px[i + 2] = b
        px[i + 3] = a


cx = cy = W / 2

# 深色圆屏
R = W / 2 - 20
for y in range(H):
    for x in range(W):
        if math.hypot(x - cx, y - cy) <= R:
            set_px(x, y, 22, 18, 26, 255)

# 暖橙环
ring_r = R - 60
rw = 14
for y in range(H):
    for x in range(W):
        d = math.hypot(x - cx, y - cy)
        if ring_r - rw <= d <= ring_r + rw:
            set_px(x, y, 255, 138, 61, 255)

# 中心粉点
dr = 70
for y in range(H):
    for x in range(W):
        if math.hypot(x - cx, y - cy) <= dr:
            set_px(x, y, 255, 158, 181, 255)


def chunk(typ, data):
    return struct.pack(">I", len(data)) + typ + data + struct.pack(">I", zlib.crc32(typ + data) & 0xffffffff)


raw = bytearray()
for y in range(H):
    raw.append(0)
    raw.extend(px[y * W * 4:(y + 1) * W * 4])

png = b"\x89PNG\r\n\x1a\n"
png += chunk(b"IHDR", struct.pack(">IIBBBBB", W, H, 8, 6, 0, 0, 0))
png += chunk(b"IDAT", zlib.compress(bytes(raw), 9))
png += chunk(b"IEND", b"")

os.makedirs("src-tauri/icons", exist_ok=True)
with open("src-tauri/icons/icon-source.png", "wb") as f:
    f.write(png)
print("icon-source.png written", len(png), "bytes")
