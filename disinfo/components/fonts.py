from PIL import ImageFont
from pathlib import Path
from dataclasses import dataclass

register = {}

@dataclass
class TTFFont:
    path: str | Path
    size: int
    license: str = 'unknown'
    credit: str = ''
    spacing: int = 0

    def __post_init__(self):
        self.path = Path(self.path)
        self.filename = self.path.name
        self._font = None

        if not self.filename in register:
            register[self.filename] = self
    
    @property
    def font(self):
        if self._font is None:
            self._font = ImageFont.truetype(str(self.path), self.size)
        return self._font

    def __hash__(self):
        return hash((self.path, self.size, self.license, self.credit))

    def __repr__(self) -> str:
        return f'TTFFont(path={self.path}, size={self.size})'

# All font paths are from the package root.

# TAMZEN
# > License   Free (non-standard)
# > Source    https://github.com/sunaku/tamzen-font
tamzen__rs = TTFFont('assets/fonts/TamzenForPowerline5x9r.ttf', 9, license='free')
tamzen__rm = TTFFont('assets/fonts/Tamzen7x13r.ttf', 13, license='free')

# PIXEL OPERATOR
# > License   CC0
# > Source    https://notabug.org/HarvettFox96/ttf-pixeloperator
px_op__r        = TTFFont('assets/fonts/PixelOperator8.ttf', 8, license='CC0')
px_op_mono_8    = TTFFont('assets/fonts/PixelOperatorMono8.ttf', 8, license='CC0')
px_op__l        = TTFFont('assets/fonts/PixelOperator.ttf', 16, license='CC0')
px_op__lb       = TTFFont('assets/fonts/PixelOperator-Bold.ttf', 16, license='CC0')
px_op__xl       = TTFFont('assets/fonts/PixelOperator.ttf', 32, license='CC0')
px_op__xxl      = TTFFont('assets/fonts/PixelOperator.ttf', 48, license='CC0')

# SCIENTIFICA
# > License   OFL v1.1
# > Source    https://github.com/nerdypepper/scientifica
scientifica__r = TTFFont('assets/fonts/scientifica.ttf', 11, license='OFL')
scientifica__b = TTFFont('assets/fonts/scientificaBold.ttf', 11, license='OFL')
scientifica__i = TTFFont('assets/fonts/scientificaItalic.ttf', 11, license='OFL')


cozette = TTFFont('assets/fonts/cozette.bdf', 13, license='MIT', credit='https://github.com/slavfox/Cozette')

# GREYBEARD
# > License   MIT
# > Source    https://github.com/flowchartsman/greybeard
greybeard = TTFFont('assets/fonts/Greybeard-11px.ttf', 11, license='MIT')

# SPLEEN
# > License   BSD
# > Source    https://github.com/fcambus/spleen
spleen__s = TTFFont('assets/fonts/spleen-5x8.bdf', 8, license='BSD')

# CREEP
# > License   MIT
# > Source    https://github.com/romeovs/creep
creep = TTFFont('assets/fonts/creep.bdf', 16, license='MIT')


# Pixel-lcd-machine
# > License   CC-SA
# > Source    https://www.dafont.com/fr/Pixel-lcd-machine.font
pixel_lcd = TTFFont('assets/fonts/Pixel-lcd-machine.ttf', 16, license='CC-SA')


# 15x5
# > License   ?
s15x5 = TTFFont('assets/fonts/15x5.ttf', 16)


# Dansk
# > License   Demo
dansk = TTFFont('assets/fonts/Dansk.ttf', 16, license='demo')

# Pixeloza
# > License   Free (non-standard)
pixeloza = TTFFont('assets/fonts/Pixeloza03.ttf', 21, license='free')

# PixTall
# > License   Free (non-standard)
# Not monospaced.
pix_tall = TTFFont('assets/fonts/PixTall.ttf', 32, license='free')


# Small Bars
# > License   Free (non-standard)
small_bars = TTFFont('assets/fonts/smallbars.ttf', 10, license='free')

# OPN Bit Fuul
# > License   GNU GPLv3
opn_bit_fuul = TTFFont('assets/fonts/OPN BitFUUL.ttf', 10, license='GPLv3')

catv = TTFFont('assets/fonts/CatV_6x12_9.ttf', 17, license='CC-BY-SA')
s16x8 = TTFFont('assets/fonts/16x8pxl-mono.ttf', 20, license='OFL')


# Pixel Play
# > License   Free
pixelplay = TTFFont('assets/fonts/pixelplay.ttf', 16)

mixserif = TTFFont('assets/fonts/MixSerifCondense.ttf', 16)
dymsmall = TTFFont('assets/fonts/dymsmall.ttf', 10)
atc = TTFFont('assets/fonts/ATC.ttf', 16)
pixwriter = TTFFont('assets/fonts/5pixwriter.ttf', 16, license='CC-BY-SA')

everyday = TTFFont('assets/fonts/Everyday.ttf', 10, license='free (nc)') # no accents
fffextra = TTFFont('assets/fonts/FFFEXTRA.TTF', 8, license='free (nc)') # cloverleaf
gaiatype = TTFFont('assets/fonts/Gaiatype.ttf', 16, license='CC0')
mecha_cond = TTFFont('assets/fonts/Mecha_Condensed.ttf', 16, license='free (nc)')
mecha_bold = TTFFont('assets/fonts/Mecha_Bold.ttf', 16, license='free (nc)')
mecha_cb = TTFFont('assets/fonts/Mecha_Condensed_Bold.ttf', 16, license='free (nc)')
mecha = TTFFont('assets/fonts/Mecha.ttf', 16, license='free (nc)')
serifpx7 = TTFFont('assets/fonts/serif_pixel-7.ttf', 10, license='free (nc)', credit='http://www.styleseven.com')
zx_spectrum = TTFFont('assets/fonts/zx_spectrum-7.ttf', 10, license='free (nc)', credit='http://www.styleseven.com')
zx_spectrum_b = TTFFont('assets/fonts/zx_spectrum-7_bold.ttf', 10, license='free (nc)', credit='http://www.styleseven.com')

bitocra7 = TTFFont('assets/fonts/bitocra7.bdf', 7, license='OFL', credit='https://github.com/ninjaaron/bitocra')
fiveel = TTFFont('assets/fonts/5thElement.bdf', 5, license='OFL', credit='https://github.com/ninjaaron/bitocra')
vdj = TTFFont('assets/fonts/virtual-dj.ttf', 8, license='free', credit='https://www.dafont.com/fr/virtual-dj.font')
long_pixel = TTFFont('assets/fonts/long_pixel-7.ttf', 10, license='free')
slkscre = TTFFont('assets/fonts/slkscre.ttf', 8, license='free')
aztech = TTFFont('assets/fonts/aztech.ttf', 16, license='CC0', credit='https://www.dafont.com/fr/aztech.font')
small_pixel = TTFFont('assets/fonts/small_pixel.ttf', 8, license='free', credit='https://www.dafont.com/fr/small-pixel.font')
megan_serif = TTFFont('assets/fonts/Megan_Serif.ttf', 8, license='free')
double01 = TTFFont('assets/fonts/double01.ttf', 8, license='free (nc)')
double01b = TTFFont('assets/fonts/double01b.ttf', 8, license='free (nc)')
sg09 = TTFFont('assets/fonts/SG09.ttf', 8)
two_slice = TTFFont('assets/fonts/Two Slice.ttf', 3, license='CC-BY-SA', credit='https://joefatula.com/twoslice.html', spacing=1)
exsmall = TTFFont('assets/fonts/Extremely-Small-Fonts.ttf', 4, license='free (nc)', spacing=2)
microfont_35_mono = TTFFont('assets/fonts/3x5-Microfont-Mono.ttf', 8, license='CC0', credit='https://github.com/nimaid/microfont')
microfont_35_reg = TTFFont('assets/fonts/3x5-Microfont.ttf', 8, license='CC0', credit='https://github.com/nimaid/microfont')

ttpixels = TTFFont('assets/fonts/TeenyTinyPixls-o2zo.ttf', 5, license='free', spacing=2)