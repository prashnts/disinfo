# icons were taken from: https://github.com/mkgeiger/matrix-weather-clock/blob/master/MatrixWeatherClock/MatrixWeatherClock.ino
#define BLK  // Black
#define CYN  // Light Cyan
#define GRY  // Dark Grey
#define YEL  // Yellow
#define BLU  // Blue
#define RED  // Red
#define GRN  // Green
#define ORG  // Orange
#define WHT  // White
# BLK,  // 0
# WHT,  // 1
# YEL,  // 2
# BLU,  // 3
# CYN,  // 4
# GRY,  // 5
# RED   // 6
from PIL import Image, ImageDraw
from functools import cache


colors = [
    '#000000',
    '#d3d3d3',
    '#bcaa09',
    '#0c4cad',
    '#148cb1',
    '#616a6f',
    '#ce1c1c',
]

icon1d = [
    0, 0, 4, 4, 0, 0, 2, 2, 0,
    0, 4, 4, 4, 4, 2, 2, 2, 2,
    4, 4, 4, 4, 4, 4, 4, 2, 2,
    4, 4, 4, 4, 4, 4, 4, 4, 4,
    0, 4, 2, 2, 4, 3, 4, 4, 3,
    0, 0, 2, 4, 4, 3, 4, 3, 0,
    0, 2, 2, 0, 3, 0, 0, 3, 0,
    0, 2, 0, 0, 3, 0, 3, 0, 0,
    2, 0, 0, 3, 0, 0, 0, 0, 0
]

icon1n = [
    0, 0, 4, 4, 0, 0, 5, 5, 0,
    0, 4, 4, 4, 4, 5, 5, 5, 5,
    4, 4, 4, 4, 4, 4, 4, 5, 5,
    4, 4, 4, 4, 4, 4, 4, 4, 4,
    0, 4, 2, 2, 4, 3, 4, 4, 3,
    0, 0, 2, 4, 4, 3, 4, 3, 0,
    0, 2, 2, 0, 3, 0, 0, 3, 0,
    0, 2, 0, 0, 3, 0, 3, 0, 0,
    2, 0, 0, 3, 0, 0, 0, 0, 0
]

icon2 = [
    0, 0, 0, 0, 0, 0, 0, 0, 2,
    0, 0, 0, 2, 2, 0, 0, 2, 0,
    0, 0, 2, 2, 0, 0, 2, 0, 0,
    0, 2, 2, 0, 0, 2, 2, 2, 2,
    2, 2, 2, 2, 0, 0, 0, 2, 0,
    0, 0, 2, 0, 0, 0, 2, 0, 0,
    0, 2, 0, 0, 0, 0, 0, 0, 0,
    2, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0
]

icon3d = [
    0, 0, 4, 4, 0, 0, 2, 2, 0,
    0, 4, 4, 4, 4, 2, 2, 2, 2,
    4, 3, 3, 4, 3, 3, 4, 2, 2,
    4, 3, 3, 4, 3, 3, 4, 4, 4,
    0, 4, 4, 4, 4, 4, 4, 4, 4,
    0, 0, 4, 4, 4, 3, 3, 0, 0,
    0, 0, 0, 0, 0, 3, 3, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0
]

icon3n = [
    0, 0, 4, 4, 0, 0, 5, 5, 0,
    0, 4, 4, 4, 4, 5, 5, 5, 5,
    4, 3, 3, 4, 3, 3, 4, 5, 5,
    4, 3, 3, 4, 3, 3, 4, 4, 4,
    0, 4, 4, 4, 4, 4, 4, 4, 4,
    0, 0, 4, 4, 4, 3, 3, 0, 0,
    0, 0, 0, 0, 0, 3, 3, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0
]

icon4d = [
    0, 0, 4, 4, 0, 0, 2, 2, 0,
    0, 4, 4, 4, 4, 2, 2, 2, 2,
    4, 4, 4, 4, 4, 4, 4, 2, 2,
    4, 4, 4, 4, 4, 4, 4, 4, 4,
    0, 4, 4, 3, 4, 3, 4, 4, 3,
    0, 0, 3, 4, 4, 3, 4, 3, 0,
    0, 0, 3, 0, 3, 0, 0, 3, 0,
    0, 3, 0, 0, 3, 0, 3, 0, 0,
    0, 0, 0, 3, 0, 0, 0, 0, 0
]

icon4n = [
    0, 0, 4, 4, 0, 0, 5, 5, 0,
    0, 4, 4, 4, 4, 5, 5, 5, 5,
    4, 4, 4, 4, 4, 4, 4, 5, 5,
    4, 4, 4, 4, 4, 4, 4, 4, 4,
    0, 4, 4, 3, 4, 3, 4, 4, 3,
    0, 0, 3, 4, 4, 3, 4, 3, 0,
    0, 0, 3, 0, 3, 0, 0, 3, 0,
    0, 3, 0, 0, 3, 0, 3, 0, 0,
    0, 0, 0, 3, 0, 0, 0, 0, 0
]

icon5d = [
    0, 0, 4, 4, 0, 0, 2, 2, 0,
    0, 4, 4, 4, 4, 2, 2, 2, 2,
    4, 4, 4, 4, 4, 4, 4, 2, 2,
    4, 4, 4, 3, 4, 4, 4, 4, 3,
    0, 4, 4, 4, 4, 3, 4, 4, 4,
    0, 0, 3, 4, 4, 4, 4, 3, 0,
    0, 0, 0, 0, 3, 0, 0, 0, 0,
    0, 3, 0, 0, 0, 0, 3, 0, 0,
    0, 0, 0, 3, 0, 0, 0, 0, 0
]

icon5n = [
    0, 0, 4, 4, 0, 0, 5, 5, 0,
    0, 4, 4, 4, 4, 5, 5, 5, 5,
    4, 4, 4, 4, 4, 4, 4, 5, 5,
    4, 4, 4, 3, 4, 4, 4, 4, 3,
    0, 4, 4, 4, 4, 3, 4, 4, 4,
    0, 0, 3, 4, 4, 4, 4, 3, 0,
    0, 0, 0, 0, 3, 0, 0, 0, 0,
    0, 3, 0, 0, 0, 0, 3, 0, 0,
    0, 0, 0, 3, 0, 0, 0, 0, 0
]

icon6d = [
    0, 0, 4, 4, 0, 0, 2, 2, 0,
    0, 4, 4, 4, 4, 2, 2, 2, 2,
    4, 4, 4, 4, 4, 4, 4, 2, 2,
    4, 4, 4, 3, 4, 4, 4, 4, 3,
    0, 4, 4, 3, 4, 3, 4, 4, 3,
    0, 0, 4, 4, 4, 3, 4, 0, 0,
    0, 0, 3, 0, 0, 0, 0, 3, 0,
    0, 3, 0, 0, 3, 0, 3, 0, 0,
    0, 0, 0, 3, 0, 0, 0, 0, 0
]

icon6n = [
    0, 0, 4, 4, 0, 0, 5, 5, 0,
    0, 4, 4, 4, 4, 5, 5, 5, 5,
    4, 4, 4, 4, 4, 4, 4, 5, 5,
    4, 4, 4, 3, 4, 4, 4, 4, 3,
    0, 4, 4, 3, 4, 3, 4, 4, 3,
    0, 0, 4, 4, 4, 3, 4, 0, 0,
    0, 0, 3, 0, 0, 0, 0, 3, 0,
    0, 3, 0, 0, 3, 0, 3, 0, 0,
    0, 0, 0, 3, 0, 0, 0, 0, 0
]

icon7d = [
    0, 0, 4, 4, 0, 0, 2, 2, 0,
    0, 4, 4, 4, 4, 2, 2, 2, 2,
    4, 4, 4, 4, 4, 4, 4, 2, 2,
    4, 4, 4, 4, 4, 4, 4, 4, 3,
    0, 4, 2, 2, 4, 3, 4, 4, 3,
    0, 0, 2, 4, 4, 3, 4, 0, 0,
    0, 2, 2, 0, 0, 0, 0, 3, 0,
    0, 2, 0, 0, 3, 0, 3, 0, 0,
    2, 0, 0, 3, 0, 0, 0, 0, 0
]

icon7n = [
    0, 0, 4, 4, 0, 0, 5, 5, 0,
    0, 4, 4, 4, 4, 5, 5, 5, 5,
    4, 4, 4, 4, 4, 4, 4, 5, 5,
    4, 4, 4, 4, 4, 4, 4, 4, 3,
    0, 4, 2, 2, 4, 3, 4, 4, 3,
    0, 0, 2, 4, 4, 3, 4, 0, 0,
    0, 2, 2, 0, 0, 0, 0, 3, 0,
    0, 2, 0, 0, 3, 0, 3, 0, 0,
    2, 0, 0, 3, 0, 0, 0, 0, 0
]

icon8d = [
    0, 0, 4, 4, 0, 0, 2, 2, 0,
    0, 4, 4, 4, 4, 2, 2, 2, 2,
    4, 4, 4, 4, 4, 4, 4, 2, 2,
    4, 4, 4, 4, 3, 4, 4, 4, 4,
    0, 4, 3, 4, 4, 4, 3, 4, 4,
    0, 0, 4, 4, 3, 4, 4, 0, 0,
    0, 0, 3, 0, 0, 0, 3, 0, 0,
    0, 0, 0, 0, 3, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0
]

icon8n = [
    0, 0, 4, 4, 0, 0, 5, 5, 0,
    0, 4, 4, 4, 4, 5, 5, 5, 5,
    4, 4, 4, 4, 4, 4, 4, 5, 5,
    4, 4, 4, 4, 3, 4, 4, 4, 4,
    0, 4, 3, 4, 4, 4, 3, 4, 4,
    0, 0, 4, 4, 3, 4, 4, 0, 0,
    0, 0, 3, 0, 0, 0, 3, 0, 0,
    0, 0, 0, 0, 3, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0
]

icon9d = [
    0, 0, 4, 4, 0, 0, 2, 2, 0,
    0, 4, 4, 4, 4, 2, 2, 2, 2,
    4, 4, 4, 4, 4, 4, 4, 2, 2,
    4, 4, 4, 4, 4, 4, 4, 4, 4,
    0, 4, 4, 4, 4, 3, 4, 4, 4,
    0, 0, 3, 4, 4, 4, 4, 3, 0,
    0, 0, 0, 0, 3, 0, 0, 0, 0,
    0, 3, 0, 0, 0, 0, 3, 0, 0,
    0, 0, 0, 3, 0, 0, 0, 0, 0
]

icon9n = [
    0, 0, 4, 4, 0, 0, 5, 5, 0,
    0, 4, 4, 4, 4, 5, 5, 5, 5,
    4, 4, 4, 4, 4, 4, 4, 5, 5,
    4, 4, 4, 4, 4, 4, 4, 4, 4,
    0, 4, 4, 4, 4, 3, 4, 4, 4,
    0, 0, 3, 4, 4, 4, 4, 3, 0,
    0, 0, 0, 0, 3, 0, 0, 0, 0,
    0, 3, 0, 0, 0, 0, 3, 0, 0,
    0, 0, 0, 3, 0, 0, 0, 0, 0
]

icon10 = [
    0, 0, 4, 4, 4, 4, 0, 0, 0,
    0, 4, 4, 4, 4, 4, 4, 4, 0,
    4, 4, 4, 4, 4, 4, 4, 4, 4,
    4, 4, 4, 4, 4, 4, 4, 4, 4,
    0, 4, 4, 4, 4, 4, 4, 4, 0,
    0, 0, 4, 4, 5, 5, 5, 0, 0,
    0, 0, 0, 5, 5, 5, 0, 0, 0,
    0, 0, 5, 5, 5, 5, 0, 0, 0,
    0, 0, 0, 5, 5, 0, 0, 0, 0
]

icon11d = [
    0, 0, 0, 0, 2, 0, 0, 0, 0,
    0, 2, 0, 0, 0, 0, 0, 2, 0,
    0, 0, 0, 2, 2, 2, 0, 0, 0,
    0, 0, 2, 2, 2, 2, 2, 0, 0,
    2, 0, 2, 2, 2, 2, 2, 0, 2,
    5, 5, 5, 5, 0, 5, 0, 5, 5,
    0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 5, 0, 5, 5, 0, 5, 5, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0
]

icon11n = [
    0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 5, 5, 5, 0, 0, 0,
    0, 0, 5, 5, 5, 5, 5, 0, 0,
    0, 5, 5, 5, 5, 5, 5, 5, 0,
    0, 5, 5, 5, 5, 5, 5, 5, 0,
    5, 5, 5, 5, 0, 5, 0, 5, 5,
    0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 5, 0, 5, 5, 0, 5, 5, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0
]

icon12 = [
    0, 0, 0, 0, 0, 0, 0, 0, 0,
    5, 5, 0, 5, 5, 5, 5, 0, 5,
    0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 5, 0, 5, 5, 0, 5, 5, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0,
    5, 5, 5, 5, 0, 5, 0, 5, 5,
    0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 5, 0, 5, 5, 0, 5, 5, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0
]

icon13d = [
    0, 0, 4, 4, 0, 0, 2, 2, 0,
    0, 4, 4, 4, 4, 2, 2, 2, 2,
    4, 4, 4, 4, 4, 4, 4, 2, 2,
    4, 4, 4, 4, 4, 4, 4, 4, 4,
    0, 3, 3, 3, 3, 3, 3, 3, 4,
    0, 0, 4, 4, 4, 4, 4, 0, 0,
    3, 3, 3, 3, 3, 3, 3, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 3, 3, 3, 3, 3, 3, 3
]

icon13n = [
    0, 0, 4, 4, 0, 0, 5, 5, 0,
    0, 4, 4, 4, 4, 5, 5, 5, 5,
    4, 4, 4, 4, 4, 4, 4, 5, 5,
    4, 4, 4, 4, 4, 4, 4, 4, 4,
    0, 3, 3, 3, 3, 3, 3, 3, 4,
    0, 0, 4, 4, 4, 4, 4, 0, 0,
    3, 3, 3, 3, 3, 3, 3, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 3, 3, 3, 3, 3, 3, 3
]

icon14d = [
    0, 0, 4, 4, 0, 0, 2, 2, 0,
    0, 4, 4, 4, 4, 2, 2, 2, 2,
    4, 4, 4, 4, 4, 4, 4, 2, 2,
    4, 4, 4, 4, 3, 3, 4, 4, 4,
    3, 3, 3, 3, 3, 3, 4, 4, 4,
    0, 0, 4, 4, 4, 4, 4, 0, 0,
    3, 3, 3, 3, 0, 0, 0, 0, 0,
    0, 0, 3, 3, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0
]

icon14n = [
    0, 0, 4, 4, 0, 0, 5, 5, 0,
    0, 4, 4, 4, 4, 5, 5, 5, 5,
    4, 4, 4, 4, 4, 4, 4, 5, 5,
    4, 4, 4, 4, 3, 3, 4, 4, 4,
    3, 3, 3, 3, 3, 3, 4, 4, 4,
    0, 0, 4, 4, 4, 4, 4, 0, 0,
    3, 3, 3, 3, 0, 0, 0, 0, 0,
    0, 0, 3, 3, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0
]

icon15 = [
    0, 0, 0, 5, 5, 5, 5, 5, 5,
    0, 0, 5, 0, 0, 0, 0, 0, 5,
    0, 0, 5, 5, 5, 5, 5, 5, 0,
    0, 5, 0, 0, 0, 0, 0, 5, 0,
    0, 5, 5, 5, 5, 5, 5, 0, 0,
    5, 0, 0, 0, 0, 5, 0, 0, 0,
    0, 5, 5, 5, 5, 0, 0, 0, 0,
    0, 5, 0, 0, 5, 0, 0, 0, 0,
    0, 0, 5, 5, 5, 0, 0, 0, 0
]

icon16d = [
    0, 0, 0, 0, 2, 0, 0, 0, 0,
    0, 2, 0, 0, 0, 0, 0, 2, 0,
    0, 0, 0, 2, 2, 2, 0, 0, 0,
    0, 0, 2, 2, 2, 2, 2, 0, 0,
    2, 0, 2, 2, 2, 2, 2, 0, 2,
    0, 0, 2, 2, 2, 2, 2, 0, 0,
    0, 0, 0, 2, 2, 2, 0, 0, 0,
    0, 2, 0, 0, 0, 0, 0, 2, 0,
    0, 0, 0, 0, 2, 0, 0, 0, 0
]

icon16n = [
    0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 5, 5, 5, 0, 0, 0,
    0, 0, 5, 5, 5, 5, 5, 0, 0,
    0, 5, 5, 5, 5, 1, 5, 5, 0,
    0, 5, 5, 5, 5, 0, 1, 5, 0,
    0, 5, 1, 5, 5, 5, 5, 5, 0,
    0, 0, 5, 5, 5, 5, 5, 0, 0,
    0, 0, 0, 5, 5, 5, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0
]

icon17d = [
    0, 0, 4, 4, 0, 0, 2, 2, 0,
    0, 4, 4, 4, 4, 2, 2, 2, 2,
    4, 4, 4, 4, 4, 4, 4, 2, 2,
    4, 4, 4, 4, 4, 4, 4, 4, 4,
    0, 3, 3, 3, 3, 4, 4, 4, 4,
    0, 0, 4, 4, 4, 4, 4, 0, 0,
    3, 3, 3, 3, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 3, 3, 3, 3, 0, 0, 0
]

icon17n = [
    0, 0, 4, 4, 0, 0, 5, 5, 0,
    0, 4, 4, 4, 4, 5, 5, 5, 5,
    4, 4, 4, 4, 4, 4, 4, 5, 5,
    4, 4, 4, 4, 4, 4, 4, 4, 4,
    0, 3, 3, 3, 3, 4, 4, 4, 4,
    0, 0, 4, 4, 4, 4, 4, 0, 0,
    3, 3, 3, 3, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 3, 3, 3, 3, 0, 0, 0
]

icon18 = [
    0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 4, 4, 0, 3, 3, 3, 0,
    0, 4, 4, 4, 4, 3, 3, 3, 3,
    4, 4, 4, 4, 4, 4, 4, 3, 0,
    4, 4, 4, 4, 4, 4, 4, 4, 4,
    0, 4, 4, 4, 4, 4, 4, 4, 4,
    0, 0, 4, 4, 4, 4, 4, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0
]

icon19 = [
    0, 0, 0, 0, 0, 3, 0, 0, 0,
    0, 0, 0, 0, 3, 0, 0, 0, 0,
    0, 0, 0, 3, 0, 0, 0, 0, 0,
    0, 0, 0, 3, 3, 0, 0, 0, 0,
    0, 0, 0, 3, 0, 3, 0, 0, 0,
    0, 0, 0, 0, 3, 3, 0, 0, 0,
    0, 0, 0, 0, 0, 3, 0, 0, 0,
    0, 0, 0, 0, 3, 0, 0, 0, 0,
    0, 0, 0, 3, 0, 0, 0, 0, 0
]

icon20 = [
    0, 0, 0, 0, 3, 0, 0, 0, 0,
    0, 3, 0, 0, 3, 0, 0, 3, 0,
    0, 0, 3, 0, 0, 0, 3, 0, 0,
    0, 0, 0, 0, 3, 0, 0, 0, 0,
    3, 3, 0, 3, 3, 3, 0, 3, 3,
    0, 0, 0, 0, 3, 0, 0, 0, 0,
    0, 0, 3, 0, 0, 0, 3, 0, 0,
    0, 3, 0, 0, 3, 0, 0, 3, 0,
    0, 0, 0, 0, 3, 0, 0, 0, 0
]

icon21d = [
    0, 0, 0, 0, 2, 0, 0, 0, 0,
    0, 2, 0, 0, 0, 0, 0, 2, 0,
    0, 0, 0, 2, 2, 2, 0, 0, 0,
    0, 0, 2, 2, 2, 2, 2, 0, 0,
    2, 0, 2, 2, 2, 2, 2, 0, 2,
    0, 6, 0, 0, 6, 0, 0, 6, 0,
    6, 0, 0, 6, 0, 0, 6, 0, 0,
    0, 6, 0, 0, 6, 0, 0, 6, 0,
    6, 0, 0, 6, 0, 0, 6, 0, 0
]

icon21n = [
    0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 5, 5, 5, 0, 0, 0,
    0, 0, 5, 5, 5, 5, 5, 0, 0,
    0, 5, 5, 5, 5, 5, 5, 5, 0,
    0, 5, 5, 5, 5, 5, 5, 5, 0,
    0, 6, 0, 0, 6, 0, 0, 6, 0,
    6, 0, 0, 6, 0, 0, 6, 0, 0,
    0, 6, 0, 0, 6, 0, 0, 6, 0,
    6, 0, 0, 6, 0, 0, 6, 0, 0
]

icon22 = [
    0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 4, 4, 4, 4, 4, 4, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0,
    4, 4, 4, 4, 4, 4, 0, 4, 4,
    0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 4, 4, 4, 4, 4, 4, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0
]

icon23d = [
    0, 0, 4, 4, 0, 0, 2, 2, 0,
    0, 4, 4, 4, 4, 2, 2, 2, 2,
    4, 4, 4, 4, 4, 4, 4, 2, 2,
    4, 4, 4, 4, 4, 4, 4, 4, 4,
    0, 4, 4, 3, 4, 3, 4, 4, 3,
    0, 0, 3, 4, 4, 3, 4, 3, 0,
    0, 0, 0, 0, 3, 0, 0, 0, 0,
    0, 3, 0, 0, 0, 0, 3, 0, 0,
    0, 0, 0, 3, 0, 0, 0, 0, 0
]

icon23n = [
    0, 0, 4, 4, 0, 0, 5, 5, 0,
    0, 4, 4, 4, 4, 5, 5, 5, 5,
    4, 4, 4, 4, 4, 4, 4, 5, 5,
    4, 4, 4, 4, 4, 4, 4, 4, 4,
    0, 4, 4, 3, 4, 3, 4, 4, 3,
    0, 0, 3, 4, 4, 3, 4, 3, 0,
    0, 0, 0, 0, 3, 0, 0, 0, 0,
    0, 3, 0, 0, 0, 0, 3, 0, 0,
    0, 0, 0, 3, 0, 0, 0, 0, 0
]

icon24 = [
    0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 4, 4, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 4,
    4, 4, 4, 4, 4, 4, 4, 4, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0,
    4, 4, 4, 4, 4, 4, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 4, 0, 0,
    0, 0, 0, 0, 4, 4, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0
]

arrow_x = [
    0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 1, 0, 0,
    0, 0, 0, 0, 0, 1, 1, 1, 0,
    0, 0, 0, 0, 1, 0, 1, 0, 1,
    0, 0, 0, 0, 0, 0, 1, 0, 0,
    0, 0, 0, 0, 0, 0, 1, 0, 0,
    0, 0, 0, 0, 0, 1, 0, 0, 0,
    0, 1, 1, 1, 1, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0
]

cursor = [
    1, 1, 1, 1, 1,
    1, 1, 1, 0, 0,
    1, 1, 1, 0, 0,
    1, 0, 0, 1, 0,
    1, 0, 0, 0, 1,
]

pw_icon_mapping = {
    'clear-day': icon16d,
    'clear-night': icon16n,
    'rain': icon5d,
    'snow': icon8d,
    'sleet': icon8d,
    'wind': icon22,
    'fog': icon13d,
    'cloudy': icon18,
    'partly-cloudy-day': icon14d,
    'partly-cloudy-night': icon14n,
}

def render_icon(icon: list, scale: int=1) -> Image:
    rank = int(len(icon) ** .5)
    width = rank * scale
    img = Image.new('RGBA', (width, width), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    for x in range(rank):
        for y in range(rank):
            value = icon[rank * x + y]
            if value == 0:
                # skip black pixels to be transparent.
                continue
            fill = colors[value]
            # 0, 0 -> 0, 0 - 2, 2
            # 0, 1 -> 0, 2 - 2, 4
            # x, y -> x * scale, ...
            rx, ry = y * scale, x * scale
            ex, ey = rx + (scale - 1), ry + (scale - 1)
            draw.rectangle([(rx, ry), (ex, ey)], fill=fill)
    return img

@cache
def get_icon_for_condition(condition: str, scale: int=1) -> Image:
    icon = pw_icon_mapping[condition]
    return render_icon(icon, scale)