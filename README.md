# OBJ//TRAKR

Futuristic object tracking + building-edge tracing overlay for any video, with a live-tweakable web UI and export up to 4K.
It runs locally and nothing gets uploaded anywhere: the "web app" is just a page served from your own machine.

- **Object layer**: YOLO11 detection + ByteTrack IDs, with corner/full boxes, monospace labels, decode-in text, hex data,
  motion trails, links between objects and segmentation outlines
- **Edge / building layer**: straight-line tracing (Canny + Hough), with an angle filter tuned for architecture,
  endpoint nodes and coordinate readouts
- **Export**: H.264 / H.265 mp4 or ProRes 422 HQ mov, up to 4K. Either a composite (video + FX) or the
  **FX layer on black** to use as a Screen/Add layer in your own edit

---

## Install & run

You need **Python 3.9–3.12** (3.12 recommended). The first launch creates a private environment in `.venv/` and
downloads about 1 GB of dependencies, so it takes a few minutes. Later launches start in seconds.
Detection models (~6–40 MB each) download automatically the first time you use them.

### macOS (Apple Silicon or Intel)

1. Install Python 3.12 from https://www.python.org/downloads/macos/ (or `brew install python@3.12`).
2. Download this repo: **Code → Download ZIP** and unzip it, or `git clone`.
3. Open **Terminal**, type `bash ` (with a trailing space), drag the `run.command` file into the window and press Enter.
   It opens http://127.0.0.1:7860 in your browser when it's ready.

> Double-clicking `run.command` also works if it's executable. If macOS says it "cannot be opened",
> run `chmod +x run.command` once, or just keep using the Terminal command above.

**Apple Silicon (M1–M4):** detection runs on the GPU through Metal (MPS), using the Mac's unified memory. No separate
VRAM is needed. The status bar under the preview should read `DEVICE APPLE GPU (MPS) [auto]`. 8 GB Macs are fine
with the `n` and `s` models. Use `yolo11m` on 16 GB or more.

### Windows

1. Install Python 3.12 from https://www.python.org/downloads/ (tick **"Add python.exe to PATH"**).
2. Download / clone this repo and double-click **`run.bat`**.

It installs the CPU build of PyTorch by default. With an NVIDIA GPU, edit `run.bat` and change `whl/cpu` to
`whl/cu124` before the first run (or delete `.venv` and run it again) to get CUDA acceleration.

### Linux

`bash run.command`. The same script works on Linux.

---

## Use

- **LOAD FILE**, drag a video onto the viewport, or paste a local file path. Pasting a path is best for big 4K files because it skips the copy.
- Scrub the timeline to preview a single frame. Every slider re-renders it immediately.
- **Space** plays a live tracked preview. Changes apply while it plays. **←/→** steps frames (Shift = 10), and **I / O** set in/out points.
- Presets: built-ins, plus save/load your own (stored in your browser) and import/export them as `.json` to share looks with friends.
- Double-click a parameter label to reset it. **↺** resets a whole group.
- **Export** renders at full source quality (or a chosen resolution) to the `exports/` folder, keeping the source audio.
  Set **output → fx layer on black** to get a compositing layer (the file name gets `_layer`).

Sizes are defined at 1080p and scale with the output resolution, so what you see in the preview matches the 4K export.

## Speed

| machine | 1080p, all layers | 4K export, all layers |
|---|---|---|
| Windows CPU (i7/i9 class) | ~10 fps | ~3 fps |
| Apple Silicon (MPS) | faster: detection moves to the GPU | |

To speed things up: raise `detect every N frames`, lower `inference size`, or use a lower preview resolution.
**compute device** (in DETECTION) lets you force `cpu`, `mps` or `cuda`. On `auto` it picks the best one available.

## Troubleshooting

- **"Python 3.9 - 3.12 is required"**: install 3.12 (see above). Python 3.13+ is not supported by all dependencies yet.
- **Broken or half-finished install**: delete the `.venv` folder and launch again.
- **Port already in use**: `PORT=7861 bash run.command` (Mac/Linux), or edit the port at the bottom of `app.py`.
- **Text looks different from a friend's**: fonts come from the OS (Consolas/Cascadia on Windows, SF Mono/Menlo on Mac).
  To force an identical look everywhere, drop a `.ttf` such as `JetBrainsMono-Regular.ttf` into a `fonts/` folder and add it to
  `FONT_FILES` in `trakr/textfx.py`.
