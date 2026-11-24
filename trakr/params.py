"""Parameter schema. The web UI builds its controls from this list.

All pixel-ish sizes are in "1080p units": they get scaled by (frame_height / 1080)
at render time, so a low-res preview looks the same as the 4K export.
"""

MODELS = ["yolo11n.pt", "yolo11s.pt", "yolo11m.pt", "yolo11n-seg.pt", "yolo11s-seg.pt"]
FONTS = ["Consolas", "Menlo", "Cascadia Mono", "Courier New", "Lucida Console"]


def _r(key, label, default, lo, hi, step):
    return {"key": key, "label": label, "type": "range", "default": default, "min": lo, "max": hi, "step": step}


def _b(key, label, default):
    return {"key": key, "label": label, "type": "bool", "default": default}


def _c(key, label, default):
    return {"key": key, "label": label, "type": "color", "default": default}


def _s(key, label, default, options):
    return {"key": key, "label": label, "type": "select", "default": default, "options": options}


def _t(key, label, default):
    return {"key": key, "label": label, "type": "text", "default": default}


SCHEMA = [
    {"group": "detection", "title": "DETECTION", "fields": [
        _s("model", "model", "yolo11n.pt", MODELS),
        _s("device", "compute device", "auto", ["auto", "mps", "cuda", "cpu"]),
        _r("conf", "confidence", 0.35, 0.05, 0.95, 0.01),
        _s("imgsz", "inference size", 640, [320, 480, 640, 960, 1280]),
        _t("classes", "classes (blank = all)", ""),
        _r("detect_every", "detect every N frames", 1, 1, 6, 1),
        _r("smoothing", "box smoothing", 0.4, 0, 0.9, 0.05),
    ]},
    {"group": "objects", "title": "OBJECT LAYER", "toggle": "obj_enabled", "fields": [
        _b("obj_enabled", "enabled", True),
        _s("box_style", "box style", "corners", ["corners", "full", "full+corners", "none"]),
        _c("box_color", "box color", "#ffffff"),
        _s("color_mode", "color mode", "single", ["single", "per_class", "per_id"]),
        _r("color_variation", "color variation", 0, 0, 1, 0.01),
        _r("box_thickness", "line thickness", 2, 1, 10, 1),
        _r("corner_len", "corner length", 0.22, 0.05, 0.5, 0.01),
        _r("box_pad", "box padding", 4, 0, 40, 1),
        _r("box_fill", "box fill", 0, 0, 0.6, 0.01),
        _b("mask_outline", "mask outline (seg models)", True),
        _r("mask_fill", "mask fill", 0.12, 0, 0.6, 0.01),
        _b("crosshair", "center crosshair", True),
        _r("crosshair_size", "crosshair size", 10, 2, 60, 1),
    ]},
    {"group": "text", "title": "LABELS / TEXT", "fields": [
        _s("font", "font", "Consolas", FONTS),
        _r("text_size", "text size", 16, 6, 64, 1),
        _c("text_color", "text color", "#ffffff"),
        _b("text_match_box", "text matches box color", False),
        _r("text_bg", "label bg opacity", 0.55, 0, 1, 0.01),
        _s("text_case", "case", "upper", ["upper", "lower", "as-is"]),
        _b("show_class", "class name", True),
        _b("show_id", "track id", True),
        _b("show_conf", "confidence", True),
        _b("show_coords", "coordinates", True),
        _b("show_velocity", "velocity", False),
        _b("show_size", "box size", False),
        _r("data_lines", "hex data lines", 1, 0, 8, 1),
        _r("data_flicker", "data flicker", 0.25, 0, 1, 0.01),
        _r("decode_frames", "decode-in frames", 14, 0, 60, 1),
    ]},
    {"group": "trails", "title": "TRAILS / LINKS", "fields": [
        _b("trails", "motion trails", True),
        _r("trail_len", "trail length", 30, 2, 150, 1),
        _r("trail_thickness", "trail thickness", 2, 1, 10, 1),
        _b("links", "link nearby objects", False),
        _r("link_dist", "link max distance", 400, 50, 1800, 10),
        _c("link_color", "link color", "#ffffff"),
        _r("link_thickness", "link thickness", 1, 1, 6, 1),
        _b("link_labels", "link distance labels", True),
    ]},
    {"group": "edges", "title": "EDGE / BUILDING LAYER", "toggle": "edge_enabled", "fields": [
        _b("edge_enabled", "enabled", False),
        _s("edge_mode", "mode", "lines", ["lines", "canny", "both"]),
        _s("edge_res", "analysis resolution", 720, [360, 540, 720, 1080]),
        _r("edge_blur", "pre-blur", 5, 0, 21, 1),
        _r("canny_low", "canny low", 60, 0, 255, 1),
        _r("canny_high", "canny high", 160, 0, 255, 1),
        _r("hough_thresh", "line votes", 50, 5, 250, 1),
        _r("min_line_len", "min line length", 80, 5, 800, 5),
        _r("max_gap", "max line gap", 8, 0, 60, 1),
        _s("angle_filter", "angle filter", "h+v", ["all", "h+v", "vertical", "horizontal"]),
        _r("angle_tol", "angle tolerance", 12, 1, 45, 1),
        _r("max_lines", "max lines", 400, 10, 3000, 10),
        _b("exclude_objects", "skip detected objects", True),
        _c("edge_color", "line color", "#ffffff"),
        _r("edge_color_variation", "color variation", 0, 0, 1, 0.01),
        _r("edge_thickness", "line thickness", 1, 1, 8, 1),
        _r("edge_opacity", "opacity", 0.85, 0, 1, 0.01),
        _b("nodes", "endpoint nodes", True),
        _r("node_size", "node size", 3, 1, 15, 1),
        _r("node_labels", "node coord labels", 0.04, 0, 0.5, 0.01),
        _r("node_text_size", "node text size", 11, 6, 40, 1),
        _r("persistence", "persistence", 0.5, 0, 0.95, 0.01),
    ]},
    {"group": "post", "title": "POST FX", "fields": [
        _s("background", "background", "video", ["video", "black"]),
        _s("blend", "overlay blend", "over", ["over", "add"]),
        _r("layer_opacity", "overlay opacity", 1.0, 0, 1, 0.01),
        _r("glow", "glow", 0.3, 0, 3, 0.05),
        _r("glow_radius", "glow radius", 10, 1, 60, 1),
        _r("darken", "darken video", 0, 0, 0.95, 0.01),
        _r("tint", "tint amount", 0, 0, 1, 0.01),
        _c("tint_color", "tint color", "#ffffff"),
        _r("vignette", "vignette", 0, 0, 1, 0.01),
    ]},
    {"group": "hud", "title": "HUD / TITLE / CODE RAIN", "fields": [
        _b("hud", "HUD overlay", True),
        _t("hud_title", "title text", "OBJ//TRAKR"),
        _c("hud_color", "HUD color", "#ffffff"),
        _r("hud_size", "HUD text size", 14, 6, 48, 1),
        _b("rain", "code rain", False),
        _r("rain_density", "rain density", 0.35, 0.02, 1, 0.01),
        _r("rain_speed", "rain speed", 1.0, 0.1, 4, 0.05),
        _r("rain_size", "rain glyph size", 16, 6, 48, 1),
        _r("rain_opacity", "rain opacity", 0.35, 0, 1, 0.01),
        _c("rain_color", "rain color", "#ffffff"),
    ]},
]


def defaults():
    return {f["key"]: f["default"] for g in SCHEMA for f in g["fields"]}


_TYPES = {f["key"]: f for g in SCHEMA for f in g["fields"]}


def coerce(p):
    """Merge user params onto defaults with type coercion."""
    out = defaults()
    for k, v in (p or {}).items():
        f = _TYPES.get(k)
        if not f:
            continue
        try:
            if f["type"] == "range":
                v = float(v)
                v = min(max(v, f["min"]), f["max"])
                if float(f["step"]).is_integer():
                    v = int(round(v))
            elif f["type"] == "bool":
                v = bool(v) if not isinstance(v, str) else v.lower() in ("1", "true", "on", "yes")
            elif f["type"] == "select":
                opts = f["options"]
                if isinstance(opts[0], int):
                    v = int(v)
                if v not in opts:
                    continue
            else:
                v = str(v)
        except (TypeError, ValueError):
            continue
        out[k] = v
    return out
