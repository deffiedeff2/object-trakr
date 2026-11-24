"""Render engine: object tracking layer + building-edge layer + post FX."""
import colorsys
import math
import os
import random
import threading
from collections import deque

import cv2
import numpy as np

from .textfx import MonoText

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_DIR = os.path.join(ROOT, "models")
TEXT = MonoText()
_MODEL_LOCK = threading.Lock()
HEXCH = "0123456789ABCDEF"
SCRAMBLE = "0123456789ABCDEF#$%&*+=<>/\\|:;@"
RAINCH = "0123456789ABCDEFXZ:.=*+-<>|"


# ---------------------------------------------------------------- colors
def hex2bgr(h):
    h = str(h).lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    try:
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except ValueError:
        r, g, b = 0, 255, 100
    return (b, g, r)


def vary(bgr, key, amount):
    """Deterministic hue/value jitter keyed on `key`."""
    if amount <= 0:
        return tuple(int(c) for c in bgr)
    rng = random.Random(str(key))
    b, g, r = [c / 255.0 for c in bgr]
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    h = (h + (rng.random() * 2 - 1) * amount * 0.35) % 1.0
    s = min(1.0, max(0.0, s * (1 - rng.random() * amount * 0.3)))
    v = min(1.0, max(0.25, v * (1 - rng.random() * amount * 0.35) + rng.random() * amount * 0.15))
    r, g, b = colorsys.hsv_to_rgb(h, s, v)
    return (int(b * 255), int(g * 255), int(r * 255))


def hue_of(bgr, key):
    """Keep the base color's saturation/value, pick a hue from key."""
    b, g, r = [c / 255.0 for c in bgr]
    _, s, v = colorsys.rgb_to_hsv(r, g, b)
    h = (random.Random(str(key)).random()) % 1.0
    r, g, b = colorsys.hsv_to_rgb(h, max(s, 0.6), max(v, 0.8))
    return (int(b * 255), int(g * 255), int(r * 255))


def scale_col(bgr, k):
    return tuple(int(min(255, c * k)) for c in bgr)


# ---------------------------------------------------------------- device
_DEVICE_CACHE = {}


def available_devices():
    """Which accelerators this machine has: cuda (NVIDIA), mps (Apple Silicon unified memory), cpu."""
    if "list" not in _DEVICE_CACHE:
        import torch
        devs = []
        if torch.cuda.is_available():
            devs.append("cuda")
        if getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
            devs.append("mps")
        devs.append("cpu")
        _DEVICE_CACHE["list"] = devs
    return _DEVICE_CACHE["list"]


def resolve_device(pref):
    devs = available_devices()
    if pref in devs:
        return pref
    return devs[0]  # "auto" or unavailable choice -> best available


# ---------------------------------------------------------------- detector
class Detector:
    def __init__(self, name, device="cpu"):
        from ultralytics import YOLO
        os.makedirs(MODEL_DIR, exist_ok=True)
        path = os.path.join(MODEL_DIR, name)
        with _MODEL_LOCK:  # serialize first-time downloads
            if not os.path.exists(path):
                cwd = os.getcwd()
                os.chdir(MODEL_DIR)
                try:
                    YOLO(name)
                finally:
                    os.chdir(cwd)
            self.model = YOLO(path)
        self.name = name
        self.device = device
        self.names = self.model.names
        self._lookup = {v.lower(): k for k, v in self.names.items()}

    def class_ids(self, text):
        if not text or not text.strip():
            return None
        ids = [self._lookup[t.strip().lower()] for t in text.split(",") if t.strip().lower() in self._lookup]
        return ids or None

    def run(self, frame, p, track=True):
        kw = dict(conf=float(p["conf"]), imgsz=int(p["imgsz"]), classes=self.class_ids(p["classes"]),
                  device=self.device, verbose=False)
        if track:
            r = self.model.track(frame, persist=True, tracker="bytetrack.yaml", **kw)[0]
        else:
            r = self.model.predict(frame, **kw)[0]
        dets = []
        if r.boxes is None or len(r.boxes) == 0:
            return dets
        xyxy = r.boxes.xyxy.cpu().numpy()
        cls = r.boxes.cls.cpu().numpy().astype(int)
        conf = r.boxes.conf.cpu().numpy()
        ids = r.boxes.id.cpu().numpy().astype(int) if r.boxes.id is not None else None
        polys = r.masks.xy if r.masks is not None else None
        for i in range(len(xyxy)):
            if track and ids is None:
                continue  # tracker not yet confirmed anything
            dets.append({
                "id": int(ids[i]) if ids is not None else i + 1,
                "cls": int(cls[i]),
                "name": self.names[int(cls[i])],
                "conf": float(conf[i]),
                "box": xyxy[i].astype(np.float32),
                "poly": polys[i] if polys is not None and i < len(polys) else None,
            })
        return dets


# ---------------------------------------------------------------- code rain
class Rain:
    def __init__(self):
        self.cols = None
        self.key = None

    def step(self, img, p, s, fidx):
        H, W = img.shape[:2]
        size = max(6, int(round(p["rain_size"] * s)))
        cw, ch = TEXT.cell(p["font"], size)
        ncols = max(1, W // cw)
        key = (W, H, size, round(p["rain_density"], 2))
        rng = random.Random()
        if self.key != key:
            self.key = key
            self.cols = []
            for c in range(ncols):
                if rng.random() < p["rain_density"]:
                    self.cols.append(self._new(c, H, ch, rng, initial=True))
        color = hex2bgr(p["rain_color"])
        op = p["rain_opacity"]
        head = scale_col(color, 1.0)
        head = tuple(int(c + (255 - c) * 0.7) for c in head)
        for col in self.cols:
            col["y"] += col["v"] * p["rain_speed"] * s * 6
            if (col["y"] - col["len"] * ch) > H:
                col.update(self._new(col["c"], H, ch, rng))
            if rng.random() < 0.08:
                col["chars"][rng.randrange(len(col["chars"]))] = rng.choice(RAINCH)
            x = col["c"] * cw
            hy = int(col["y"])
            n = col["len"]
            for i in range(n):
                y = hy - i * ch
                if y < -ch or y > H:
                    continue
                a = op * (1 - i / n)
                TEXT.draw(img, col["chars"][i % len(col["chars"])], x, y, head if i == 0 else color, size, p["font"], a)

    @staticmethod
    def _new(c, H, ch, rng, initial=False):
        n = rng.randint(6, 28)
        return {"c": c, "y": rng.uniform(-H, H) if initial else -rng.uniform(0, H * 0.5), "v": rng.uniform(0.6, 1.6),
                "len": n, "chars": [rng.choice(RAINCH) for _ in range(n)]}


# ---------------------------------------------------------------- renderer
class Renderer:
    """Stateful renderer. One instance per video pass (preview stream / export)."""

    def __init__(self, track=True):
        self.track = track
        self.detector = None
        self.tracks = {}
        self.prev_edge = None
        self.rain = Rain()
        self._vig = {}
        self._last_dets = []
        self.det_cache = None  # optional dict for stateless preview

    # -------------------------------------------------------- detection
    def _get_detector(self, p):
        dev = resolve_device(p["device"])
        if self.detector is None or self.detector.name != p["model"] or self.detector.device != dev:
            self.detector = Detector(p["model"], dev)
            self.tracks = {}
        return self.detector

    def _detect(self, frame, idx, p, cache_key=None):
        det = self._get_detector(p)
        if not self.track:
            if self.det_cache is not None and cache_key is not None:
                k = (cache_key, p["model"], p["conf"], p["imgsz"], p["classes"])
                if k in self.det_cache:
                    return self.det_cache[k]
                dets = det.run(frame, p, track=False)
                if len(self.det_cache) > 64:
                    self.det_cache.pop(next(iter(self.det_cache)))
                self.det_cache[k] = dets
                return dets
            return det.run(frame, p, track=False)

        every = max(1, int(p["detect_every"]))
        if idx % every == 0 or not self.tracks:
            dets = det.run(frame, p, track=True)
            self._update_tracks(dets, idx, p)
        else:  # extrapolate with last velocity
            for t in self.tracks.values():
                if t["last"] == idx - 1:
                    t["box"] = t["box"] + np.tile(t["vel"], 2)
                    t["last"] = idx
                    c = (t["box"][:2] + t["box"][2:]) / 2
                    t["hist"].append(c.copy())
        return [t for t in self.tracks.values() if t["last"] == idx]

    def _update_tracks(self, dets, idx, p):
        a = float(p["smoothing"])
        maxlen = max(2, int(p["trail_len"]))
        for d in dets:
            t = self.tracks.get(d["id"])
            if t is None:
                t = self.tracks[d["id"]] = {"id": d["id"], "first": idx, "box": d["box"].copy(), "vel": np.zeros(2, np.float32),
                                            "hist": deque(maxlen=maxlen)}
            else:
                if t["hist"].maxlen != maxlen:
                    t["hist"] = deque(t["hist"], maxlen=maxlen)
                prev_c = (t["box"][:2] + t["box"][2:]) / 2
                gap = max(1, idx - t["last"])
                t["box"] = t["box"] * a + d["box"] * (1 - a)
                c = (t["box"][:2] + t["box"][2:]) / 2
                t["vel"] = t["vel"] * 0.5 + ((c - prev_c) / gap) * 0.5
            t.update(cls=d["cls"], name=d["name"], conf=d["conf"], poly=d["poly"], last=idx)
            t["hist"].append(((t["box"][:2] + t["box"][2:]) / 2).copy())
        for k in [k for k, t in self.tracks.items() if idx - t["last"] > 45]:
            del self.tracks[k]

    # -------------------------------------------------------- main entry
    def render(self, frame, idx, fps, p, cache_key=None):
        H, W = frame.shape[:2]
        s = H / 1080.0
        fps = fps or 30.0

        objs = []
        if p["obj_enabled"] or (p["edge_enabled"] and p["exclude_objects"]):
            objs = self._detect(frame, idx, p, cache_key)
            if not self.track:
                objs = [dict(o, first=-10_000, vel=np.zeros(2, np.float32), hist=deque()) for o in objs]

        # base video treatment
        black = p["background"] == "black"
        out = np.zeros_like(frame) if black else self._base(frame, p)
        if p["rain"]:
            self.rain.step(out, p, s, idx)

        ov = np.zeros_like(frame)
        texts = []
        if p["edge_enabled"]:
            self._edges(frame, ov, texts, p, s, objs, idx)
        if p["obj_enabled"]:
            self._objects(ov, texts, objs, p, s, idx)

        out = self._composite(out, ov, p, s)
        for t in texts:
            t(out)
        if p["hud"]:
            self._hud(out, p, s, idx, fps, len(objs) if p["obj_enabled"] else 0)
        if not black:
            out = self._post(out, p, s, idx)
        return out

    # -------------------------------------------------------- layers
    def _base(self, frame, p):
        out = frame
        if p["tint"] > 0:
            g = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            tc = hex2bgr(p["tint_color"])
            tinted = cv2.merge([cv2.convertScaleAbs(g, alpha=c / 255.0) for c in tc])
            out = cv2.addWeighted(frame, 1 - p["tint"], tinted, p["tint"], 0)
        if p["darken"] > 0:
            out = cv2.convertScaleAbs(out, alpha=1 - p["darken"])
        if out is frame:
            out = frame.copy()
        return out

    def _edges(self, frame, ov, texts, p, s, objs, idx):
        H, W = frame.shape[:2]
        ah = int(p["edge_res"])
        k = ah / H
        aw = max(1, int(round(W * k)))
        small = cv2.resize(frame, (aw, ah), interpolation=cv2.INTER_AREA if k < 1 else cv2.INTER_LINEAR)
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        b = int(p["edge_blur"])
        if b > 0:
            b = b | 1
            gray = cv2.GaussianBlur(gray, (b, b), 0)
        e = cv2.Canny(gray, int(p["canny_low"]), int(p["canny_high"]))
        if p["exclude_objects"] and objs:
            pad = 6 * ah / 1080
            for o in objs:
                x1, y1, x2, y2 = o["box"] * k
                cv2.rectangle(e, (int(x1 - pad), int(y1 - pad)), (int(x2 + pad), int(y2 + pad)), 0, -1)

        layer = np.zeros_like(frame)
        base = hex2bgr(p["edge_color"])
        var = p["edge_color_variation"]
        th = max(1, int(round(p["edge_thickness"] * s)))
        mode = p["edge_mode"]

        if mode in ("canny", "both"):
            ef = cv2.resize(e, (W, H), interpolation=cv2.INTER_LINEAR)
            if th > 1:
                ef = cv2.dilate(ef, np.ones((th, th), np.uint8))
            col = scale_col(base, 0.8 if mode == "both" else 1.0)
            cl = cv2.merge([cv2.convertScaleAbs(ef, alpha=c / 255.0) for c in col])
            cv2.max(layer, cl, dst=layer)

        if mode in ("lines", "both"):
            u = ah / 1080.0
            lines = cv2.HoughLinesP(e, 1, np.pi / 180, int(p["hough_thresh"]),
                                    minLineLength=max(2, p["min_line_len"] * u), maxLineGap=p["max_gap"] * u)
            if lines is not None:
                L = np.asarray(lines).reshape(-1, 4).astype(np.float32)
                dx, dy = L[:, 2] - L[:, 0], L[:, 3] - L[:, 1]
                ang = np.degrees(np.arctan2(np.abs(dy), np.abs(dx)))  # 0 = horizontal, 90 = vertical
                tol = p["angle_tol"]
                af = p["angle_filter"]
                if af == "h+v":
                    keep = (ang <= tol) | (ang >= 90 - tol)
                elif af == "vertical":
                    keep = ang >= 90 - tol
                elif af == "horizontal":
                    keep = ang <= tol
                else:
                    keep = np.ones(len(L), bool)
                L = L[keep]
                length = np.hypot(L[:, 2] - L[:, 0], L[:, 3] - L[:, 1])
                L = L[np.argsort(-length)][: int(p["max_lines"])] / k
                ns = max(1, int(round(p["node_size"] * s)))
                lab_p = p["node_labels"]
                tsize = max(6, int(round(p["node_text_size"] * s)))
                cell = 40 * s
                for x1, y1, x2, y2 in L:
                    key = (int(x1 // cell), int(y1 // cell))
                    col = vary(base, key, var)
                    a, bpt = (int(x1), int(y1)), (int(x2), int(y2))
                    cv2.line(layer, a, bpt, col, th, cv2.LINE_AA)
                    if p["nodes"]:
                        for pt in (a, bpt):
                            cv2.rectangle(layer, (pt[0] - ns, pt[1] - ns), (pt[0] + ns, pt[1] + ns), col, -1 if ns <= 2 else max(1, ns // 3))
                    if lab_p > 0 and random.Random(f"{key}").random() < lab_p:
                        txt = f"{a[0]:04d}.{a[1]:04d}"
                        tc = scale_col(col, 1.0)
                        texts.append(lambda img, txt=txt, a=a, tc=tc: TEXT.draw(img, txt, a[0] + ns + 3, a[1] - tsize - 2, tc, tsize, p["font"], 0.9))

        if p["edge_opacity"] < 1:
            layer = cv2.convertScaleAbs(layer, alpha=p["edge_opacity"])
        per = p["persistence"]
        if per > 0 and self.track:
            if self.prev_edge is not None and self.prev_edge.shape == layer.shape:
                cv2.max(layer, cv2.convertScaleAbs(self.prev_edge, alpha=per), dst=layer)
            self.prev_edge = layer
        cv2.max(ov, layer, dst=ov)

    def _obj_color(self, o, p):
        base = hex2bgr(p["box_color"])
        mode = p["color_mode"]
        if mode == "per_class":
            base = hue_of(base, o["name"])
        elif mode == "per_id":
            base = hue_of(base, o["id"] * 7919)
        return vary(base, o["id"], p["color_variation"])

    def _fmt(self, t, p):
        c = p["text_case"]
        return t.upper() if c == "upper" else t.lower() if c == "lower" else t

    def _objects(self, ov, texts, objs, p, s, idx):
        H, W = ov.shape[:2]
        th = max(1, int(round(p["box_thickness"] * s)))
        pad = p["box_pad"] * s
        tsize = max(6, int(round(p["text_size"] * s)))
        font = p["font"]
        cw, chh = TEXT.cell(font, tsize)
        tcol_base = hex2bgr(p["text_color"])
        dec = int(p["decode_frames"])
        rng_frame = random.Random(idx)
        centers = []

        for o in objs:
            col = self._obj_color(o, p)
            x1, y1, x2, y2 = o["box"]
            x1, y1, x2, y2 = int(x1 - pad), int(y1 - pad), int(x2 + pad), int(y2 + pad)
            bw, bh = x2 - x1, y2 - y1
            cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
            centers.append((cx, cy, col, o))

            # trails
            if p["trails"] and self.track and len(o["hist"]) > 1:
                pts = list(o["hist"])
                n = len(pts)
                tt = max(1, int(round(p["trail_thickness"] * s)))
                for i in range(1, n):
                    k = i / n
                    cv2.line(ov, tuple(int(v) for v in pts[i - 1]), tuple(int(v) for v in pts[i]), scale_col(col, k), max(1, int(tt * (0.4 + 0.6 * k))), cv2.LINE_AA)

            # segmentation outline
            poly = o.get("poly")
            if poly is not None and len(poly) > 2 and p["mask_outline"]:
                pts = poly.astype(np.int32).reshape(-1, 1, 2)
                if p["mask_fill"] > 0:
                    fill = np.zeros_like(ov)
                    cv2.fillPoly(fill, [pts], scale_col(col, p["mask_fill"]))
                    cv2.max(ov, fill, dst=ov)
                cv2.polylines(ov, [pts], True, col, max(1, th // 2 + 1), cv2.LINE_AA)

            # box fill
            if p["box_fill"] > 0 and p["box_style"] != "none":
                ox0, oy0, ox1, oy1 = max(x1, 0), max(y1, 0), min(x2, W), min(y2, H)
                if ox1 > ox0 and oy1 > oy0:
                    roi = ov[oy0:oy1, ox0:ox1]
                    cv2.max(roi, np.full_like(roi, scale_col(col, p["box_fill"])), dst=roi)

            style = p["box_style"]
            if style in ("full", "full+corners"):
                c2 = col if style == "full" else scale_col(col, 0.45)
                cv2.rectangle(ov, (x1, y1), (x2, y2), c2, th if style == "full" else max(1, th // 2), cv2.LINE_AA)
            if style in ("corners", "full+corners"):
                lx = int(bw * p["corner_len"])
                ly = int(bh * p["corner_len"])
                ct = th + (1 if style == "full+corners" else 0)
                for (px, py, sx, sy) in ((x1, y1, 1, 1), (x2, y1, -1, 1), (x1, y2, 1, -1), (x2, y2, -1, -1)):
                    cv2.line(ov, (px, py), (px + sx * lx, py), col, ct, cv2.LINE_AA)
                    cv2.line(ov, (px, py), (px, py + sy * ly), col, ct, cv2.LINE_AA)
            if p["crosshair"]:
                cs = int(p["crosshair_size"] * s)
                g = max(2, cs // 3)
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    cv2.line(ov, (cx + dx * g, cy + dy * g), (cx + dx * cs, cy + dy * cs), col, max(1, th // 2), cv2.LINE_AA)

            # label text
            lines = []
            head = []
            if p["show_class"]:
                head.append(self._fmt(o["name"], p))
            if p["show_id"]:
                head.append(f"#{o['id']:03d}")
            if head:
                lines.append(" ".join(head))
            if p["show_conf"]:
                lines.append(self._fmt(f"conf {o['conf']:.2f}", p))
            if p["show_coords"]:
                lines.append(f"X{max(cx, 0):04d} Y{max(cy, 0):04d}")
            if p["show_velocity"]:
                v = float(np.hypot(*o["vel"])) / s
                lines.append(self._fmt(f"vel {v:5.1f}", p))
            if p["show_size"]:
                lines.append(f"{bw}x{bh}")
            nd = int(p["data_lines"])
            if nd:
                fl = p["data_flicker"]
                # change rate: data re-seeds every N frames, N shrinks with flicker
                period = max(1, int(round((1 - fl) * 30))) if fl > 0 else 10 ** 9
                drng = random.Random(f"{o['id']}:{idx // period}")
                for _ in range(nd):
                    lines.append("0x" + "".join(drng.choice(HEXCH) for _ in range(4)) + " " + "".join(drng.choice(HEXCH) for _ in range(4)))
            if not lines:
                continue

            age = idx - o.get("first", -10_000)
            if dec > 0 and age < dec:
                frac = age / dec
                out_lines = []
                for ln in lines:
                    nrev = int(len(ln) * frac)
                    out_lines.append(ln[:nrev] + "".join(rng_frame.choice(SCRAMBLE) if c != " " else " " for c in ln[nrev:]))
                lines = out_lines

            tcol = col if p["text_match_box"] else vary(tcol_base, o["id"], p["color_variation"] * 0.5)
            texts.append(self._label_job(lines, x1, y1, x2, y2, col, tcol, tsize, cw, chh, font, p["text_bg"], s, H, W))

        if p["links"] and len(centers) > 1:
            maxd = p["link_dist"] * s
            lc = hex2bgr(p["link_color"])
            lt = max(1, int(round(p["link_thickness"] * s)))
            lsize = max(6, int(round(p["text_size"] * 0.75 * s)))
            cs = centers[:60]
            for i in range(len(cs)):
                for j in range(i + 1, len(cs)):
                    (ax, ay, _, _), (bx, by, _, _) = cs[i], cs[j]
                    d = math.hypot(bx - ax, by - ay)
                    if d < maxd:
                        k = 1 - d / maxd
                        cv2.line(ov, (ax, ay), (bx, by), scale_col(lc, 0.35 + 0.65 * k), lt, cv2.LINE_AA)
                        if p["link_labels"]:
                            mx, my = (ax + bx) // 2, (ay + by) // 2
                            txt = f"{d / s:.0f}"
                            texts.append(lambda img, txt=txt, mx=mx, my=my: TEXT.draw(img, txt, mx + 4, my - lsize, lc, lsize, font, 0.85))

    @staticmethod
    def _label_job(lines, x1, y1, x2, y2, col, tcol, tsize, cw, chh, font, bg, s, H, W):
        def job(img):
            padx = max(2, int(4 * s))
            lh = int(chh * 1.05)
            w = max(len(l) for l in lines) * cw + padx * 2 + max(2, int(3 * s))
            h = lh * len(lines) + padx
            x = max(0, min(x1, W - w))
            y = y1 - h - max(2, int(4 * s))
            if y < 0:
                y = y2 + max(2, int(4 * s))
                if y + h > H:
                    y = max(0, y1)
            TEXT.panel(img, x, y, w, h, (0, 0, 0), bg)
            bar = max(2, int(3 * s))
            TEXT.panel(img, x, y, bar, h, col, 0.95)
            for i, ln in enumerate(lines):
                TEXT.draw(img, ln, x + bar + padx, y + padx // 2 + i * lh, col if i == 0 else tcol, tsize, font)
        return job

    def _composite(self, out, ov, p, s):
        op = float(p["layer_opacity"])
        if p["glow"] > 0:
            sm = cv2.resize(ov, (max(1, ov.shape[1] // 4), max(1, ov.shape[0] // 4)), interpolation=cv2.INTER_AREA)
            sig = max(0.5, p["glow_radius"] * s / 4)
            sm = cv2.GaussianBlur(sm, (0, 0), sig)
            glow = cv2.resize(sm, (ov.shape[1], ov.shape[0]), interpolation=cv2.INTER_LINEAR)
            out = cv2.addWeighted(out, 1.0, glow, p["glow"] * op * 1.5, 0)
        if op <= 0:
            return out
        if p["blend"] == "add":
            return cv2.addWeighted(out, 1.0, ov, op, 0)
        # "over": alpha derived from overlay intensity
        a = cv2.max(cv2.max(ov[..., 0], ov[..., 1]), ov[..., 2])
        if op < 1:
            a = cv2.convertScaleAbs(a, alpha=op)
        inv = cv2.merge([cv2.bitwise_not(a)] * 3)
        out = cv2.multiply(out, inv, scale=1 / 255.0)
        return cv2.addWeighted(out, 1.0, ov, op, 0)

    def _hud(self, img, p, s, idx, fps, nobj):
        H, W = img.shape[:2]
        col = hex2bgr(p["hud_color"])
        size = max(6, int(round(p["hud_size"] * s)))
        font = p["font"]
        _, ch = TEXT.cell(font, size)
        m = int(24 * s)
        L = int(40 * s)
        th = max(1, int(round(1.5 * s)))
        for (px, py, sx, sy) in ((m, m, 1, 1), (W - m, m, -1, 1), (m, H - m, 1, -1), (W - m, H - m, -1, -1)):
            cv2.line(img, (px, py), (px + sx * L, py), col, th, cv2.LINE_AA)
            cv2.line(img, (px, py), (px, py + sy * L), col, th, cv2.LINE_AA)
        t = idx / fps
        tc = f"T+{int(t // 3600):02d}:{int(t // 60) % 60:02d}:{int(t) % 60:02d}.{int((t % 1) * 100):02d}"
        x0 = m + int(10 * s)
        y0 = m + int(8 * s)
        TEXT.draw(img, p["hud_title"], x0, y0, col, size, font)
        TEXT.draw(img, f"FRM {idx:06d}", x0, y0 + ch, col, size, font, 0.8)
        rec = "● REC" if (idx // max(1, int(fps / 2))) % 2 == 0 else "  REC"
        TEXT.draw(img, rec.replace("●", "*"), W - m - int(10 * s) - TEXT.cell(font, size)[0] * 5, y0, col, size, font)
        TEXT.draw(img, tc, x0, H - m - int(8 * s) - ch * 2, col, size, font, 0.8)
        TEXT.draw(img, f"TRACKS {nobj:03d}  RES {W}x{H}", x0, H - m - int(8 * s) - ch, col, size, font, 0.8)
        rng = random.Random(idx // 3)
        hx = "".join(rng.choice(HEXCH) for _ in range(8))
        txt = f"SYS {hx}"
        TEXT.draw(img, txt, W - m - int(10 * s) - TEXT.cell(font, size)[0] * len(txt), H - m - int(8 * s) - ch, col, size, font, 0.7)

    def _post(self, out, p, s, idx):
        H, W = out.shape[:2]
        if p["vignette"] > 0:
            key = (W, H, round(p["vignette"], 2))
            v = self._vig.get(key)
            if v is None:
                yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
                d = np.sqrt(((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2) / math.sqrt(2)
                m = 1 - p["vignette"] * np.clip(d, 0, 1) ** 2 * 1.3
                m = (np.clip(m, 0, 1) * 255).astype(np.uint8)
                v = cv2.merge([m, m, m])
                self._vig = {key: v}
            out = cv2.multiply(out, v, scale=1 / 255.0)
        return out
