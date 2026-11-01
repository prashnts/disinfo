from typing import Callable

from discore.color import AppColor


def scale(stops: list) -> Callable[[float], AppColor]:
    '''Colors between (value, hex) stops, linear in RGB; clamped to the ends.'''
    values = [v for v, _ in stops]
    rgbs = [tuple(int(h[i:i + 2], 16) for i in (1, 3, 5)) for _, h in stops]

    def at(value: float) -> AppColor:
        value = min(max(value, values[0]), values[-1])
        i = next((i for i in range(1, len(values)) if value <= values[i]), len(values) - 1)
        k = (value - values[i - 1]) / ((values[i] - values[i - 1]) or 1)
        return AppColor('#%02x%02x%02x' % tuple(round(a + (b - a) * k) for a, b in zip(rgbs[i - 1], rgbs[i])))
    return at


gray_lt = AppColor("#cbcdd9")
gray = AppColor('#9a9ba2')
light_gray = AppColor('#c6c6cb')
black = AppColor('#000000')
light_blue = AppColor('#2d83b4')
amber_red = AppColor('#b21a1a')
orange_red = AppColor('#c93f20')
minute_green = AppColor('#42a459')


# Sky colors
class SkyHues:
    black = AppColor('#000000')
    day_sky = AppColor('#27699b')
    night_sky = AppColor('#092134')

    sky_blue = AppColor('#27699b')
    sky_blue_b = AppColor('#2A5EAC')
    twilight_blue = AppColor('#1A4498')
    dusk_blue = AppColor('#190c7d')
    night_blue = AppColor('#0b043e')

    night_background = AppColor('#131129')

    evening_streak = AppColor('#1b1d74')
    evening_streak_2 = AppColor('#FBCA7F')
    evening_streak_3 = AppColor('#4B39A3')

    sun_path_a = AppColor('#bebebe00')
    sun_path_b = AppColor('#bebebeff')
    sun_position = AppColor('#d6d6d6')

    night = AppColor('#03152E')
    astronomical_twilight = AppColor('#071D42')
    nautical_twilight = AppColor('#082B6B')
    civil_twilight = AppColor('#15377D')

    label = '#9a9ba28c'
    tick_dark = '#0000008c'
