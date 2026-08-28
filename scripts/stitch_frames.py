"""Stitch captured viewer frames into an mp4,.

Pairs with `scripts/frame_capture_server.py`. The page captures its own WebGL
canvas at 2102 x 1484 and POSTs each frame to the sink; this turns a folder of
numbered frames into a video.

ffmpeg comes from `imageio_ffmpeg` (7.1), which is already installed - there is
no system ffmpeg on this machine.

Encoding choices, and why:
  * H.264 yuv420p, because that is what GitHub, Chrome and QuickTime all play
    without a codec argument. A README video that does not autoplay is useless.
  * even dimensions are forced with a scale filter; H.264 rejects odd sizes and
    2102 x 1484 halves to 1051 x 742, which has an odd width.
  * CRF 20 and `-preset slow`: these are short clips, file size matters more
    than encode time, and the scene is mostly flat colour that compresses well.
  * `-movflags +faststart` so the file starts playing before it fully loads.

Run from district_v3:
    python scripts/stitch_frames.py --run sunsweep --fps 24 --width 1600
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import imageio_ffmpeg

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True, help="frame folder name under outputs/frames")
    ap.add_argument("--fps", type=int, default=24)
    ap.add_argument("--width", type=int, default=1600,
                    help="output width; height follows the source aspect")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    src = ROOT / "outputs" / "frames" / a.run
    if not src.exists():
        sys.exit("no such frame folder: %s" % src)
    frames = sorted(list(src.glob("*.jpg")) + list(src.glob("*.png")))
    if not frames:
        sys.exit("no frames in %s" % src)
    ext = frames[0].suffix

    out = Path(a.out) if a.out else (ROOT / "outputs" / "media" / ("%s.mp4" % a.run))
    out.parent.mkdir(parents=True, exist_ok=True)

    exe = imageio_ffmpeg.get_ffmpeg_exe()
    # -2 on the height keeps the aspect ratio AND forces an even number.
    vf = "scale=%d:-2:flags=lanczos" % a.width
    cmd = [
        exe, "-y",
        "-framerate", str(a.fps),
        "-i", str(src / ("%%04d%s" % ext)),
        "-vf", vf,
        "-c:v", "libx264", "-preset", "slow", "-crf", "20",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        str(out),
    ]
    print("frames : %d (%s)" % (len(frames), ext))
    print("output : %s" % out)
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr[-3000:])
        sys.exit("ffmpeg failed (%d)" % r.returncode)
    size = out.stat().st_size
    print("done   : %.1f MB, %.1f s at %d fps"
          % (size / 1e6, len(frames) / a.fps, a.fps))


if __name__ == "__main__":
    main()
