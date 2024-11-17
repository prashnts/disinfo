import asyncio
import wave
import sys
import pyaudio
import rich
import time

from shazamio import Shazam

from ..redis import publish
from ..config import app_config
from .data_service import SafeScheduler

async def recognize():
    destination = '/tmp/shazamioinput.wav'
    RATE = app_config.shazam.sample_rate
    CHUNK = app_config.shazam.chunk
    RECORD_SECONDS = app_config.shazam.record_duration
    FORMAT = pyaudio.paInt16

    with wave.open(destination, 'wb') as wf:
        p = pyaudio.PyAudio()
        wf.setnchannels(app_config.shazam.channels)
        wf.setsampwidth(p.get_sample_size(FORMAT))
        wf.setframerate(app_config.shazam.sample_rate)

        stream = p.open(
            format=FORMAT,
            channels=app_config.shazam.channels,
            rate=app_config.shazam.sample_rate,
            input=True,
            input_device_index=app_config.shazam.device_index)

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
scheduler.every(18).seconds.do(get_recognized_music)

if __name__ == '__main__':
    scheduler.run_all(1)
    while True:
        scheduler.run_pending()
        time.sleep(1)
