import asyncio
import wave
import sys
import pyaudio
import rich
import time

from shazamio import Shazam

from ..redis import publish
from .data_service import SafeScheduler

CHUNK = 1024
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 48000
RECORD_SECONDS = 6
DEVICE_INDEX = 6

async def recognize():
    destination = '/tmp/shazamioinput.wav'
    with wave.open(destination, 'wb') as wf:
        p = pyaudio.PyAudio()
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(p.get_sample_size(FORMAT))
        wf.setframerate(RATE)

        stream = p.open(format=FORMAT, channels=CHANNELS, rate=RATE, input=True, input_device_index=DEVICE_INDEX)

        print('Recording...')
        publish('di.pubsub.shazam', action='begin-recording')
        for _ in range(0, RATE // CHUNK * RECORD_SECONDS):
            wf.writeframes(stream.read(CHUNK))
        publish('di.pubsub.shazam', action='end-recording')
        print('Done')

        stream.close()
        p.terminate()

    shazam = Shazam()
    return await shazam.recognize(destination)

def recognize_music():
    results = asyncio.run(recognize())

    try:
        track = results['track']
        title = track['title']
        subtitle = track['subtitle']
        coverart = track['images']['coverart']
        data = {
            'title': title,
            'subtitle': subtitle,
            'coverart': coverart
        }
    except (KeyError, TypeError):
        print('Could not recognize music')    
        data = {}

    publish('di.pubsub.shazam', action='update', payload=data)

def get_recognized_music():
    try:
        print('[i] [fetch] recognized music')
        recognize_music()
    except Exception as e:
        publish('di.pubsub.shazam', action='end-recording')
        print('[e] shazam', e)

scheduler = SafeScheduler(reschedule_on_failure=True)
scheduler.every(10).seconds.do(get_recognized_music)

if __name__ == '__main__':
    scheduler.run_all(1)
    while True:
        scheduler.run_pending()
        time.sleep(1)
