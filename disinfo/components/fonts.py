from PIL import ImageFont

class TTFFont:
    def __init__(self, path: str, size: int):
        self.path = path
        self.size = size
        self.font = ImageFont.truetype(path, size)

    def __repr__(self) -> str:
        return f'TTFFont(path={self.path}, size={self.size})'

# All font paths are from the package root.

# TAMZEN
# > License   Free (non-standard)
# > Source    https://github.com/sunaku/tamzen-font
tamzen__rs = TTFFont('assets/fonts/TamzenForPowerline5x9r.ttf', 9)
tamzen__rm = TTFFont('assets/fonts/Tamzen7x13r.ttf', 13)

# PIXEL OPERATOR
# > License   CC0
# > Source    https://notabug.org/HarvettFox96/ttf-pixeloperator
px_op__r        = TTFFont('assets/fonts/PixelOperator8.ttf', 8)
px_op_mono_8    = TTFFont('assets/fonts/PixelOperatorMono8.ttf', 8)
px_op__l        = TTFFont('assets/fonts/PixelOperator.ttf', 16)
px_op__lb       = TTFFont('assets/fonts/PixelOperator-Bold.ttf', 16)
px_op__xl       = TTFFont('assets/fonts/PixelOperator.ttf', 32)
px_op__xxl      = TTFFont('assets/fonts/PixelOperator.ttf', 48)

# SCIENTIFICA
# > License   OFL v1.1
# > Source    https://github.com/nerdypepper/scientifica
scientifica__r = TTFFont('assets/fonts/scientifica.ttf', 11)
scientifica__b = TTFFont('assets/fonts/scientificaBold.ttf', 11)
scientifica__i = TTFFont('assets/fonts/scientificaItalic.ttf', 11)

# BITOCRA
# > License   OFL v1.1
# > Source    https://github.com/ninjaaron/bitocra
bitocra7 = TTFFont('assets/fonts/bitocra7.bdf', 7)
fiveel = TTFFont('assets/fonts/5thElement.bdf', 5)

# COZETTE
# > License   MIT
# > Source    https://github.com/slavfox/Cozette
cozette = TTFFont('assets/fonts/cozette.bdf', 13)

# GREYBEARD
# > License   MIT
# > Source    https://github.com/flowchartsman/greybeard
greybeard = TTFFont('assets/fonts/Greybeard-11px.ttf', 11)

# SPLEEN
# > License   BSD
# > Source    https://github.com/fcambus/spleen
spleen__s = TTFFont('assets/fonts/spleen-5x8.bdf', 8)

# CREEP
# > License   MIT
# > Source    https://github.com/romeovs/creep
creep = TTFFont('assets/fonts/creep.bdf', 16)

# VIRTUAL DJ
# > License   Free (non-standard)
# > Source    https://www.dafont.com/fr/virtual-dj.font
vdj = TTFFont('assets/fonts/virtual-dj.ttf', 8)

# SMALL PIXEL
# > License   Free (non-standard)
# > Source    https://www.dafont.com/fr/small-pixel.font
small_pixel = TTFFont('assets/fonts/small_pixel.ttf', 8)

# AZTECH
# > License   CC0
# > Source    https://www.dafont.com/fr/aztech.font
aztech = TTFFont('assets/fonts/aztech.ttf', 16)

# Pixel-lcd-machine
# > License   CC-SA
# > Source    https://www.dafont.com/fr/Pixel-lcd-machine.font
pixel_lcd = TTFFont('assets/fonts/Pixel-lcd-machine.ttf', 16)