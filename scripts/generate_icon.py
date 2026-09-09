"""
AISBench-Prefix-Tools 图标生成器
设计: 蓝色渐变圆角背景 + 白色速度表(性能测试) + 红色指针 + AI文字
"""
import math
from PIL import Image, ImageDraw, ImageFont

# 配色 (与程序界面一致)
BLUE_TOP = (37, 99, 235)       # #2563eb COLOR_PRIMARY
BLUE_BOTTOM = (30, 58, 138)   # #1e3a8a 深蓝
WHITE = (255, 255, 255)
RED = (239, 68, 68)           # #ef4444
LIGHT_BLUE = (147, 197, 253)  # #93c5fd 浅蓝刻度
GRAY_DARK = (30, 41, 59)      # 深灰中心点


def _render(size: int) -> Image.Image:
    """在指定尺寸渲染图标 (无抗锯齿, 供超采样使用)"""
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # ---- 背景: 蓝色渐变圆角矩形 ----
    grad = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    gd = ImageDraw.Draw(grad)
    for y in range(size):
        ratio = y / max(1, size - 1)
        r = int(BLUE_TOP[0] + (BLUE_BOTTOM[0] - BLUE_TOP[0]) * ratio)
        g = int(BLUE_TOP[1] + (BLUE_BOTTOM[1] - BLUE_TOP[1]) * ratio)
        b = int(BLUE_TOP[2] + (BLUE_BOTTOM[2] - BLUE_TOP[2]) * ratio)
        gd.line([(0, y), (size, y)], fill=(r, g, b, 255))

    mask = Image.new('L', (size, size), 0)
    md = ImageDraw.Draw(mask)
    radius = max(2, size // 5)
    md.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    img.paste(grad, (0, 0), mask)
    draw = ImageDraw.Draw(img)

    # ---- 速度表 (上半圆弧) ----
    cx = size // 2
    cy = int(size * 0.56)
    r_out = int(size * 0.34)
    gauge_w = max(2, size // 20)

    # 弧线 180°→360° = 左→上→右 (上半圆)
    bbox = [cx - r_out, cy - r_out, cx + r_out, cy + r_out]
    draw.arc(bbox, start=180, end=360, fill=WHITE + (255,), width=gauge_w)

    # ---- 刻度线 ----
    num_ticks = 7
    r_tick_in = r_out - gauge_w - max(1, size // 45)
    r_tick_out = r_out - max(1, gauge_w // 3)
    tick_w = max(1, size // 55)
    for i in range(num_ticks):
        angle = math.radians(180 + (180 * i / (num_ticks - 1)))
        x1 = cx + r_tick_in * math.cos(angle)
        y1 = cy + r_tick_in * math.sin(angle)
        x2 = cx + r_tick_out * math.cos(angle)
        y2 = cy + r_tick_out * math.sin(angle)
        draw.line([(x1, y1), (x2, y2)], fill=LIGHT_BLUE + (255,), width=tick_w)

    # ---- 指针 (指向右上 ~315°, 表示高性能) ----
    needle_angle = math.radians(320)
    needle_len = int(r_out * 0.78)
    nx = cx + needle_len * math.cos(needle_angle)
    ny = cy + needle_len * math.sin(needle_angle)
    needle_w = max(2, size // 26)
    draw.line([(cx, cy), (nx, ny)], fill=RED + (255,), width=needle_w)

    # ---- 中心轴 ----
    hub_r = max(2, size // 26)
    draw.ellipse([cx - hub_r, cy - hub_r, cx + hub_r, cy + hub_r], fill=WHITE + (255,))
    hub_r2 = max(1, size // 60)
    draw.ellipse([cx - hub_r2, cy - hub_r2, cx + hub_r2, cy + hub_r2], fill=RED + (255,))

    # ---- "AI" 文字 ----
    if size >= 48:
        font_size = max(10, size // 6)
        font = None
        for fp in ["C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/arial.ttf",
                    "arialbd.ttf", "arial.ttf"]:
            try:
                font = ImageFont.truetype(fp, font_size)
                break
            except Exception:
                continue
        if font is None:
            font = ImageFont.load_default()

        text = "AI"
        tbbox = draw.textbbox((0, 0), text, font=font)
        tw, th = tbbox[2] - tbbox[0], tbbox[3] - tbbox[1]
        tx = cx - tw // 2 - tbbox[0]
        ty = int(size * 0.83) - th // 2 - tbbox[1]
        draw.text((tx, ty), text, fill=WHITE + (255,), font=font)

    return img


def create_icon(size: int) -> Image.Image:
    """超采样渲染 (4x → LANCZOS缩小), 产生平滑边缘"""
    ss = 4
    large = _render(size * ss)
    return large.resize((size, size), Image.LANCZOS)


def main():
    target_sizes = [16, 24, 32, 48, 64, 128, 256]
    images = [create_icon(s) for s in target_sizes]

    # 保存多分辨率 .ico
    images[-1].save(
        "app.ico",
        format="ICO",
        sizes=[(s, s) for s in target_sizes],
    )

    # 保存预览 PNG
    create_icon(256).save("app_preview.png")
    print("图标已生成: app.ico (多分辨率: 16~256)")
    print("预览图: app_preview.png")


if __name__ == "__main__":
    main()
