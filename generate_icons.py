"""
Ikon generáló script — létrehozza a system tray ikonokat.
Csak egyszer kell futtatni, utána a fájlok megmaradnak.
"""

from PIL import Image, ImageDraw
from pathlib import Path

ICONS_DIR = Path(__file__).parent / "icons"
ICONS_DIR.mkdir(exist_ok=True)

SIZE = 64


def create_mic_icon(state: str) -> Image.Image:
    """Mikrofon ikont generál.

    Args:
        state: 'idle' (szürke), 'active' (piros) vagy 'listening' (zöld)
    """
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Háttér kör
    if state == "active":
        bg_color = (220, 50, 50, 255)      # Piros — felvétel
    elif state == "listening":
        bg_color = (50, 180, 50, 255)      # Zöld — figyel
    else:
        bg_color = (100, 100, 100, 255)     # Szürke — idle

    draw.ellipse([2, 2, SIZE - 2, SIZE - 2], fill=bg_color)

    # Mikrofon test (lekerekített téglalap)
    mic_w, mic_h = 14, 22
    mic_x = (SIZE - mic_w) // 2
    mic_y = 14
    draw.rounded_rectangle(
        [mic_x, mic_y, mic_x + mic_w, mic_y + mic_h],
        radius=7,
        fill=(255, 255, 255, 255)
    )

    # Mikrofon ív (félkör alul)
    arc_margin = 8
    arc_top = mic_y + 8
    arc_bottom = mic_y + mic_h + 6
    draw.arc(
        [mic_x - arc_margin, arc_top, mic_x + mic_w + arc_margin, arc_bottom],
        start=0, end=180,
        fill=(255, 255, 255, 255),
        width=3
    )

    # Mikrofon szára
    stem_x = SIZE // 2
    stem_top = arc_bottom - 2
    stem_bottom = stem_top + 8
    draw.line(
        [stem_x, stem_top, stem_x, stem_bottom],
        fill=(255, 255, 255, 255),
        width=3
    )

    # Talp
    foot_w = 14
    draw.line(
        [stem_x - foot_w // 2, stem_bottom, stem_x + foot_w // 2, stem_bottom],
        fill=(255, 255, 255, 255),
        width=3
    )

    return img


if __name__ == "__main__":
    # Idle ikon (szürke)
    idle_icon = create_mic_icon("idle")
    idle_path = ICONS_DIR / "mic_idle.png"
    idle_icon.save(idle_path)
    print(f"Idle ikon elmentve: {idle_path}")

    # Listening ikon (zöld)
    listening_icon = create_mic_icon("listening")
    listening_path = ICONS_DIR / "mic_listening.png"
    listening_icon.save(listening_path)
    print(f"Listening ikon elmentve: {listening_path}")

    # Active ikon (piros)
    active_icon = create_mic_icon("active")
    active_path = ICONS_DIR / "mic_active.png"
    active_icon.save(active_path)
    print(f"Active ikon elmentve: {active_path}")

    print("Kész!")
