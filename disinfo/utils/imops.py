import io
import requests
import numpy as np
import time

from functools import cache
from PIL import Image, ImageDraw, ImageEnhance

from disinfo.components.elements import Frame, StillImage


def enlarge_pixels(img: Image.Image, scale: int = 4, gap: int = 1, outline_color: str = '#000000'):
    # turn the img into a mosaic with gap between px.
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


def floyd_steinberg(image):
    # image: np.array of shape (height, width), dtype=float, 0.0-1.0
    # works in-place!
    h, w = image.shape
    for y in range(h):
        for x in range(w):
            old = image[y, x]
            new = np.round(old)
            image[y, x] = new
            error = old - new
            # precomputing the constants helps
            if x + 1 < w:
                image[y, x + 1] += error * 0.4375 # right, 7 / 16
            if (y + 1 < h) and (x + 1 < w):
                image[y + 1, x + 1] += error * 0.0625 # right, down, 1 / 16
            if y + 1 < h:
                image[y + 1, x] += error * 0.3125 # down, 5 / 16
            if (x - 1 >= 0) and (y + 1 < h):
                image[y + 1, x - 1] += error * 0.1875 # left, down, 3 / 16
    return image

def dither(img: np.array):
    chans = np.split(img, 4, axis=2)
    # Convert the channels from [[[x]]] to [[x]].
    chans = [c.reshape(c.shape[0], c.shape[1]) for c in chans]
    return np.stack([floyd_steinberg(c) for c in chans], axis=2)

def apply_gamma(img: Image.Image, g):
    im = np.array(img) / 255
    # im = floyd_steinberg(im)
    # im = dither(im)
    im = im ** g    # gamma correction
    return Image.fromarray((im * 255).astype(np.uint8))


def find_coeffs(pa, pb):
    # https://stackoverflow.com/a/14178717
    matrix = []
    for p1, p2 in zip(pa, pb):
        matrix.append([p1[0], p1[1], 1, 0, 0, 0, -p2[0]*p1[0], -p2[0]*p1[1]])
        matrix.append([0, 0, 0, p1[0], p1[1], 1, -p2[1]*p1[0], -p2[1]*p1[1]])

    A = np.matrix(matrix, dtype=np.float64)
    B = np.array(pb).reshape(8)

    res = np.dot(np.linalg.inv(A.T * A) * A.T, B)
    return np.array(res).reshape(8)

def perspective_transform(img: Image.Image, src_pts, dst_pts):
    coeffs = find_coeffs(dst_pts, src_pts)
    return img.transform((img.width, img.height), Image.PERSPECTIVE, coeffs, Image.BICUBIC)



@cache
def _fetch_image(url: str) -> bytes:
    r = requests.get(url, timeout=4)
    r.raise_for_status()
    return r.content

@cache
def image_from_url(url: str, resize: tuple[int, int] = (42, 42), ratio_fn=max):
    hash_ = ('img_from_url', url, resize) 
    fallback = Frame(Image.new('RGBA', (2, 2), (0, 0, 0, 0)), hash_)
    if not url:
        return fallback
    try:
        r = _fetch_image(url)
        with io.BytesIO(r) as fp:
            img = Image.open(fp)
            res_x, res_y = resize
            ratio = ratio_fn(res_x/img.width, res_y/img.height)
            size = (int(img.width*ratio), int(img.height*ratio))
            midsize = (int(1.5 * size[0]), int(1.5 * size[1]))
            img = (img
                .resize(midsize, resample=Image.Resampling.LANCZOS)
                .resize(size)
                .convert('RGBA'))
        return Frame(img, hash_)
    except requests.RequestException as e:
        return fallback
