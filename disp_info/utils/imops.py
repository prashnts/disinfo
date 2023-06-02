from PIL import Image, ImageDraw, ImageEnhance


def enlarge_pixels(img: Image.Image, scale: int = 4, gap: int = 1):
    # turn the img into a mosaic with gap between px.
    outline_color = '#000000'
    w, h = img.width, img.height
    iw, ih = w * scale, h * scale
    i = Image.new('RGBA', (iw, ih))
    d = ImageDraw.Draw(i)

    for x in range(w):
        for y in range(h):
            px = img.getpixel((x, y))

            # draw a rect.
            rx, ry = x * scale, y * scale
            ex, ey = rx + (scale - 1), ry + (scale - 1)
            d.rectangle([(rx, ry), (ex, ey)], fill=px, outline=outline_color, width=gap)

    brightness = ImageEnhance.Brightness(i)
    i = brightness.enhance(1.5)
    contrast = ImageEnhance.Contrast(i)
    i = contrast.enhance(0.8)

    return i
