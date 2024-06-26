from colour import Color


def constrain(value, min_value=0, max_value=1):
    return max(min(value, max_value), min_value)


class AppColor(Color):
    def __init__(self, color: str):
        self.__dict__['alpha'] = 1
        if color.startswith('#'):
            if len(color) == 9:
                # contains alpha.
                self.__dict__['alpha'] = int(color[7:9], 16) / 255
                color = color[0:7]
        super().__init__(color)

    def saturate(self, amount: float):
        self.saturation += amount
        return self

    def darken(self, amount: float):
        c = Color(self)
        luminance = self.luminance - amount
        c.luminance = constrain(luminance)
        return c

    def get_rgba(self):
        return (*self.rgb, self.alpha)
    
    def get_hexa(self):
        alpha = hex(int(self.alpha * 255))[2:].zfill(2)
        return f'{self.hex}{alpha}'

    def set_alpha(self, alpha: float) -> 'AppColor':
        self.__dict__['alpha'] = alpha
        return self


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
