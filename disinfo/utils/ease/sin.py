import math

pi = math.pi
half_pi = pi / 2

def sin_in(t: float) -> float:
    if abs(t) == 1:
        return 1
    else:
        return 1 - math.cos(t * half_pi)

def sin_out(t: float) -> float:
    return math.sin(t * half_pi)

def sin_in_out(t: float) -> float:
    return (1 - math.cos(t * pi)) / 2
