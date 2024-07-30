import math
import cartopy

from disinfo.config import app_config


earth_radius = 6371

source_transform = cartopy.crs.Geodetic()
screen_transform = cartopy.crs.epsg(4087)


def bbox(center: tuple[float, float], radius: tuple[float, float]):
    x, y = screen_transform.transform_point(center[0], center[1], source_transform)

    return (
        (x - radius[0], y - radius[1]),
        (x + radius[0], y + radius[1]),
    )

def lat_long_zoom_to_xy(lat: float, long: float):
    return screen_transform.transform_point(lat, long, source_transform)

def scale_xy_to_screen(x: float, y: float, bbox: tuple):
    order = max(app_config.width, app_config.height) / 2
    x = (x - bbox[0][0]) / (bbox[1][0] - bbox[0][0]) * order
    y = (y - bbox[0][1]) / (bbox[1][1] - bbox[0][1]) * order
    return y, order - x
