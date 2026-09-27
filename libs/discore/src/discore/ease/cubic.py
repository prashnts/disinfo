def cubic_in(t):
    return t ** 3

def cubic_out(t):
    t -= 1
    return t ** 3 + 1

def cubic_in_out(t):
    t *= 2
    if t <= 1:
        return cubic_in(t) / 2
    t -= 2
    return (t ** 3 + 2) / 2
