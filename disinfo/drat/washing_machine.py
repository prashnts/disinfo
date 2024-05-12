import skimage as ski
from PIL import Image

dot_pos = [485, 480]
offset_from_key = [0, 10]
digit_pos = {
    3: [0, 1],
    2: [35, 2],
    1: [66, 2],
}

positions = {
    'a': [0, 0],
    'b1': [10, -9],
    'b2': [9, 10],
    'c': [15, 2],
    'd1': [23, -8],
    'd2': [23, 12],
    'e': [30, 3],
}

seven_segment_map = {
    '1': ['b2', 'd2'],
    '2': ['a', 'b2', 'c', 'e', 'd1'],
    '3': ['a', 'b2', 'c', 'e', 'd2'],
    '4': ['b1', 'b2', 'c', 'd2'],
    '5': ['a', 'b1', 'c', 'd2', 'e'],
    '6': ['a', 'b1', 'c', 'd1', 'd2', 'e'],
    '7': ['a', 'b2', 'd2'],
    '8': ['a', 'b1', 'b2', 'c', 'd1', 'd2', 'e'],
    '9': ['a', 'b1', 'b2', 'c', 'd2', 'e'],
    '0': ['a', 'b1', 'b2', 'd1', 'd2', 'e'],
    'h': ['b1', 'c', 'd1', 'd2'],
}



def decode_digits(image):
    from matplotlib import pyplot as plt
    # image = image[400:800, 200:900]
    # hsv_img = ski.color.rgb2hsv(image)
    # image = hsv_img[:,:,2]
    image = image[400:800, 400:900]
    # image = hsv_img[:,:,2]
    print(image)
    t = ski.filters.threshold_mean(image)
    print(t)
    image = image < t
    plt.imshow(image, cmap='gray')
    plt.show()
    Image.fromarray(image).convert('L').save('wmkeysx.jpg')
    image = hsv_img[:,:,2]
    # ski.filters.threshold_otsu(image)
    image = ski.transform.rotate(image, -90)
    plt.imshow(Image.fromarray(image).convert('L'), cmap='gray')
    plt.show()

    print(image)

    # ski.io.imsave('wmkey.raw', image)
    Image.fromarray(image).convert('L').save('wmkeysx.jpg')


    digits = [' ', ' ', ' ', ' ']

    is_on = False
    key_pos = [272, 240]

    for num, digit in digit_pos.items():
        lit_segments = []
        for p, pos in positions.items():
            x = key_pos[0] + offset_from_key[0] + digit[0] + pos[1]
            y = key_pos[1] + offset_from_key[1] + digit[1] + pos[0]
            areas = [[x, y], [x + 1, y], [x, y + 1], [x + 1, y + 1]]
            intensity = sum([image[j][i] for i, j in areas]) / 4
            print(intensity)
            plt.scatter(x, y, c='red', s=1)
            if intensity > 0.85:
                lit_segments.append(p)
                is_on = True
        for k, v in seven_segment_map.items():
            if set(v) == set(lit_segments):
                digits[num - 1] = k

    plt.show()
    
    return is_on, f'{digits[2]}:{digits[1]}{digits[0]}'


def read_display():
    print('[Washing Machine] Fetching washing machine display')
    # img = ski.io.imread('http://10.0.1.101:8081/')
    # img = ski.io.imread('wmchn.jpg')
    img = ski.io.imread('wmchn.jpg')
    # ski.io.imsave('wmchn.jpg', img)
    print('[Washing Machine] Decoding')
    is_on, hours = decode_digits(img)

    return {'hours': hours, 'active': is_on}


if __name__ == '__main__':
    print(read_display())