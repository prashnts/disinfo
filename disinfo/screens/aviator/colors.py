from disinfo.screens.colors import scale as color_scale


altitude_scale = [
    [0,     '#F16915'],
    [1200,  '#E8B714'],
    [2400,  '#5DC60D'],
    [3000,  '#21C134'],
    [6000,  '#0FB4C1'],
    [9000,  '#3E39F0'],
    [12000, '#C111D1'],
]
scale = color_scale(altitude_scale)

def marker_color(altitude: float):
    return scale(0 if type(altitude) == str else altitude)
