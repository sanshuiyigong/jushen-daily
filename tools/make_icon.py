"""生成应用图标：深色底 + 青色夹爪 + 红色方块。

设计理由：
  · 「夹爪抓住方块」是机器人操作最经典的意象，一眼就知道是具身/机器人
  · 只用两个色块，形状简单，缩到 16px 仍然能认出来
  · 青色对应程序主色调，红色对应「最高优先级」那一档
  · 平涂不渐变，小尺寸下不会糊成一片

实现要点：
  字形先画在**透明层**上，算出它的实际包围盒，再等比缩放到占画布 66%，
  最后居中贴到圆角底上。这样不管字形怎么调，都不会出现「偏左/偏小」。
"""

from pathlib import Path
import sys

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
OUT_ICO = ROOT / "web" / "favicon.ico"
OUT_PNG = ROOT / "web" / "icon-512.png"

S = 1024                      # 先画大图再缩，等于超采样抗锯齿
FILL_RATIO = 0.66             # 字形占画布的比例

BG = (11, 14, 19, 255)        # #0b0e13
CYAN = (125, 211, 252, 255)   # #7dd3fc
RED = (225, 29, 72, 255)      # #e11d48
EDGE = (30, 41, 59, 255)      # #1e293b


def build_glyph() -> Image.Image:
    """只画夹爪和方块，透明背景。"""
    layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)

    bar = 132
    x0 = 300
    y_top, y_bot = 280, 760        # 夹爪外沿高度 480
    reach = x0 + 300               # 横梁长度

    # 竖梁
    d.rounded_rectangle([x0, y_top, x0 + bar, y_bot], radius=bar // 2, fill=CYAN)
    # 上横梁
    d.rounded_rectangle([x0, y_top, reach, y_top + bar], radius=bar // 2, fill=CYAN)
    # 下横梁
    d.rounded_rectangle([x0, y_bot - bar, reach, y_bot], radius=bar // 2, fill=CYAN)

    # 方块：卡在开口里，右侧探出来
    cube = 190
    cy = (y_top + y_bot) // 2
    d.rounded_rectangle(
        [reach - 40, cy - cube // 2, reach - 40 + cube, cy + cube // 2],
        radius=42,
        fill=RED,
    )
    return layer


def compose() -> Image.Image:
    glyph = build_glyph()
    box = glyph.getbbox()
    if not box:
        raise RuntimeError("字形是空的")

    glyph = glyph.crop(box)
    gw, gh = glyph.size

    target = int(S * FILL_RATIO)
    scale = target / max(gw, gh)
    glyph = glyph.resize((max(1, int(gw * scale)), max(1, int(gh * scale))), Image.LANCZOS)

    canvas = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(canvas)
    d.rounded_rectangle([0, 0, S - 1, S - 1], radius=214, fill=BG, outline=EDGE, width=6)

    pos = ((S - glyph.width) // 2, (S - glyph.height) // 2)
    canvas.alpha_composite(glyph, pos)
    return canvas


def main() -> int:
    big = compose()
    OUT_PNG.parent.mkdir(parents=True, exist_ok=True)

    big.resize((512, 512), Image.LANCZOS).save(OUT_PNG, "PNG")

    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    big.save(OUT_ICO, format="ICO", sizes=sizes)

    # 32px 的真实效果放大 4 倍，用来检查小尺寸下会不会糊
    check = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("_icon32_check.png")
    big.resize((32, 32), Image.LANCZOS).resize((128, 128), Image.NEAREST).save(check, "PNG")

    print(f"  OK  {OUT_PNG}  (512x512)")
    print(f"  OK  {OUT_ICO}  ({len(sizes)} sizes: 16-256)")
    print(f"  OK  {check}  (32px x4)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
