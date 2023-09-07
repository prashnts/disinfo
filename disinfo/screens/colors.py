from colour import Color


def constrain(value, min_value=0, max_value=1):
    return max(min(value, max_value), min_value)


class AppColor(Color):
    def __init__(self, color: str):
        self.__dict__['alpha'] = 1
        if color.startswith('#'):
            if len(color) == 9:
                # contains alpha.
                color = color[0:7]
                self.__dict__['alpha'] = int(color[6:8], 16) / 255
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



gray = AppColor('#9a9ba2')
light_gray = AppColor('#c6c6cb')
black = AppColor('#000000')
light_blue = AppColor('#2d83b4')
amber_red = AppColor('#b21a1a')
orange_red = AppColor('#c93f20')


# Sky colors
class SkyHues:
    day_sky = AppColor('#27699b')
    night_sky = AppColor('#092134')

    sky_blue = AppColor('#27699b')
    twilight_blue = AppColor('#404BD9')
    dusk_blue = AppColor('#190c7d')
    night_blue = AppColor('#0b043e')

    sun_path_a = AppColor('#bebebe00')
    sun_path_b = AppColor('#bebebeff')
    sun_position = AppColor('#d6d6d6')

    night = AppColor('#0e111f')
    astronomical_twilight = AppColor('#111154')
    nautical_twilight = AppColor('#1b1d74')
    civil_twilight = AppColor('#284995')

    label = '#9a9ba25c'
