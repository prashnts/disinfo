from colour import Color


def constrain(value, min_value=0, max_value=1):
    return max(min(value, max_value), min_value)


class AppColor(Color):
    def saturate(self, amount: float):
        self.saturation += amount
        return self

    def darken(self, amount: float):
        c = Color(self)
        luminance = self.luminance - amount
        c.luminance = constrain(luminance)
        return c


gray = AppColor('#9a9ba2')
light_gray = AppColor('#c6c6cb')
black = AppColor('#000000')
light_blue = AppColor('#2d83b4')
amber_red = AppColor('#b21a1a')
