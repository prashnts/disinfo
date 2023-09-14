import spectra
from disinfo.screens.colors import AppColor


# Temperature color palette.
# https://www.esri.com/arcgis-blog/products/arcgis-pro/mapping/a-meaningful-temperature-palette/
temperature_scale_mapping = [
    [-5, '#e4eeff'],
    [0, '#9ab1d7'],
    [5, '#2a4d7f'],
    [10, '#297593'],
    [15, '#759386'],
    [20, '#bfa96d'],
    [25, '#b7925e'],
    [30, '#b27853'],
    [35, '#a64c4c'],
    [40, '#9e214b'],
]
def temperature_color(temp: float):
    tickpoints, colors = zip(*temperature_scale_mapping)
    scale = spectra.scale(colors).domain(tickpoints)
    if temp < tickpoints[0]:
        temp = tickpoints[0]
    elif temp > tickpoints[-1]:
        temp = tickpoints[-1]
    return AppColor(scale(temp).hexcode)
