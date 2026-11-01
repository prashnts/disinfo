from disinfo.screens.colors import scale


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
_temperature = scale(temperature_scale_mapping)

def temperature_color(temp: float):
    return _temperature(temp)
