import spectra
from disinfo.screens.colors import AppColor


altitude_scale = [
    [0,     '#F16915'],
    [1200,  '#E8B714'],
    [2400,  '#5DC60D'],
    [3000,  '#21C134'],
    [6000,  '#0FB4C1'],
    [9000,  '#3E39F0'],
    [12000, '#C111D1'],
]
def marker_color(altitude: float):
    tickpoints, colors = zip(*altitude_scale)
    scale = spectra.scale(colors).domain(tickpoints)
    if type(altitude) == str:
        altitude = 0
    if altitude < tickpoints[0]:
        altitude = tickpoints[0]
    elif altitude > tickpoints[-1]:
        altitude = tickpoints[-1]
    return AppColor(scale(altitude).hexcode)
