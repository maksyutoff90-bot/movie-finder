"""Генерация иконки приложения (data/app.ico) без внешних ресурсов.

Запуск:  python tools/make_icon.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "data" / "app.ico"

BG = (16, 21, 30, 255)
BORDER = (44, 54, 70, 255)
ACCENT = (76, 141, 255, 255)
LIGHT = (233, 237, 244, 255)


def draw_icon(size: int = 512) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    radius = int(size * 0.22)
    draw.rounded_rectangle(
        [0, 0, size - 1, size - 1], radius=radius, fill=BG, outline=BORDER, width=max(2, size // 96)
    )

    # Киноплёнка: полоса с перфорацией справа
    strip_w = int(size * 0.16)
    strip_x = size - strip_w - int(size * 0.12)
    draw.rounded_rectangle(
        [strip_x, int(size * 0.16), strip_x + strip_w, int(size * 0.84)],
        radius=int(strip_w * 0.18),
        fill=(24, 31, 43, 255),
        outline=(58, 70, 88, 255),
        width=max(1, size // 200),
    )
    hole = int(strip_w * 0.42)
    hole_h = int(strip_w * 0.30)
    for index in range(4):
        top = int(size * 0.22) + index * int(size * 0.15)
        left = strip_x + (strip_w - hole) // 2
        draw.rounded_rectangle(
            [left, top, left + hole, top + hole_h], radius=hole_h // 3, fill=(60, 74, 94, 255)
        )

    # Кнопка «плей»
    cx, cy = int(size * 0.42), int(size * 0.5)
    play = size * 0.20
    draw.polygon(
        [(cx - play * 0.62, cy - play), (cx - play * 0.62, cy + play), (cx + play, cy)],
        fill=ACCENT,
    )
    draw.ellipse(
        [cx - play * 1.35, cy - play * 1.35, cx + play * 1.35, cy + play * 1.35],
        outline=(76, 141, 255, 90),
        width=max(2, size // 90),
    )

    # Блик сверху
    draw.rounded_rectangle(
        [int(size * 0.06), int(size * 0.05), int(size * 0.94), int(size * 0.05) + max(2, size // 120)],
        radius=2,
        fill=(255, 255, 255, 18),
    )
    return img


def main() -> int:
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    icon = draw_icon(512)
    icon.save(TARGET, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    preview = TARGET.with_name("app_icon_preview.png")
    icon.resize((256, 256), Image.LANCZOS).save(preview)
    print(f"Сохранено: {TARGET}")
    print(f"Превью:   {preview}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
