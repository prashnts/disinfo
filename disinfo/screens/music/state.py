from disinfo.data_structures import FrameState, AppBaseModel
from disinfo.drat.app_states import PubSubMessage, PubSubStateManager
from disinfo import config


class MediaData(AppBaseModel):
    title: str = ''
    album: str = ''
    artist: str = ''
    source: str = ''
    album_art: str = ''

class MusicState(AppBaseModel):
    playing: bool = False
    paused: bool = False
    data: MediaData = MediaData()

    is_visible: bool = False



class MusicStateManager(PubSubStateManager[MusicState]):
    model = MusicState
    channels = ('di.pubsub.music',)

    # Tracks a single speaker source.

    def process_message(self, channel: str, data: PubSubMessage):
        if data.action != 'update':
            return

        s = data.payload['new_state']

        if s['entity_id'] != config.speaker_source:
            return

        self.state.data = MediaData(
            title=s['attributes'].get('media_title', ''),
            album=s['attributes'].get('media_album_name', ''),
            artist=s['attributes'].get('media_artist', ''),
            source=s['attributes'].get('source', ''),
        )
        self.state.playing = s['state'] == 'playing'
        self.state.paused = s['state'] == 'paused'

        state['playing'] = s['state'] == 'playing'
        state['paused'] = s['state'] == 'paused'

        last_updated = arrow.get(s['last_updated']).to('local')
        now = arrow.now()

        state['media_title'] = s['attributes'].get('media_title')
        state['media_album'] = s['attributes'].get('media_album_name')
        state['media_artist'] = s['attributes'].get('media_artist')

        state['is_spotify'] = 'Spotify' in s['attributes'].get('source', '')
        state['album_art'] = get_album_art(
            s['attributes'].get('entity_picture'),
            media_album=state['media_album'],
            is_spotify=state['is_spotify'])

        timeout_delay = 40 if state['playing'] else 2

        state['is_visible'] = all([
            state['playing'] or state['paused'],
            state['media_title'] != 'TV',
            (last_updated + timedelta(minutes=timeout_delay)) > now,
        ])

        return state


