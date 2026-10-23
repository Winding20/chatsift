"""生成 README 顶部的宣传 GIF（v2：更短、更干净）。

素材：两张自己的界面截图，命名为
    docs/images/digest.png   （「群里发生了什么」那一屏）
    docs/images/cards.png    （「值得看的卡片」那一屏）
仓库里只保留了生成好的 GIF，源图需要自己截；放入上述路径后运行本脚本即可重做。

输出：docs/images/promo.gif

用法：
    .\\.venv\\Scripts\\python.exe -X utf8 tools\\make_promo.py
"""

from __future__ import annotations

import math
import random
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont


ROOT = Path(__file__).resolve().parent.parent
IMAGES = ROOT / "docs" / "images"
OUT = IMAGES / "promo.gif"

W, H = 960, 540
FPS = 10
DURATION = 10.6

# 截图里含留白，先裁掉再放大
CROP_FULL = (0, 0, 1440, 1000)
CROP_CARDS = (812, 150, 1440, 1000)
CROP_SEARCH = (236, 60, 1440, 700)

FONT_DIR = Path("C:/Windows/Fonts")
INK = (38, 44, 66)
MUTED = (112, 120, 142)
ACCENT = (79, 139, 255)
WHITE = (255, 255, 255)


def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(str(FONT_DIR / name), size)
    except OSError:
        return ImageFont.load_default(size)


F_HERO = font("msyhbd.ttc", 58)
F_TITLE = font("msyhbd.ttc", 46)
F_SUB = font("msyh.ttc", 22)
F_BODY = font("msyh.ttc", 18)
F_SMALL = font("msyh.ttc", 15)
F_TAG = font("msyhbd.ttc", 16)


def gradient(top, bottom) -> Image.Image:
    column = Image.new("RGB", (1, H))
    pixels = column.load()
    for y in range(H):
        ratio = y / (H - 1)
        pixels[0, y] = tuple(int(top[i] + (bottom[i] - top[i]) * ratio) for i in range(3))
    return column.resize((W, H))


BACKGROUND = gradient((233, 241, 255), (246, 238, 255))


def ease(t: float) -> float:
    return 1 - (1 - max(0.0, min(1.0, t))) ** 3


def mask_round(size, radius) -> Image.Image:
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size[0] - 1, size[1] - 1], radius=radius, fill=255)
    return mask


def upscale(path: Path, box, width: int, height: int, shift: float) -> Image.Image:
    image = Image.open(path).convert("RGB").crop(box)
    scale = width / image.width
    resized = image.resize((width, int(image.height * scale)), Image.LANCZOS)
    view_h = min(height, resized.height)
    top = int(max(0, resized.height - view_h) * shift)
    return resized.crop((0, top, width, top + view_h))


def card(image: Image.Image, size, radius: int = 16) -> Image.Image:
    w, h = size
    shadow = Image.new("RGBA", (w + 50, h + 50), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle(
        [25, 28, 25 + w, 28 + h], radius=radius, fill=(60, 90, 150, 75)
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(13))

    body = image.convert("RGBA").resize((w, h), Image.LANCZOS)
    body.putalpha(mask_round((w, h), radius))

    canvas = Image.new("RGBA", shadow.size, (0, 0, 0, 0))
    canvas.alpha_composite(shadow)
    canvas.alpha_composite(body, (25, 28))
    ImageDraw.Draw(canvas).rounded_rectangle(
        [25, 28, 25 + w - 1, 28 + h - 1], radius=radius, outline=(255, 255, 255, 200), width=1
    )
    return canvas


BUBBLES = [
    ("张三", "明天下午三点开会"),
    ("李四", "好的"),
    ("王五", "[image]"),
    ("赵六", "那个显卡到底值不值"),
    ("张三", "先别买，等降价"),
    ("小美", "哈哈哈"),
    ("王五", "今晚聚餐有人吗"),
    ("李四", "[face]"),
    ("赵六", "我这有个更便宜的车"),
    ("张三", "链接发我"),
    ("小美", "冲"),
    ("王五", "服务器又维护了"),
]


def draw_bubbles(frame: Image.Image, t: float) -> None:
    """右侧一列不断上滚的消息气泡，示意"消息很多"。"""
    column_w, column_h, left, top = 330, 430, 570, 60
    column = Image.new("RGBA", (column_w, column_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(column)

    gap, bubble_h = 52, 42
    total = len(BUBBLES) * gap
    offset = (t * 60) % total

    for index in range(len(BUBBLES) + 3):
        name, text = BUBBLES[index % len(BUBBLES)]
        y = index * gap - offset
        if y < -bubble_h or y > column_h:
            continue
        width = min(column_w - 16, 60 + int(len(text) * 15))
        x = 8 if index % 2 == 0 else column_w - width - 8
        box = [x, y, x + width, y + bubble_h]
        draw.rounded_rectangle(box, radius=12, fill=(255, 255, 255, 225))
        draw.text((x + 12, y + 6), name, font=F_SMALL, fill=(140, 158, 186))
        draw.text((x + 12, y + 21), text, font=F_SMALL, fill=(60, 82, 118))

    # 上下渐隐：在原有 alpha 上做乘法，否则透明区域会变成黑色
    fade = Image.new("L", (column_w, column_h), 255)
    fade_draw = ImageDraw.Draw(fade)
    for y in range(50):
        fade_draw.line([(0, y), (column_w, y)], fill=int(255 * y / 50))
        fade_draw.line([(0, column_h - 1 - y), (column_w, column_h - 1 - y)], fill=int(255 * y / 50))
    column.putalpha(ImageChops.multiply(column.getchannel("A"), fade))

    frame.alpha_composite(column, (left, top))


def scene_flood(t: float) -> Image.Image:
    frame = BACKGROUND.copy().convert("RGBA")
    draw = ImageDraw.Draw(frame)

    a = int(255 * ease(t / 0.5))
    rise = int((1 - ease(t / 0.6)) * 18)
    draw.text((70, 176 + rise), "群消息一天", font=F_SUB, fill=MUTED + (a,))
    draw.text((70, 208 + rise), "300 条", font=F_HERO, fill=INK + (a,))
    draw.text((70, 292 + rise), "你只看了 3 条", font=F_HERO, fill=ACCENT + (a,))

    draw_bubbles(frame, t)
    return frame


def scene_digest(t: float) -> Image.Image:
    frame = BACKGROUND.copy().convert("RGBA")
    draw = ImageDraw.Draw(frame)

    a = int(255 * ease(t / 0.45))
    draw.text((64, 150), "AI 替你看完", font=F_TITLE, fill=INK + (a,))
    draw.text((64, 208), "按话题整理", font=F_SUB, fill=MUTED + (a,))
    draw.text((64, 240), "带结论、时间和参与人", font=F_SUB, fill=MUTED + (a,))
    draw.text((64, 296), "不用翻几百条", font=F_SMALL, fill=ACCENT + (a,))

    slide = int((1 - ease((t - 0.1) / 0.6)) * 46) if t > 0.1 else 46
    shot = upscale(IMAGES / "ui_full.png", CROP_FULL, 520, 361, ease(t / 3.2) * 0.5)
    frame.alpha_composite(card(shot, (520, 361)), (398 + slide, 72))
    return frame


TAGS = ["知识点", "段子", "观点", "情报", "约定"]


def scene_cards(t: float) -> Image.Image:
    frame = BACKGROUND.copy().convert("RGBA")
    draw = ImageDraw.Draw(frame)

    a = int(255 * ease(t / 0.45))
    draw.text((64, 152), "只留值得看的", font=F_TITLE, fill=INK + (a,))

    x, y = 64, 232
    for index, tag in enumerate(TAGS):
        delay = 0.25 + index * 0.12
        if t < delay:
            continue
        ta = int(255 * ease((t - delay) / 0.3))
        width = int(len(tag) * 16 + 24)
        draw.rounded_rectangle([x, y, x + width, y + 34], radius=17, fill=ACCENT + (ta,))
        draw.text((x + width / 2, y + 17), tag, font=F_TAG, fill=WHITE + (ta,), anchor="mm")
        x += width + 8
        if x > 430:
            x, y = 64, y + 46

    slide = int((1 - ease((t - 0.1) / 0.6)) * 40) if t > 0.1 else 40
    shot = upscale(IMAGES / "ui_full.png", CROP_CARDS, 300, 411, ease(t / 3.0) * 0.5)
    frame.alpha_composite(card(shot, (300, 411)), (560 + slide, 60))
    return frame


def scene_end(t: float) -> Image.Image:
    frame = BACKGROUND.copy().convert("RGBA")
    draw = ImageDraw.Draw(frame)

    a = int(255 * ease(t / 0.45))
    icon_path = ROOT / "app" / "static" / "apple-touch-icon.png"
    if icon_path.exists():
        size = 76
        icon = Image.open(icon_path).convert("RGBA").resize((size, size), Image.LANCZOS)
        mask = Image.new("L", (size, size), 0)
        ImageDraw.Draw(mask).rounded_rectangle(
            [0, 0, size - 1, size - 1], radius=int(size * 0.23), fill=255
        )
        icon.putalpha(mask)
        frame.alpha_composite(icon, (W // 2 - size // 2, 114))
        title_y = 244
    else:
        title_y = 208

    draw.text((W // 2, title_y), "chatsift", font=F_HERO, fill=INK + (a,), anchor="mm")
    draw.text((W // 2, title_y + 54), "没时间看群，也能捡到值得看的东西", font=F_SUB, fill=MUTED + (a,), anchor="mm")

    a2 = int(255 * ease((t - 0.3) / 0.4))
    draw.text((W // 2, title_y + 114), "本地运行 · 数据只在你电脑上", font=F_SMALL, fill=MUTED + (a2,), anchor="mm")

    a3 = int(255 * ease((t - 0.5) / 0.4))
    draw.rounded_rectangle([268, title_y + 152, 692, title_y + 202], radius=14, fill=(255, 255, 255, 210))
    draw.text(
        (W // 2, title_y + 177),
        "github.com/Winding20/chatsift",
        font=F_BODY,
        fill=INK + (a3,),
        anchor="mm",
    )
    return frame


def scene_search(t: float) -> Image.Image:
    frame = BACKGROUND.copy().convert("RGBA")
    draw = ImageDraw.Draw(frame)

    a = int(255 * ease(t / 0.45))
    draw.text((64, 150), "想找什么", font=F_TITLE, fill=INK + (a,))
    draw.text((64, 208), "直接搜", font=F_SUB, fill=MUTED + (a,))
    draw.text((64, 240), "消息、卡片、话题一起搜", font=F_SUB, fill=MUTED + (a,))

    slide = int((1 - ease((t - 0.1) / 0.6)) * 46) if t > 0.1 else 46
    shot = upscale(IMAGES / "ui_search.png", CROP_SEARCH, 560, 320, ease(t / 3.0) * 0.4)
    frame.alpha_composite(card(shot, (560, 320)), (360 + slide, 110))
    return frame


SCENES = [
    (0.0, 2.0, scene_flood),
    (2.0, 4.2, scene_digest),
    (4.2, 6.2, scene_cards),
    (6.2, 8.4, scene_search),
    (8.4, DURATION, scene_end),
]


def frame_at(t: float) -> Image.Image:
    for start, end, builder in SCENES:
        if start <= t < end:
            local = t - start
            frame = builder(local)
            if local < 0.2:
                frame = Image.blend(BACKGROUND.convert("RGBA"), frame, ease(local / 0.2))
            return frame
    return scene_end(DURATION - SCENES[-1][0])


def main() -> None:
    missing = [name for name in ("ui_full.png",) if not (IMAGES / name).exists()]
    if missing:
        print("缺少素材：" + "、".join(f"docs/images/{name}" for name in missing))
        print("放一张自己的界面截图进去（文件名保持不变），再运行本脚本。")
        return

    total = int(FPS * DURATION)
    target = (800, 450)  # 输出再缩一档，仓库里别放大文件
    frames = [
        frame_at(index / FPS)
        .convert("RGB")
        .resize(target, Image.LANCZOS)
        .convert("P", palette=Image.ADAPTIVE, colors=64)
        for index in range(total)
    ]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(
        OUT,
        save_all=True,
        append_images=frames[1:],
        duration=int(1000 / FPS),
        loop=0,
        optimize=True,
        disposal=2,
    )
    print(f"已生成 {OUT}  帧数={total}  体积={OUT.stat().st_size / 1024 / 1024:.2f} MB")


if __name__ == "__main__":
    main()
