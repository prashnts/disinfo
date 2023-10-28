def tpmt(x: float) -> float:
    '''tpmt is two power minus ten times t scaled to [0,1]'''
    return ((2 ** (-10 * x)) - 0.0009765625) * 1.0009775171065494
