import spectra
from disinfo.screens.colors import AppColor


# Temperature color palette.
temperature_scale_mapping = [
    [-5, '#234ea0'],
    [0, '#2073b2'],
    [10, '#73c9bd'],
    [25, '#4393c3'],
    [30, '#fed676'],
    [40, '#d85b0a'],
]
def temperature_color(temp: float):
    tickpoints, colors = zip(*temperature_scale_mapping)
    scale = spectra.scale(colors).domain(tickpoints)
    if temp < tickpoints[0]:
        temp = tickpoints[0]
    elif temp > tickpoints[-1]:
        temp = tickpoints[-1]
    return AppColor(scale(temp).hexcode)
