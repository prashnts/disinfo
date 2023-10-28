import math

def circle_in(t: float) -> float:
    return 1 - math.sqrt(1 - (t * t))

def circle_out(t: float) -> float:
    t -= 1
    return math.sqrt(1 - t * t)

def circle_in_out(t: float) -> float:
    t *= 2
    if t <= 1:
        return (1 - math.sqrt(1 - t * t)) / 2
    t -= 2
    return (math.sqrt(1 - t * t) + 1) / 2
