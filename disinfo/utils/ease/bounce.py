b1 = 4 / 11
b2 = 6 / 11
b3 = 8 / 11
b4 = 3 / 4
b5 = 9 / 11
b6 = 10 / 11
b7 = 15 / 16
b8 = 21 / 22
b9 = 63 / 64
b0 = 1 / b1 / b1

def bounce_in(t: float) -> float:
    return 1 - bounce_out(1 - t)

def bounce_out(t: float) -> float:
    t = abs(t)
    if t < b1:
        return b0 * t * t
    if t < b3:
        t -= b2
        return b0 * t * t + b4
    if t < b6:
        t -= b5
        return b0 * t * t + b7
    t -= b8
    return b0 * t * t + b9

def bounce_in_out(t: float) -> float:
    t *= 2
    if t <= 1:
        return (1 - bounce_out(1 - t)) / 2
    return (bounce_out(t - 1) + 1) / 2

# TODO: this does not work as expected.

# (t = +t) < b1
#     ? b0 * t * t
#     : t < b3
#         ? b0 * (t -= b2) * t + b4
#         : t < b6
#             ? b0 * (t -= b5) * t + b7
#             : b0 * (t -= b8) * t + b9;
