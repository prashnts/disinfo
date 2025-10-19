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
    
    def get_pil_color(self) -> tuple[int, int, int, int]:
        r, g, b = [int(c * 255) for c in self.rgb]
        a = int(self.alpha * 255)
        return (r, g, b, a)