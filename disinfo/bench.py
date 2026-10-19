'''Benchmark: compose and transport, per screen and size.

    DI_CONFIG_PATH=.config-pcstate.json python -m disinfo.bench --size 800x480 --label "..." 2>&1 >/dev/null

Nothing is published. Forced awake unless --as-is. Results append to bench.jsonl, the report is on stderr.
--at "2026-10-19 17:00" runs the screens' clock from that time (the sky, the clocks the same each run);
what comes from Home Assistant (weather, music, printers) is still now's.
'''
import io
import os
import json
import time
import base64
import cProfile
import pstats
import subprocess
import sys

from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
import zlib
import pendulum
from PIL import Image

from discore.data_structures import FrameState
from discore.elements import Frame
from discore.func import uname
from disinfo import compositor
from disinfo.config import app_config, load_config
from disinfo.transport import pack_raw, changed_boxes, pack_regions, RGBZ


def report(line: str):
    print(line, file=sys.stderr, flush=True)

def timed(fn, n: int = 10) -> float:
    fn()
    t = time.perf_counter()
    for _ in range(n):
        fn()
    return (time.perf_counter() - t) / n * 1e3

def pct(xs: list[float], p: float) -> float:
    xs = sorted(xs)
    return xs[min(int(len(xs) * p), len(xs) - 1)]

def png_b64(im: Image.Image) -> str:
    with io.BytesIO() as b:
        im.save(b, format='png')
        return base64.b64encode(b.getvalue()).decode()

def decode_jpeg(b64: str) -> bytes:
    with io.BytesIO(base64.b64decode(b64)) as incoming, io.BytesIO() as out:
        Image.open(incoming).convert('RGB').save(out, format='jpeg', quality=85)
        return out.getvalue()

def micro() -> dict:
    canvas = Image.new('RGBA', (1280, 720), (24, 52, 88, 255))
    return {
        'frame_720p_ms': round(timed(lambda: Frame(canvas), 50), 4),
        'frame_of_pixels_720p_ms': round(timed(lambda: Frame.of_pixels(canvas), 50), 4),
        'uname_us': round(timed(lambda: uname(), 1000) * 1e3, 2),
    }

_clock = None      # (the time asked for, when the run started)

def frame_state(cfg) -> FrameState:
    if not _clock:
        return FrameState.create(cfg)
    at, t0 = _clock
    return FrameState(tick=time.time(), now=at.add(seconds=time.time() - t0), config=cfg)

def bench_screen(cfg, frames: int, warmup: int, fps: float, profile: Optional[cProfile.Profile]) -> dict:
    for _ in range(warmup):
        compositor.compose_frame(frame_state(cfg))
    ts, rgbs = [], []
    for _ in range(frames):
        t = time.perf_counter()
        if profile:
            profile.enable()
        im = compositor.compose_frame(frame_state(cfg))
        if profile:
            profile.disable()
        ts.append((time.perf_counter() - t) * 1e3)
        rgbs.append(im.convert('RGB').tobytes())
        time.sleep(max(1 / fps - ts[-1] / 1e3, 0))
    b64 = png_b64(im)
    raw = pack_raw(cfg.name, im.size, im.convert('RGB').tobytes())
    # /ws2 regions between consecutive frames that changed: sent whole past half the frame.
    pairs = [(a, b) for a, b in zip(rgbs, rgbs[1:]) if a != b]
    diff_ms, region_kb = [], []
    for a, b in pairs:
        t = time.perf_counter()
        boxes = changed_boxes(a, b, im.size)
        msg = pack_regions(b, im.size, boxes, RGBZ) if sum(w * h for *_, w, h in boxes) <= im.size[0] * im.size[1] // 2 else zlib.compress(b, 1)
        diff_ms.append((time.perf_counter() - t) * 1e3)
        region_kb.append(len(msg) / 1024)
    return {
        'screen': cfg.name,
        'size': f'{cfg.width}x{cfg.height}',
        'compose_ms': {'median': round(pct(ts, .5), 2), 'p90': round(pct(ts, .9), 2), 'max': round(max(ts), 2)},
        'png_b64_ms': round(timed(lambda: png_b64(im)), 2),
        'decode_jpeg_ms': round(timed(lambda: decode_jpeg(b64)), 2),
        'png_kb': len(b64) * 3 // 4 // 1024,
        # The transport since /ws2: raw RGB + zlib, inflated by the client.
        'raw_zlib_ms': round(timed(lambda: pack_raw(cfg.name, im.size, im.convert('RGB').tobytes())), 2),
        'rgbz_decode_ms': round(timed(lambda: Image.frombytes('RGB', im.size, zlib.decompress(raw[6 + len(cfg.name):]))), 2),
        'raw_kb': len(raw) // 1024,
        'changed_frames': len(pairs),
        'region_kb': round(pct(region_kb, .5), 2) if pairs else 0,
        'regions_ms': round(pct(diff_ms, .5), 2) if pairs else 0,
    }

def main(
    config: Optional[list[str]] = None,
    size: Optional[list[str]] = None,
    frames: int = 120,
    warmup: int = 30,
    fps: float = 12,
    as_is: bool = False,
    profile: bool = False,
    label: str = '',
    at: str = '',
    log: Path = Path('bench.jsonl'),
):
    # --config and --size can be repeated.
    global _clock
    if at:
        _clock = (pendulum.parse(at, tz=pendulum.local_timezone()), time.time())
    if not as_is:
        compositor.should_turn_on_display = lambda fs: True
    configs = [load_config(c) for c in config or []] or [app_config]
    sizes = [tuple(int(v) for v in s.split('x')) for s in size or []]
    prof = cProfile.Profile() if profile else None

    results = []
    for c in configs:
        for w, h in sizes or [(c.width, c.height)]:
            r = bench_screen(c.model_copy(update={'width': w, 'height': h}), frames, warmup, fps, prof)
            results.append(r)
            ms = r['compose_ms']
            report(f"{r['screen']:12} {r['size']:>9}  compose {ms['median']:6.2f} ms  p90 {ms['p90']:6.2f}  max {ms['max']:7.2f}"
                   f"  | png+b64 {r['png_b64_ms']:6.2f}  decode+jpeg {r['decode_jpeg_ms']:6.2f}  ({r['png_kb']} KB)"
                   f"  | raw+zlib {r['raw_zlib_ms']:5.2f}  inflate {r['rgbz_decode_ms']:5.2f}  ({r['raw_kb']} KB)"
                   f"  | regions {r['regions_ms']:5.2f} ms  {r['region_kb']} KB  ({r['changed_frames']} changed)")
    m = micro()
    report(f"Frame(720p) {m['frame_720p_ms']} ms   Frame.of_pixels(720p) {m['frame_of_pixels_720p_ms']} ms   uname() {m['uname_us']} us")

    if prof:
        pstats.Stats(prof, stream=sys.stderr).sort_stats('cumtime').print_stats(25)

    rev = subprocess.run(['git', 'rev-parse', '--short', 'HEAD'], capture_output=True, text=True).stdout.strip()
    dirty = bool(subprocess.run(['git', 'status', '--porcelain'], capture_output=True, text=True).stdout.strip())
    entry = {'at': datetime.now().isoformat(timespec='seconds'), 'rev': rev + ('+' if dirty else ''), 'label': label,
             'frames': frames, 'awake': not as_is, 'clock': at or None, 'screens': results, 'micro': m}
    with log.open('a') as f:
        f.write(json.dumps(entry) + '\n')
    report(f'logged to {log}')
    os._exit(0)     # client threads hold the exit


if __name__ == '__main__':
    typer.run(main)
