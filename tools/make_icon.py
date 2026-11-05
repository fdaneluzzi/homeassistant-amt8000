"""Generate the integration's brand images (custom_components/amt8000/brand/).

Original artwork (shield + house + signal arcs); it does not use Intelbras'
logo or trademarks. Run: python tools/make_icon.py  (needs Pillow)
"""
from pathlib import Path

from PIL import Image, ImageDraw

S = 1024  # draw large, downscale for anti-aliasing
OUT = Path(__file__).resolve().parent.parent / "custom_components" / "amt8000" / "brand"

GREEN_TOP, GREEN_BOT = (0, 168, 120), (0, 105, 92)
WHITE = (255, 255, 255, 255)


def shield_mask() -> Image.Image:
    m = Image.new("L", (S, S), 0)
    d = ImageDraw.Draw(m)
    # shield outline: flat top with rounded corners, tapering to a point
    pts = [(512, 70), (880, 190), (880, 520)]
    left = [(144, 520), (144, 190)]
    # approximate the curved flanks with a polygon sampled along a quadratic bezier
    def bez(p0, p1, p2, n=60):
        return [
            (
                (1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t**2 * p2[0],
                (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t**2 * p2[1],
            )
            for t in (i / n for i in range(n + 1))
        ]
    poly = [(512, 70), (880, 190)] + [(880, 190), (880, 520)]
    poly += bez((880, 520), (860, 800), (512, 960))
    poly += bez((512, 960), (164, 800), (144, 520))
    poly += [(144, 190)]
    d.polygon(poly, fill=255)
    return m


def gradient() -> Image.Image:
    g = Image.new("RGBA", (S, S))
    px = g.load()
    for y in range(S):
        t = y / (S - 1)
        c = tuple(int(GREEN_TOP[i] + (GREEN_BOT[i] - GREEN_TOP[i]) * t) for i in range(3))
        for x in range(S):
            px[x, y] = (*c, 255)
    return g


def build() -> Image.Image:
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    img.paste(gradient(), (0, 0), shield_mask())
    d = ImageDraw.Draw(img)
    # house: roof triangle + body, door cut-out drawn in gradient colour
    d.polygon([(512, 285), (760, 495), (264, 495)], fill=WHITE)
    d.rectangle([326, 480, 698, 725], fill=WHITE)
    d.rounded_rectangle([452, 575, 572, 725], radius=18, fill=(0, 128, 104, 255))
    # signal arcs above the roof (local-network / monitoring cue)
    for r, w in ((70, 28), (125, 28)):
        d.arc([512 - r, 238 - r, 512 + r, 238 + r], 225, 315, fill=WHITE, width=w)
    d.ellipse([512 - 22, 238 - 22, 512 + 22, 238 + 22], fill=WHITE)
    return img


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    big = build()
    for name, size in (("icon.png", 256), ("icon@2x.png", 512), ("logo.png", 256), ("logo@2x.png", 512)):
        big.resize((size, size), Image.LANCZOS).save(OUT / name, optimize=True)
        print("wrote", OUT / name)


if __name__ == "__main__":
    main()
