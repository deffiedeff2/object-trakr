"""Fast monospace text blitting into BGR numpy frames.

Glyphs are rendered once with PIL per (font, size, char) and cached; strings are
assembled by stacking glyph masks side by side (works because the font is monospace).
"""
import os
from collections import OrderedDict

import numpy as np
from PIL import Image, ImageDraw, ImageFont

_HOME = os.path.expanduser("~")
FONT_DIRS = [
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fonts"),  # bundled (optional)
    os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"),                   # Windows
    os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Windows", "Fonts"),
    "/System/Library/Fonts", "/System/Library/Fonts/Supplemental", "/Library/Fonts",  # macOS
    os.path.join(_HOME, "Library", "Fonts"),
    "/usr/share/fonts/truetype/dejavu", "/usr/share/fonts/truetype/liberation",       # Linux
    "/usr/share/fonts/TTF", os.path.join(_HOME, ".fonts"),
]
# Each UI font name maps to its own file first, then the closest look-alike on other OSes.
FONT_FILES = {
    "Consolas": ["consola.ttf", "SFNSMono.ttf", "Menlo.ttc"],
    "Cascadia Mono": ["CascadiaMono.ttf", "SFNSMono.ttf", "Menlo.ttc"],
    "Menlo": ["Menlo.ttc", "consola.ttf"],
    "Courier New": ["cour.ttf", "Courier New.ttf", "LiberationMono-Regular.ttf"],
    "Lucida Console": ["lucon.ttf", "Monaco.ttf", "Menlo.ttc"],
}
FALLBACK = ["consola.ttf", "Menlo.ttc", "SFNSMono.ttf", "Monaco.ttf", "DejaVuSansMono.ttf", "LiberationMono-Regular.ttf"]


def _font_path(name):
    for fn in FONT_FILES.get(name, []) + FALLBACK:
        for d in FONT_DIRS:
            p = os.path.join(d, fn)
            if d and os.path.exists(p):
                return p
    return None


class MonoText:
    def __init__(self, max_strings=4096):
        self._fonts = {}
        self._glyphs = {}
        self._strings = OrderedDict()
        self._max = max_strings

    def _font(self, name, size):
        key = (name, size)
        f = self._fonts.get(key)
        if f is None:
            path = _font_path(name)
            f = ImageFont.truetype(path, size) if path else ImageFont.load_default(size)
            asc, desc = f.getmetrics()
            adv = max(1, int(round(f.getlength("M"))))
            self._fonts[key] = f = (f, asc + desc, adv)
        return f

    def cell(self, name, size):
        _, h, adv = self._font(name, size)
        return adv, h

    def _glyph(self, name, size, ch):
        key = (name, size, ch)
        g = self._glyphs.get(key)
        if g is None:
            font, h, adv = self._font(name, size)
            img = Image.new("L", (adv, h), 0)
            ImageDraw.Draw(img).text((0, 0), ch, font=font, fill=255)
            g = self._glyphs[key] = np.asarray(img, dtype=np.uint8)
        return g

    def mask(self, text, name, size):
        key = (text, name, size)
        m = self._strings.get(key)
        if m is not None:
            self._strings.move_to_end(key)
            return m
        if not text:
            _, h, _ = self._font(name, size)
            m = np.zeros((h, 0), np.uint8)
        else:
            m = np.hstack([self._glyph(name, size, c) for c in text])
        self._strings[key] = m
        if len(self._strings) > self._max:
            self._strings.popitem(last=False)
        return m

    @staticmethod
    def blit(img, mask, x, y, color, alpha=1.0):
        """Alpha-blend a solid color through an 8-bit mask at (x, y). Clips to image."""
        H, W = img.shape[:2]
        h, w = mask.shape
        x, y = int(x), int(y)
        x0, y0 = max(x, 0), max(y, 0)
        x1, y1 = min(x + w, W), min(y + h, H)
        if x1 <= x0 or y1 <= y0:
            return
        m = mask[y0 - y:y1 - y, x0 - x:x1 - x]
        a = m.astype(np.uint16)
        if alpha < 1.0:
            a = (a * int(alpha * 256)) >> 8
        a = a[..., None]
        roi = img[y0:y1, x0:x1]
        col = np.array(color, np.uint16)[None, None, :]
        roi[:] = ((roi.astype(np.uint16) * (255 - a) + col * a) // 255).astype(np.uint8)

    @staticmethod
    def panel(img, x, y, w, h, color, alpha):
        """Semi-transparent filled rectangle."""
        if alpha <= 0:
            return
        H, W = img.shape[:2]
        x0, y0 = max(int(x), 0), max(int(y), 0)
        x1, y1 = min(int(x + w), W), min(int(y + h), H)
        if x1 <= x0 or y1 <= y0:
            return
        roi = img[y0:y1, x0:x1]
        col = np.empty_like(roi)
        col[:] = color
        roi[:] = (roi.astype(np.uint16) * int((1 - alpha) * 256) + col.astype(np.uint16) * int(alpha * 256) >> 8).astype(np.uint8)

    def draw(self, img, text, x, y, color, size, font="Consolas", alpha=1.0):
        m = self.mask(text, font, size)
        self.blit(img, m, x, y, color, alpha)
        return m.shape[1], m.shape[0]
