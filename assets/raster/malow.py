"""Malow, the disinfo cat: nyan-like pixel art, facing right. Writes malow.gif.

The head is drawn (one char a colour), the coat follows rules. Each part gets
its own outline, then they stack: tail, legs, body, head.
python assets/raster/malow.py
"""
from pathlib import Path
from PIL import Image

block, step_ms = 8, 70
ink = {
    'O': '#26232a',     # outline
    'G': '#8d8781',     # warm grey hood
    'B': '#7c7168',     # tabby saddle, browner
    'D': '#565049',     # stripes, spine, lids
    'W': '#f2eee6',     # white
    'w': '#d8d2c6',     # white in shade
    'P': '#eda3a6',     # nose, ears
    'Y': '#cfc35a',     # eyes, olive yellow
}

# Big ears set wide and tipped out, a square face: a grey hood to the cheeks,
# the blaze thin at the brow and wide at the muzzle, heavy lids, her pink nose.
head = """
G...............G
GG.............GG
GPG...........GPG
GPPG.........GPPG
.GPPGGGGWGGGGPPG.
.GGGGGGGWGGGGGGG.
.GGGGGGWWWGGGGGG.
.GDDDGGWWWGGDDDG.
.GYOYGGWWWGGYOYG.
.GYOYGWWWWWGYOYG.
.GGGWWWPPPWWWGGG.
"""
# The mouth under the nose, nyan's grin or a small cat's, and her chin.
mouths = {
    'grin': ['.GGWWWWWPWWWWWGG.', '..WWWOWWOWWOWWW..', '...WWOOOOOOOWW...', '....WWWWWWWWW....'],
    'cat': ['.GGWWWWWPWWWWWGG.', '..WWWWWWOWWWWWW..', '...WWWWOWOWWWW...', '....WWWWWWWWW....'],
}


def rounded(x: int, y: int, w: int, h: int, r: float) -> bool:
    dx, dy = max(r - x, x - (w - 1 - r), 0), max(r - y, y - (h - 1 - r), 0)
    return dx * dx + dy * dy <= r * r + 0.5


body_w, body_h = 21, 12


def coat(x: int, y: int) -> str:
    # The saddle: a dark spine, stripes slanting back; white rising to the chest,
    # the hind thigh grey down to the leg.
    w, h = body_w, body_h
    if not rounded(x, y, w, h, 3.5):
        return '.'
    white = round(8 - 6 * max(0, x - 8) ** 1.5 / (w - 9) ** 1.5)
    if 1 < x < 7:
        white = 11
    if y >= white:
        return 'w' if y == h - 1 or x < 2 else 'W'
    if y == 0 or (x - y // 2) % 5 == 0 and 0 < y < white - 1 and x < w - 4:
        return 'D'
    return 'B' if y < 5 else 'G'


body = [''.join(coat(x, y) for x in range(body_w)) for y in range(body_h)]
# Legs: the top two rows go under the body, then a stub and a paw.
hind, front = 'GG.\nGG.\nGG.\nGW.\nWWW', 'WW.\nWW.\nWW.\nWW.\nWWW'
# Tail from the body's back, tip last, raised and curling: three poses; up is
# the one she holds when excited, its tip trembling.
tails = [
    [(0, 0), (-1, 0), (-2, -1), (-3, -2), (-3, -3), (-3, -4), (-3, -5), (-2, -6), (-1, -7)],
    [(0, 0), (-1, 0), (-2, -1), (-3, -1), (-4, -2), (-4, -3), (-4, -4), (-4, -5), (-3, -6)],
    [(0, 0), (-1, 0), (-2, 0), (-3, -1), (-4, -1), (-5, -2), (-5, -3), (-5, -4), (-4, -5)],
    [(0, 0), (-1, -1), (-1, -2), (-2, -3), (-2, -4), (-2, -5), (-2, -6), (-2, -7), (-1, -8)],
]
# A leg's swing: (dx, lift), each leg its own phase: hind, hind, front, front.
swing, phases = [(-1, 0), (0, 1), (1, 1), (1, 0), (0, 0), (-1, 0)], (0, 1, 3, 4)
# Per frame: tail pose, tremble, body bob, head (dx, dy), ear flick.
frames = [
    (0, 0, 0, (0, 0), 0), (1, 0, 0, (0, 0), 0), (2, 0, 1, (1, 0), 0), (1, 0, 1, (1, 1), 0),
    (0, 0, 1, (0, 1), 0), (1, 0, 0, (0, 1), 1), (3, 1, 0, (0, 0), 1), (3, -1, 0, (0, 0), 0),
    (3, 1, 1, (1, 0), 0), (3, -1, 1, (1, 1), 0), (3, 1, 1, (0, 1), 0), (3, 0, 0, (0, 1), 0),
]


def grid(art: str) -> list[str]:
    return art.strip('\n').splitlines()


def outlined(rows: list[str]) -> dict:
    # Fill pixels plus a 4-neighbour outline: {(x, y): char}, padded by one.
    px = {(x + 1, y + 1): c for y, r in enumerate(rows) for x, c in enumerate(r) if c != '.'}
    edge = {(x + dx, y + dy) for x, y in px for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))}
    return {p: 'O' for p in edge - px.keys()} | px


def tail(pose: list, tremble: int = 0) -> tuple[list[str], int, int]:
    # The tip's last three pixels shake by tremble: a micro quiver.
    pose = [(x + tremble * (i >= len(pose) - 3), y) for i, (x, y) in enumerate(pose)]
    xs, ys = [x for x, _ in pose], [y for _, y in pose]
    rows = [['.'] * (max(xs) - min(xs) + 2) for _ in range(max(ys) - min(ys) + 1)]
    for i, (x, y) in enumerate(pose):
        c = 'D' if i % 2 or i >= len(pose) - 2 else 'G'
        rows[y - min(ys)][x - min(xs)] = rows[y - min(ys)][x - min(xs) + 1] = c
    return [''.join(r) for r in rows], min(xs), min(ys)


def face(mouth: str, flick: int) -> list[str]:
    rows = grid(head) + mouths[mouth]
    if flick:
        # The left ear turns back a moment.
        rows[0], rows[1] = '.' + rows[0][1:], '.G' + rows[1][2:]
    return rows


def canvas(w: int, h: int):
    im = Image.new('RGBA', (w, h), (0, 0, 0, 0))

    def put(part: dict, x0: int, y0: int):
        for (x, y), c in part.items():
            im.putpixel((x0 + x, y0 + y), (*bytes.fromhex(ink[c][1:]), 255))
    return im, put


def frame(n: int, mouth: str = 'grin') -> Image.Image:
    pose, tremble, bob, (hx, hy), flick = frames[n]
    im, put = canvas(46, 30)
    bx, by = 7, 10 + bob
    rows, tx, ty = tail(tails[pose], tremble)
    put(outlined(rows), bx + 1 + tx, by + 3 + ty)
    for i, x in enumerate((bx + 3, bx + 7, bx + 13, bx + 17)):
        dx, lift = swing[(n + phases[i]) % len(swing)]
        put(outlined(grid(front if i > 1 else hind)), x + dx, by + body_h - 1 - lift)
    put(outlined(body), bx, by)
    put(outlined(face(mouth, flick)), bx + body_w - 8 + hx, bob + hy)
    return im


# Standing for her food: front-facing, on her hind legs, tiny arms pawing.
stand_w, stand_h = 13, 13


def belly(x: int, y: int) -> str:
    w, h = stand_w, stand_h
    if not rounded(x, y, w, h, 4.5):
        return '.'
    if abs(x - w // 2) <= 2 + y // 4:
        return 'W' if y < h - 1 else 'w'
    if (x + y) % 4 == 0 and 1 < y < h - 2:
        return 'D'
    return 'G'


stand_body = [''.join(belly(x, y) for x in range(stand_w)) for y in range(stand_h)]
# Per frame: left arm up, right arm up, bob, tail tremble, head dy.
stand_frames = [(1, 0, 0, 1, 0), (1, 0, 0, -1, 0), (0, 1, 1, 1, 1), (0, 1, 1, -1, 1), (1, 1, 0, 1, 0), (0, 0, 1, -1, 1)]


def standing(n: int, mouth: str = 'grin') -> Image.Image:
    up_l, up_r, bob, tremble, hy = stand_frames[n]
    im, put = canvas(30, 34)
    bx, by = 9, 15 + bob
    rows, tx, ty = tail(tails[3], tremble)
    put(outlined(rows), bx - 1 + tx, by + stand_h - 2 + ty)
    put(outlined(stand_body), bx, by)
    for x in (bx + 1, bx + stand_w - 3):
        put(outlined(['WWW']), x, by + stand_h)
    put(outlined(face(mouth, 0)), bx - 2, bob + hy)
    for x, up in ((bx + 3, up_l), (bx + stand_w - 5, up_r)):
        arm = {p: c for p, c in outlined(['WW', 'WW', 'ww']).items() if p[1]}     # open at the shoulder
        put(arm, x, by + 3 - up)
    return im


def save(path: Path, frames: list):
    # Cropped to the cat, so her middle is the picture's.
    boxes = [f.getbbox() for f in frames]
    box = min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)
    frames = [f.crop(box) for f in frames]
    big = [f.resize((f.width * block, f.height * block), Image.Resampling.NEAREST) for f in frames]
    big[0].save(path, save_all=True, append_images=big[1:], duration=step_ms, loop=0, disposal=2)


if __name__ == '__main__':
    here = Path(__file__).parent
    save(here / 'malow.gif', [frame(n) for n in range(len(frames))])
    save(here / 'malow-stand.gif', [standing(n) for n in range(len(stand_frames))])
