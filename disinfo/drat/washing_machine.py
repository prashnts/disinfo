import skimage as ski
# import matplotlib.pyplot as plt

dot_pos = [485, 480]
digit_pos = {
    3: [465, 480],
    2: [501, 478],
    1: [530, 478],
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
    hsv_img = ski.color.rgb2hsv(image)
    image = hsv_img[:,:,2]
    image = ski.transform.rotate(image, -90)
    # plt.imshow(image, cmap='gray')

    digits = [' ', ' ', ' ', ' ']

    is_on = False

    for num, digit in digit_pos.items():
        lit_segments = []
        for p, pos in positions.items():
            x = digit[0] + pos[1]
            y = digit[1] + pos[0]
            areas = [[x, y], [x + 1, y], [x, y + 1], [x + 1, y + 1]]
            intensity = sum([image[j][i] for i, j in areas]) / 4
            print(intensity)
            if intensity > 0.85:
                lit_segments.append(p)
                is_on = True
        for k, v in seven_segment_map.items():
            if set(v) == set(lit_segments):
                digits[num - 1] = k

    # plt.show()
    
    return is_on, f'{digits[2]}:{digits[1]}{digits[0]}'


def read_display():
    print('[Washing Machine] Fetching washing machine display')
    img = ski.io.imread('http://10.0.1.101:8081/')
    print('[Washing Machine] Decoding')
    is_on, hours = decode_digits(img)

    return {'hours': hours, 'active': is_on}


if __name__ == '__main__':
    print(read_display())