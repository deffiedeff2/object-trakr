"""OBJ//TRAKR web app: live-tweakable object tracking + edge tracing overlay for video."""
import os

# Apple Silicon: let any op MPS lacks fall back to CPU instead of crashing.
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
import subprocess
import threading
import time
import uuid
from collections import OrderedDict

import cv2
from flask import Flask, Response, abort, jsonify, request, send_file, send_from_directory

from trakr.engine import Renderer, available_devices, resolve_device
from trakr.params import SCHEMA, coerce, defaults

ROOT = os.path.dirname(os.path.abspath(__file__))
UPLOADS = os.path.join(ROOT, "uploads")
EXPORTS = os.path.join(ROOT, "exports")
os.makedirs(UPLOADS, exist_ok=True)
os.makedirs(EXPORTS, exist_ok=True)

app = Flask(__name__, static_folder="static", static_url_path="/static")

VIDEOS = {}
PARAMS = {"p": defaults()}
STREAM = {"token": 0, "pos": 0, "fps_actual": 0.0}
JOBS = {}
PREVIEW_LOCK = threading.Lock()
PREVIEW = Renderer(track=False)
PREVIEW.det_cache = {}
FRAME_CACHE = OrderedDict()


def ffmpeg_exe():
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def probe(path):
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        return None
    info = {
        "w": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
        "h": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
        "fps": cap.get(cv2.CAP_PROP_FPS) or 30.0,
        "n": int(cap.get(cv2.CAP_PROP_FRAME_COUNT)),
    }
    cap.release()
    return info


def register(path, name=None):
    info = probe(path)
    if not info:
        return None
    vid = uuid.uuid4().hex[:10]
    VIDEOS[vid] = dict(info, path=path, name=name or os.path.basename(path), id=vid)
    return VIDEOS[vid]


def fit(frame, ph):
    h, w = frame.shape[:2]
    if ph and h > ph:
        nw = int(round(w * ph / h)) // 2 * 2
        frame = cv2.resize(frame, (nw, ph), interpolation=cv2.INTER_AREA)
    return frame


def get_frame(vid, f, ph):
    key = (vid, f, ph)
    if key in FRAME_CACHE:
        FRAME_CACHE.move_to_end(key)
        return FRAME_CACHE[key]
    v = VIDEOS[vid]
    cap = cv2.VideoCapture(v["path"])
    cap.set(cv2.CAP_PROP_POS_FRAMES, f)
    ok, frame = cap.read()
    cap.release()
    if not ok:
        return None
    frame = fit(frame, ph)
    FRAME_CACHE[key] = frame
    if len(FRAME_CACHE) > 12:
        FRAME_CACHE.popitem(last=False)
    return frame


# ------------------------------------------------------------------ routes
@app.get("/")
def index():
    return send_from_directory(os.path.join(ROOT, "static"), "index.html")


@app.get("/api/schema")
def schema():
    return jsonify({"schema": SCHEMA, "params": PARAMS["p"], "devices": available_devices(),
                    "auto_device": resolve_device("auto")})


@app.post("/api/params")
def set_params():
    PARAMS["p"] = coerce(request.get_json(force=True))
    return jsonify(ok=True)


@app.post("/api/upload")
def upload():
    f = request.files.get("file")
    if not f:
        abort(400)
    name = os.path.basename(f.filename or "video.mp4")
    path = os.path.join(UPLOADS, f"{uuid.uuid4().hex[:8]}_{name}")
    f.save(path)
    v = register(path, name)
    if not v:
        return jsonify(error="could not open video"), 400
    return jsonify(v)


@app.post("/api/open")
def open_path():
    path = (request.get_json(force=True) or {}).get("path", "").strip().strip('"')
    if not os.path.isfile(path):
        return jsonify(error="file not found"), 400
    v = register(path)
    if not v:
        return jsonify(error="could not open video"), 400
    return jsonify(v)


@app.post("/api/frame")
def frame():
    d = request.get_json(force=True)
    vid, f, ph = d["vid"], int(d.get("f", 0)), int(d.get("ph", 720))
    if vid not in VIDEOS:
        abort(404)
    p = coerce(d.get("params"))
    with PREVIEW_LOCK:
        img = get_frame(vid, f, ph)
        if img is None:
            abort(404)
        t = time.perf_counter()
        out = PREVIEW.render(img, f, VIDEOS[vid]["fps"], p, cache_key=(vid, f, ph))
        ms = (time.perf_counter() - t) * 1000
    ok, buf = cv2.imencode(".jpg", out, [cv2.IMWRITE_JPEG_QUALITY, 95])
    return Response(buf.tobytes(), mimetype="image/jpeg", headers={"X-Render-Ms": f"{ms:.0f}"})


@app.post("/api/stop")
def stop():
    STREAM["token"] += 1
    return jsonify(pos=STREAM["pos"])


@app.get("/api/status")
def status():
    return jsonify(pos=STREAM["pos"], fps=round(STREAM["fps_actual"], 1))


@app.get("/api/stream")
def stream():
    vid = request.args["vid"]
    start = int(request.args.get("f", 0))
    ph = int(request.args.get("ph", 720))
    if vid not in VIDEOS:
        abort(404)
    STREAM["token"] += 1
    token = STREAM["token"]
    v = VIDEOS[vid]

    def gen():
        r = Renderer(track=True)
        cap = cv2.VideoCapture(v["path"])
        cap.set(cv2.CAP_PROP_POS_FRAMES, start)
        idx = start
        frame_dt = 1.0 / (v["fps"] or 30)
        t_next = time.perf_counter()
        ema = None
        try:
            while STREAM["token"] == token:
                t0 = time.perf_counter()
                ok, img = cap.read()
                if not ok:  # loop
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    idx = 0
                    r = Renderer(track=True)
                    continue
                img = fit(img, ph)
                out = r.render(img, idx, v["fps"], PARAMS["p"])
                ok, buf = cv2.imencode(".jpg", out, [cv2.IMWRITE_JPEG_QUALITY, 92])
                STREAM["pos"] = idx
                dt = time.perf_counter() - t0
                if idx != start:  # first frame includes model load
                    ema = dt if ema is None else ema * 0.9 + dt * 0.1
                    STREAM["fps_actual"] = 1.0 / max(ema, 1e-3)
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + buf.tobytes() + b"\r\n"
                idx += 1
                t_next += frame_dt
                wait = t_next - time.perf_counter()
                if wait > 0:
                    time.sleep(wait)
                else:
                    t_next = time.perf_counter()
        finally:
            cap.release()

    return Response(gen(), mimetype="multipart/x-mixed-replace; boundary=frame",
                    headers={"Cache-Control": "no-cache"})


# ------------------------------------------------------------------ export
def run_export(job):
    v = VIDEOS[job["vid"]]
    p = job["params"]
    cap = cv2.VideoCapture(v["path"])
    W, H = v["w"], v["h"]
    oh = job["out_h"]
    if oh and oh != H:
        W, H = int(round(W * oh / H)) // 2 * 2, oh // 2 * 2
    else:
        W, H = W // 2 * 2, H // 2 * 2
    fps = v["fps"]
    start, end = job["start"], job["end"]
    cap.set(cv2.CAP_PROP_POS_FRAMES, start)

    codec = job["codec"]
    ext = ".mov" if codec == "prores" else ".mp4"
    base = os.path.splitext(v["name"])[0]
    out_path = os.path.join(EXPORTS, f"{base}_trakr{'_layer' if p['background'] == 'black' else ''}_{time.strftime('%Y%m%d-%H%M%S')}_{H}p{ext}")
    vcodec = {
        "h264": ["-c:v", "libx264", "-preset", job["preset"], "-crf", str(job["crf"]), "-pix_fmt", "yuv420p"],
        "h265": ["-c:v", "libx265", "-preset", job["preset"], "-crf", str(job["crf"]), "-pix_fmt", "yuv420p", "-tag:v", "hvc1"],
        "prores": ["-c:v", "prores_ks", "-profile:v", "3", "-pix_fmt", "yuv422p10le"],
    }[codec]
    cmd = [ffmpeg_exe(), "-y", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}", "-r", f"{fps}", "-i", "-",
           "-ss", f"{start / fps:.3f}", "-t", f"{(end - start) / fps:.3f}", "-i", v["path"],
           "-map", "0:v", "-map", "1:a?", *vcodec, "-c:a", "aac", "-b:a", "192k", "-shortest",
           "-movflags", "+faststart", out_path]
    log = open(out_path + ".log", "w")
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=log)
    r = Renderer(track=True)
    job.update(status="rendering", path=out_path, size=f"{W}x{H}")
    t0 = time.perf_counter()
    try:
        for idx in range(start, end):
            if job["cancel"]:
                job["status"] = "cancelled"
                break
            ok, img = cap.read()
            if not ok:
                break
            if img.shape[0] != H or img.shape[1] != W:
                img = cv2.resize(img, (W, H), interpolation=cv2.INTER_AREA if H < img.shape[0] else cv2.INTER_CUBIC)
            out = r.render(img, idx, fps, p)
            proc.stdin.write(out.tobytes())
            done = idx - start + 1
            el = time.perf_counter() - t0
            job.update(done=done, fps=done / el, eta=(job["total"] - done) / max(done / el, 1e-6))
        proc.stdin.close()
        proc.wait()
        log.close()
        if job["status"] == "cancelled":
            try:
                os.remove(out_path)
            except OSError:
                pass
        elif proc.returncode != 0:
            job.update(status="error", error=open(out_path + ".log").read()[-800:])
        else:
            job["status"] = "done"
            try:
                os.remove(out_path + ".log")
            except OSError:
                pass
    except Exception as e:  # noqa: BLE001
        job.update(status="error", error=str(e))
        try:
            proc.kill()
        except Exception:  # noqa: BLE001
            pass
    finally:
        cap.release()


@app.post("/api/export")
def export():
    d = request.get_json(force=True)
    vid = d["vid"]
    if vid not in VIDEOS:
        abort(404)
    v = VIDEOS[vid]
    n = v["n"] or 1
    start = max(0, int(d.get("start", 0)))
    end = min(n, int(d.get("end", n)) or n)
    if end <= start:
        end = n
    out_h = d.get("out_h", "source")
    job = {
        "id": uuid.uuid4().hex[:8], "vid": vid, "params": coerce(d.get("params")),
        "out_h": None if out_h == "source" else int(out_h), "codec": d.get("codec", "h264"),
        "crf": int(d.get("crf", 18)), "preset": d.get("preset", "medium"),
        "start": start, "end": end, "total": end - start, "done": 0, "fps": 0, "eta": 0,
        "status": "starting", "cancel": False, "error": None,
    }
    JOBS[job["id"]] = job
    threading.Thread(target=run_export, args=(job,), daemon=True).start()
    return jsonify(id=job["id"])


@app.get("/api/export/<jid>")
def export_status(jid):
    j = JOBS.get(jid) or abort(404)
    return jsonify({k: j[k] for k in ("id", "status", "done", "total", "fps", "eta", "error") if k in j} |
                   {"file": os.path.basename(j.get("path", "")), "size": j.get("size")})


@app.post("/api/export/<jid>/cancel")
def export_cancel(jid):
    j = JOBS.get(jid) or abort(404)
    j["cancel"] = True
    return jsonify(ok=True)


@app.get("/api/download/<jid>")
def download(jid):
    j = JOBS.get(jid) or abort(404)
    if j["status"] != "done":
        abort(409)
    return send_file(j["path"], as_attachment=True)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    print(f"\n  OBJ//TRAKR running -> http://127.0.0.1:{port}\n")
    app.run(host="127.0.0.1", port=port, threaded=True, debug=False)
