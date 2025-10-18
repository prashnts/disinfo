import threading

from .di_remote import sensor_loop

def gesture_detector(callback):
    try:
        threading.Thread(target=sensor_loop, args=(callback,), daemon=True).start()
        print('[Gestures] Enabled')
    except ImportError:
        print('[Gestures] Not enabled')
