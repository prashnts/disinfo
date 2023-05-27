import arrow

from .utilities.func import throttle
from .redis import get_dict, rkeys


@throttle(500)
def should_turn_on_display() -> bool:
    def is_motion_detected(name: str) -> bool:
        pir_state = get_dict(rkeys[name])
        if not pir_state:
            # Uninitialized state on this sensor. Assume on.
            return True

        occupied = pir_state['occupancy']
        if occupied:
            # when motion is detected, it's on.
            return True

        # When motion is NOT detected, we want to keep the display on
        # for 30 minutes during day (8h -> 23h), otherwise 5 minutes.
        # this time is in local timezone.
        last_change = arrow.get(pir_state['timestamp'])
        now = arrow.now()
        delay = 30 if 8 <= now.timetuple().tm_hour < 23 else 5
        delta = (now - last_change).total_seconds()

        return delta <= 60 * delay

    sensors = ['ha_pir_salon', 'ha_pir_kitchen']
    motion_states = [is_motion_detected(s) for s in sensors]

    # if any sensor reports True we keep the display on.
    return any(motion_states)
