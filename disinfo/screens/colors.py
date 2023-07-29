from colour import Color


def constrain(value, min_value=0, max_value=1):
    return max(min(value, max_value), min_value)


class AppColor(Color):
    def saturate(self, amount: float):
        self.saturation += amount
        return self

    def darken(self, amount: float):
        luminance = self.luminance - amount
        self.luminance = constrain(luminance)
        return self


smoky_uniform = AppColor('#9a9ba2')
