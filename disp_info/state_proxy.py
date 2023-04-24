import arrow

from .redis import get_dict, rkeys

def should_turn_on_display() -> bool:
    pir_state = get_dict(rkeys['ha_pir_salon'])
    if not pir_state:
        # Uninitialized state is always on.
        return True

    occupied = pir_state['occupancy']

    if occupied:
        # when motion is detected, it's on.
        return True

    # when motion is NOT detected, we want to keep the display on
    # for 30 minutes during day (8h -> 23h), otherwise 5 minutes.
    # this time is in local timezone.
    last_change = arrow.get(pir_state['timestamp'])
    now = arrow.now()
    delay = 30 if 8 <= now.timetuple().tm_hour < 23 else 5
    delta = (now - last_change).total_seconds()

    if delta <= 60 * delay:
        return True

    return False
