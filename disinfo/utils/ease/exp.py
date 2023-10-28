from .math import tpmt

def exp_in(t: float) -> float:
    return tpmt(1 - abs(t))

def exp_out(t: float) -> float:
    return 1 - tpmt(t)

def exp_in_out(t: float) -> float:
    if t * 2 <= 1:
        return tpmt(1 - t) / 2
    return (2 - tpmt(t - 1)) / 2
