import asyncio
import wave
import sys
import pyaudio
import rich

from shazamio import Shazam

CHUNK = 1024
FORMAT = pyaudio.paInt16
CHANNELS = 1 if sys.platform == 'darwin' else 2
RATE = 44100
RECORD_SECONDS = 8

async def recognize():
    destination = '/tmp/shazamioinput.wav'
    with wave.open(destination, 'wb') as wf:
        p = pyaudio.PyAudio()
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(p.get_sample_size(FORMAT))
        wf.setframerate(RATE)

        stream = p.open(format=FORMAT, channels=CHANNELS, rate=RATE, input=True)

        print('Recording...')
        for _ in range(0, RATE // CHUNK * RECORD_SECONDS):
            wf.writeframes(stream.read(CHUNK))
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
    except (KeyError, TypeError):
        print('Could not recognize music')
        return
    
    return {
        'title': title,
        'subtitle': subtitle,
        'coverart': coverart
    }


if __name__ == '__main__':
    print(recognize_music())