"""Render the slow demo video: drawing -> generated 3D/2D models -> simulated inspection -> summary.

  1. The OEM engineering drawing of bracket MS-4505-001 (slow zoom).
  2. Each generated model variant: rotating 3D model (STL/GLB) beside its 2D drawing (DXF geometry).
  3. The simulated camera inspection. Every sample frame is sent to the running API exactly as the
     browser does (480 px, JPEG q70); the detections that come back are drawn with the UI's highlight
     style (wireframe outline + colour fill over the defect only). Bracket frames also show the 3D
     model they were generated from. Nothing in the images is pre-marked.
  4. A summary of what was detected.

Run (API on :8000): py scripts/make_demo_video.py [output.mp4]
"""
from __future__ import annotations

import math
import subprocess
import sys
from pathlib import Path

import cv2
import httpx
import imageio_ffmpeg
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import trimesh
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bracket_variants as bv  # noqa: E402
import make_bracket_models as mbm  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
API = "http://localhost:8000/api/v1"
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "docs" / "demo" / "novaliseo_demo.mp4"

W, H, FPS = 1280, 720, 24
INTRO_S, MODEL_S, FRAME_S, OUTRO_S = 7.0, 5.0, 6.0, 8.0
TURN_FPS, TURN_N = 12, 60                 # turntable: 60 azimuth steps shown at 12 renders/second
DETECT_DELAY = 1.0                        # the UI polls about once a second
FEED = 600
COLORS = {"crack": "#ff2d55", "dent": "#ff7a00", "scratch": "#ffd400", "deformation": "#00c2ff", "size_mismatch": "#d946ef"}
BG, PANEL, INK, MUTED = (14, 19, 26), (23, 30, 40), (232, 238, 245), (140, 154, 170)
VARIANTS = ["good", "defect", "crack", "size_mismatch"]
STEP_TITLES = {1: "Step 1 · OEM engineering drawing", 2: "Step 2 · Generated 3D and 2D models",
               3: "Step 3 · Simulated camera, live defect marking", 4: "Step 4 · Summary"}


def font(size, bold=False):
    return ImageFont.truetype(r"C:\Windows\Fonts\segoeuib.ttf" if bold else r"C:\Windows\Fonts\segoeui.ttf", size)


F_H1, F_H2, F_B, F_S, F_L, F_T = font(26, True), font(18, True), font(16), font(13), font(15, True), font(34, True)


def hex_rgb(h):
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def ease(u):
    u = min(1.0, max(0.0, u))
    return 0.5 - 0.5 * math.cos(math.pi * u)


# ---- Pre-rendered assets ------------------------------------------------------------------
def fig_to_array(fig):
    fig.canvas.draw()
    arr = np.asarray(fig.canvas.buffer_rgba())[..., :3].copy()
    plt.close(fig)
    return arr


def render_turntable(v, mesh):
    fine = trimesh.Trimesh(*trimesh.remesh.subdivide_to_size(mesh.vertices, mesh.faces, max_edge=4.0), process=True)
    frames = []
    for i in range(TURN_N):
        fig = plt.figure(figsize=(6.0, 4.4), dpi=100, facecolor="#0e131a")
        ax = fig.add_subplot(111, projection="3d", facecolor="#0e131a")
        fig.subplots_adjust(0, 0, 1, 1)
        mbm.render_3d(ax, fine, v, elev=26, azim=20 + i * 360 / TURN_N, labels=False, max_edge=1e6)
        frames.append(fig_to_array(fig))
    return frames


def render_2d(v):
    fig = plt.figure(figsize=(5.6, 5.9), dpi=100, facecolor="white")
    ax = fig.add_axes([0.02, 0.02, 0.96, 0.96])
    mbm.draw_2d(ax, v, marked=False)
    return fig_to_array(fig)


def describe(v):
    lines = []
    if v.name == "good":
        return ["Nominal geometry: 120 x 80 x 50 mm, 2 mm sheet", "6 x hole dia 12.00 (4 base, 2 flange), bend 90 deg"]
    if v.dents:
        lines.append("Spherical dent, 1 mm deep, near (62, 42) mm")
    if v.scratches:
        lines.append("Scratch groove, 0.9 mm wide, about 47 mm long")
    if abs(v.bend_deg - 90) > 0.01:
        lines.append(f"Flange springback: bend {v.bend_deg:.0f} deg (nominal 90 +/- 0.5)")
    for c in v.cracks:
        lines.append("Through-crack at the edge of a " + ("base" if c["plane"] == "base" else "flange") + " hole")
    if abs(v.length - bv.NOMINAL_L) > 0.01:
        lines.append(f"Length {v.length:.2f} mm (nominal {bv.NOMINAL_L:.2f})")
    for i, ((nx, ny), (x, y, d)) in enumerate(zip(bv.BASE_HOLES, v.base_holes), 1):
        if abs(d - bv.HOLE_D) > 0.01:
            lines.append(f"Base hole {i}: dia {d:.2f} (nominal {bv.HOLE_D:.2f})")
        if math.hypot(x - nx, y - ny) > 0.01:
            lines.append(f"Base hole {i} centre ({x:.1f}, {y:.1f}) vs ({nx:.0f}, {ny:.0f})")
    for i, ((nx, nz), (x, z, d)) in enumerate(zip(bv.FLANGE_HOLES, v.flange_holes), 1):
        if math.hypot(x - nx, z - nz) > 0.01:
            lines.append(f"Flange hole {i} centre X {x:.0f} vs {nx:.0f} mm")
    return lines


def frame_variant(name):
    for key, var in (("good", "good"), ("surface", "defect"), ("crack", "crack"), ("size", "size_mismatch")):
        if f"bracket_{key}" in name:
            return var
    return None


# ---- Scene drawing ------------------------------------------------------------------------
def base_canvas(step, t_total, t_now):
    canvas = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(canvas)
    d.text((40, 24), "NOVALISEO", font=F_H1, fill=INK)
    d.text((196, 31), STEP_TITLES[step], font=F_B, fill=MUTED)
    d.rectangle((0, H - 6, W, H), fill=(30, 38, 50))
    d.rectangle((0, H - 6, int(W * t_now / t_total), H), fill=(90, 150, 220))
    return canvas, d


def intro_scene(drawing, t, total, t_now):
    canvas, d = base_canvas(1, total, t_now)
    u = ease(t / INTRO_S)
    z = 1 + 0.45 * u
    sh, sw = drawing.shape[:2]
    cw, ch = sw / z, sh / z
    cx = sw * (0.5 - 0.20 * u)
    cy = sh * (0.5 - 0.06 * u)
    x0 = int(min(max(cx - cw / 2, 0), sw - cw))
    y0 = int(min(max(cy - ch / 2, 0), sh - ch))
    crop = drawing[y0:y0 + int(ch), x0:x0 + int(cw)]
    crop = cv2.resize(crop, (877, 620), interpolation=cv2.INTER_AREA)
    canvas.paste(Image.fromarray(crop), (40, 84))
    d.rectangle((39, 83, 917, 704), outline=(60, 74, 92), width=2)
    d.rounded_rectangle((940, 84, 1240, 704), 14, fill=PANEL)
    d.text((964, 104), "Bracket MS-4505-001", font=F_H2, fill=INK)
    rows = ["Sheet-metal L-bracket", "SPCC steel, 2.0 mm", "Base 120 x 80 mm", "Flange 50 mm, 90 deg +/-0.5",
            "4 base holes, axis A1 along Z", "2 flange holes, axis A2 along Y", "Hole dia 12.00 +/-0.05",
            "General tolerance +/-0.10 mm"]
    y = 146
    for r in rows:
        d.text((964, y), r, font=F_B, fill=INK)
        y += 32
    d.text((964, 430), "Models generated from this part", font=F_L, fill=(150, 190, 240))
    for i, r in enumerate(["3D: STL and GLB", "2D: DXF (top, front, side)", "4 variants:", "good, surface defects,", "cracked, size mismatch"]):
        d.text((964, 462 + i * 28), r, font=F_B, fill=MUTED)
    return canvas


def model_scene(vname, variants, turns, twod, t, total, t_now):
    canvas, d = base_canvas(2, total, t_now)
    v = variants[vname]
    d.text((40, 76), f"3D MODEL  ·  MS-4505-001_{vname}.stl / .glb", font=F_S, fill=MUTED)
    d.text((680, 76), f"2D MODEL  ·  MS-4505-001_{vname}.dxf", font=F_S, fill=MUTED)
    frame = turns[vname][int(t * TURN_FPS) % TURN_N]
    canvas.paste(Image.fromarray(frame), (40, 100))
    d.rectangle((39, 99, 640, 541), outline=(60, 74, 92), width=2)
    canvas.paste(Image.fromarray(twod[vname]), (680, 100))
    d.rectangle((679, 99, 1241, 691), outline=(60, 74, 92), width=2)
    d.text((40, 556), v.title, font=F_H2, fill=INK)
    y = 592
    for line in describe(v):
        d.text((52, y), "· " + line, font=F_B, fill=MUTED)
        y += 26
    return canvas


def inspect_scene(img_bgr, det, t, idx, total_frames, name, inset, vname, total, t_now):
    canvas, d = base_canvas(3, total, t_now)
    d.rounded_rectangle((1060, 20, 1240, 54), 17, fill=(20, 60, 40))
    d.ellipse((1078, 32, 1090, 44), fill=(60, 220, 120) if int(t * 2) % 2 == 0 else (30, 120, 70))
    d.text((1100, 28), "LIVE", font=F_L, fill=(150, 240, 190))
    fx, fy = 40, 80
    feed = Image.fromarray(cv2.cvtColor(cv2.resize(img_bgr, (FEED, FEED), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2RGB)).convert("RGBA")
    shown = det is not None and t >= DETECT_DELAY
    if shown:
        k = FEED / det["width"]
        fade = min(1.0, (t - DETECT_DELAY) / 0.5)
        layer = Image.new("RGBA", feed.size, (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer)
        for defect in det["defects"]:
            col = hex_rgb(COLORS.get(defect["defect_type"], "#ff3b6b"))
            pts = [(x * k, y * k) for x, y in defect["polygon"]]
            ld.polygon(pts, fill=col + (int(90 * fade),))                              # colour only over the defect
            ld.line(pts + [pts[0]], fill=col + (int(255 * fade),), width=3, joint="curve")   # wireframe outline
            for x, y in pts:
                ld.ellipse((x - 3.5, y - 3.5, x + 3.5, y + 3.5), fill=(255, 255, 255, int(255 * fade)), outline=col + (int(255 * fade),))
        feed = Image.alpha_composite(feed, layer)
        fd = ImageDraw.Draw(feed)
        for defect in det["defects"]:
            col = hex_rgb(COLORS.get(defect["defect_type"], "#ff3b6b"))
            b = defect["bbox"]
            label = f"{defect['defect_type'].replace('_', ' ')} {round(defect['confidence'] * 100)}%"
            w = fd.textlength(label, font=F_L)
            lx = max(4, min(b["x1"] * k, FEED - w - 10))                              # keep labels inside the image
            ly = max(2, b["y1"] * k - 24)
            fd.rounded_rectangle((lx - 4, ly - 1, lx + w + 6, ly + 21), 5, fill=(10, 14, 20, 220))
            fd.text((lx + 1, ly), label, font=F_L, fill=col + (255,))
            if defect.get("note"):
                nw = fd.textlength(defect["note"], font=F_S)
                nx = max(4, min(b["x1"] * k, FEED - nw - 10))
                ny = min(FEED - 22, b["y2"] * k + 4)
                fd.rounded_rectangle((nx - 4, ny - 1, nx + nw + 6, ny + 18), 5, fill=(10, 14, 20, 200))
                fd.text((nx + 1, ny), defect["note"], font=F_S, fill=(235, 240, 246, 255))
    canvas.paste(feed.convert("RGB"), (fx, fy))
    d.rounded_rectangle((fx - 1, fy - 1, fx + FEED, fy + FEED), 4, outline=(60, 74, 92), width=2)
    d.text((fx, fy + FEED + 8), f"{name}   ·   frame {idx + 1} of {total_frames}", font=F_S, fill=MUTED)

    px = 680
    d.rounded_rectangle((px, 80, 1240, 690), 14, fill=PANEL)
    d.text((px + 28, 98), "Inspection result", font=F_H2, fill=INK)
    if not shown:
        d.text((px + 28, 150), "Analysing frame...", font=F_B, fill=MUTED)
    else:
        defects = det["defects"]
        d.rounded_rectangle((px + 28, 136, px + 150, 170), 8, fill=(120, 30, 40) if defects else (20, 80, 50))
        d.text((px + 44, 142), "DEFECTS" if defects else "PASS", font=F_L, fill=(255, 190, 200) if defects else (150, 240, 190))
        d.text((px + 166, 144), f"{len(defects)} found" if defects else "No defects found", font=F_B, fill=INK)
        d.text((px + 28, 182), f"detector: {det['source']}", font=F_S, fill=MUTED)
        y = 212
        for defect in defects[:6]:
            col = hex_rgb(COLORS.get(defect["defect_type"], "#ff3b6b"))
            d.rounded_rectangle((px + 28, y + 4, px + 40, y + 16), 3, fill=col)
            d.text((px + 52, y), f"{defect['defect_type'].replace('_', ' ').title()}  ·  {round(defect['confidence'] * 100)}%", font=F_B, fill=INK)
            if defect.get("note"):
                d.text((px + 52, y + 22), defect["note"], font=F_S, fill=MUTED)
            y += 52
    if inset is not None:
        d.line((px + 28, 440, px + 532, 440), fill=(45, 56, 70), width=1)
        canvas.paste(Image.fromarray(inset), (px + 28, 452))
        d.text((px + 28 + inset.shape[1] + 18, 462), "Generated from the 3D model", font=F_L, fill=(150, 190, 240))
        d.text((px + 28 + inset.shape[1] + 18, 490), f"MS-4505-001_{vname}.stl", font=F_B, fill=INK)
        d.text((px + 28 + inset.shape[1] + 18, 516), variants_title[vname], font=F_S, fill=MUTED)
    d.text((px + 28, 636), "Legend", font=F_S, fill=MUTED)
    lx = px + 28
    for kind, col in COLORS.items():
        d.rounded_rectangle((lx, 660, lx + 12, 672), 3, fill=hex_rgb(col))
        label = kind.replace("_", " ")
        d.text((lx + 18, 655), label, font=F_S, fill=INK)
        lx += 18 + d.textlength(label, font=F_S) + 22
    return canvas


variants_title: dict[str, str] = {}


def outro_scene(results, t, total, t_now):
    canvas, d = base_canvas(4, total, t_now)
    d.text((40, 76), "What was detected, from pixels only", font=F_T, fill=INK)
    d.text((40, 122), "No boxes, labels or annotation files are stored in the images.", font=F_B, fill=MUTED)
    d.rounded_rectangle((40, 160, 1240, 690), 14, fill=PANEL)
    d.text((64, 176), "Frame", font=F_L, fill=(150, 190, 240))
    d.text((520, 176), "Detector", font=F_L, fill=(150, 190, 240))
    d.text((690, 176), "Result", font=F_L, fill=(150, 190, 240))
    y = 212
    shown = min(len(results), int(t / 0.35) + 1)          # rows appear one after another
    for name, source, types in results[:shown]:
        d.text((64, y), name, font=F_S, fill=INK)
        d.text((520, y), source, font=F_S, fill=MUTED)
        if types:
            x = 690
            for kind in dict.fromkeys(types):
                col = hex_rgb(COLORS.get(kind, "#ff3b6b"))
                n = types.count(kind)
                label = f"{kind.replace('_', ' ')} x{n}"
                d.rounded_rectangle((x, y + 2, x + 12, y + 14), 3, fill=col)
                d.text((x + 18, y), label, font=F_S, fill=INK)
                x += 18 + d.textlength(label, font=F_S) + 22
        else:
            d.text((690, y), "no defects (PASS)", font=F_S, fill=(150, 240, 190))
        y += 36
    return canvas


# ---- Main ---------------------------------------------------------------------------------
def detect(client, path: Path):
    img = cv2.imread(str(path))
    small = cv2.resize(img, (480, 480), interpolation=cv2.INTER_AREA)
    jpg = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 70])[1].tobytes()
    r = client.post("/parts/live-detect", files={"image": ("frame.jpg", jpg, "image/jpeg")})
    r.raise_for_status()
    return img, r.json()


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    variants = bv.make_variants()
    variants_title.update({n: v.title for n, v in variants.items()})
    print("rendering 3D turntables and 2D views ...", flush=True)
    meshes = {n: bv.build_mesh(variants[n]) for n in VARIANTS}
    turns = {n: render_turntable(variants[n], meshes[n]) for n in VARIANTS}
    twod = {n: render_2d(variants[n]) for n in VARIANTS}
    drawing = cv2.cvtColor(cv2.imread(str(ROOT / "docs" / "drawings" / "MS-4505-001_bracket.png")), cv2.COLOR_BGR2RGB)
    insets = {n: cv2.resize(turns[n][7], (230, 169), interpolation=cv2.INTER_AREA) for n in VARIANTS}

    client = httpx.Client(base_url=API, timeout=180)
    names = [s["name"] for s in client.get("/demo/samples").json()]
    results, detections = [], []
    for name in names:
        img, det = detect(client, ROOT / "samples" / name)
        detections.append((name, img, det))
        results.append((name, det["source"], [x["defect_type"] for x in det["defects"]]))
        print(name, det["source"], results[-1][2], flush=True)

    total = INTRO_S + MODEL_S * len(VARIANTS) + FRAME_S * len(names) + OUTRO_S
    proc = subprocess.Popen(
        [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", "-preset", "medium", "-movflags", "+faststart", str(OUT)],
        stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)

    def emit(img):
        proc.stdin.write(cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR).tobytes())

    clock = 0.0
    for f in range(int(INTRO_S * FPS)):
        emit(intro_scene(drawing, f / FPS, total, clock + f / FPS))
    clock += INTRO_S
    for vname in VARIANTS:
        for f in range(int(MODEL_S * FPS)):
            emit(model_scene(vname, variants, turns, twod, f / FPS, total, clock + f / FPS))
        clock += MODEL_S
    for i, (name, img, det) in enumerate(detections):
        vname = frame_variant(name)
        for f in range(int(FRAME_S * FPS)):
            emit(inspect_scene(img, det, f / FPS, i, len(detections), name, insets.get(vname), vname, total, clock + f / FPS))
        clock += FRAME_S
    for f in range(int(OUTRO_S * FPS)):
        emit(outro_scene(results, f / FPS, total, clock + f / FPS))
    proc.stdin.close()
    proc.wait()
    print("wrote", OUT, OUT.stat().st_size // 1024, "KB,", round(total), "s")


if __name__ == "__main__":
    main()
