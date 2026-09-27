from discore.cairo import load_svg_string
from discore.layers import styled_div


def render_emoji(text: str, size: int = 14):
    fontsize = size * 0.8
    w = size * 1
    h = size * 1
    template = f'''<?xml version="1.0" encoding="UTF-8"?>
<svg width="{w}px" height="{h}px" viewBox="0 0 {w} {h}" version="1.1" xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">
    <title>Artboard</title>
    <g id="Artboard" stroke="none" stroke-width="1" fill="none" fill-rule="evenodd" font-family="AppleColorEmoji, Apple Color Emoji" font-size="{fontsize}" font-weight="normal" line-spacing="{fontsize}">
        <text id="" fill="#000000">
            <tspan x="0" y="{size * 0.8}">{text}</tspan>
        </text>
    </g>
</svg>'''
    # div = styled_div(border=1, border_color='#FF0000', padding=1, radius=2, margin=1)
    div = styled_div()
    return div(load_svg_string(template))