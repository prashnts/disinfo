'''Shapes for the map: fewer points, only 0/45/90... degree edges, rounded corners. Points are (x, y) in km.'''
import math

from collections import defaultdict


def simplify(pts: list, tol: float) -> list:
    # Douglas-Peucker. A ring (first == last) works too: the first point is the anchor.
    if len(pts) < 3:
        return list(pts)
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    todo = [(0, len(pts) - 1)]
    while todo:
        a, b = todo.pop()
        (ax, ay), (bx, by) = pts[a], pts[b]
        dx, dy = bx - ax, by - ay
        n = math.hypot(dx, dy)
        far, at = 0, None
        for i in range(a + 1, b):
            px, py = pts[i][0] - ax, pts[i][1] - ay
            d = math.hypot(px, py) if n == 0 else abs(px * dy - py * dx) / n
            if d > far:
                far, at = d, i
        if at is not None and far > tol:
            keep[at] = True
            todo += [(a, at), (at, b)]
    return [p for p, k in zip(pts, keep) if k]

def octilinear(pts: list, closed: bool = False) -> list:
    '''Each edge becomes a diagonal and a straight leg. Ends on the original points, so it doesn't drift.

    The leg that continues the way the path was going goes first, which keeps the bends few.
    '''
    n = len(pts)
    out = [pts[0]]
    last = None     # the direction of the last leg: (sign x, sign y)
    for i in range(1, n + (1 if closed else 0)):
        (ax, ay), (bx, by) = out[-1], pts[i % n]
        dx, dy = bx - ax, by - ay
        sx, sy = (dx > 0) - (dx < 0), (dy > 0) - (dy < 0)
        d = min(abs(dx), abs(dy))
        if d > 1e-9 and abs(abs(dx) - abs(dy)) > 1e-9:
            major = (sx, 0) if abs(dx) > abs(dy) else (0, sy)
            # Straight first when the path was going that way.
            first_straight = last == major
            out.append((bx - sx * d, by - sy * d) if first_straight else (ax + sx * d, ay + sy * d))
            last = (sx, sy) if first_straight else major
        else:
            last = (sx, sy)
        out.append((bx, by))
    if closed and out[-1] == out[0]:
        out.pop()
    return tidy(out, closed)

def tidy(pts: list, closed: bool = False) -> list:
    # Without the repeated points and the ones in the middle of a straight edge.
    out = []
    for p in pts:
        if not out or math.dist(p, out[-1]) > 1e-9:
            out.append(p)
    changed = True
    while changed and len(out) > 2:
        changed = False
        m = len(out)
        for i in range(0 if closed else 1, m if closed else m - 1):
            (ax, ay), (bx, by), (cx, cy) = out[i - 1], out[i], out[(i + 1) % m]
            if abs((bx - ax) * (cy - by) - (by - ay) * (cx - bx)) < 1e-9 * max(1, math.dist(out[i - 1], out[i])):
                del out[i]
                changed = True
                break
    return out

def area(ring: list) -> float:
    return abs(sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(ring, ring[1:] + ring[:1]))) / 2

def length(line: list) -> float:
    return sum(math.dist(a, b) for a, b in zip(line, line[1:]))

def chains(segs: list[list]) -> list[list]:
    # Ways that meet end to end, joined: the pieces of a river, the sides of a lake's relation. Closed ones end where they start.
    ends = defaultdict(list)
    for i, s in enumerate(segs):
        ends[s[0]].append(i)
        ends[s[-1]].append(i)
    used, out = set(), []
    for i, s in enumerate(segs):
        if i in used:
            continue
        used.add(i)
        c = list(s)
        for _ in range(2):
            while c[0] != c[-1] or len(c) < 3:
                j = next((j for j in ends[c[-1]] if j not in used), None)
                if j is None:
                    break
                used.add(j)
                t = segs[j]
                c.extend((t if t[0] == c[-1] else t[::-1])[1:])
            c.reverse()
        out.append(c)
    return out

def rounded(ctx, pts: list, closed: bool, r: float):
    # The path through the points, the corners cut (at most r, or half of the edge) and rounded.
    pts = tidy(pts, closed)
    n = len(pts)
    if n < (3 if closed else 2):
        return
    def corner(i):
        v = pts[i]
        p, q = pts[(i - 1) % n], pts[(i + 1) % n]
        lp, lq = math.dist(v, p), math.dist(v, q)
        c = min(r, lp / 2, lq / 2)
        a = (v[0] + (p[0] - v[0]) / lp * c, v[1] + (p[1] - v[1]) / lp * c)
        b = (v[0] + (q[0] - v[0]) / lq * c, v[1] + (q[1] - v[1]) / lq * c)
        k = 2 / 3
        return a, (a[0] + (v[0] - a[0]) * k, a[1] + (v[1] - a[1]) * k), (b[0] + (v[0] - b[0]) * k, b[1] + (v[1] - b[1]) * k), b
    if closed:
        first = corner(0)
        ctx.move_to(*first[3])
        for i in list(range(1, n)) + [0]:
            a, c1, c2, b = corner(i)
            ctx.line_to(*a)
            ctx.curve_to(*c1, *c2, *b)
        ctx.close_path()
    else:
        ctx.move_to(*pts[0])
        for i in range(1, n - 1):
            a, c1, c2, b = corner(i)
            ctx.line_to(*a)
            ctx.curve_to(*c1, *c2, *b)
        ctx.line_to(*pts[-1])
