import paho.mqtt.client as mqtt

import json
import arrow

from ..config import app_config
from ..redis import set_dict, rkeys, db, get_dict, publish

rmt_enki_keymap = {
    'color_saturation_step_up': 'up',
    'color_saturation_step_down': 'down',
    'color_hue_step_up': 'right',
    'color_hue_step_down': 'left',
    'scene_1': 'btn_metro',
    'scene_2': 'btn_twentytwo',
    'scene_3': 'btn_debug',
}
rmt_ikea_keymap = {
    'brightness_up_click': 'up',
    'brightness_down_click': 'down',
    'arrow_right_click': 'right',
    'arrow_left_click': 'left',
    'toggle': 'btn_metro',
}


def on_connect(client, userdata, flags, reason_code, properties=None):
    print('connected!')

    client.subscribe('zigbee2mqtt/enki.rmt.0x03')   # Remote to control the display
    client.subscribe('zigbee2mqtt/ikea.rmt.0x01')   # Kitchen Remote
    client.subscribe('zigbee2mqtt/aqara.contact.dishwasher')   # Dishwasher contact
    client.subscribe('ha_root')   # Get ALL HomeAssistant data.

def on_disconnect(client, userdata, rc):
    print('Unexpected MQTT disconnection.')


def notify(channel: str, action: str, payload: dict = {}, persist: bool = False):
    publish(channel, action, payload)
    if persist:
        db.set(f'state_{channel}', json.dumps(payload))


def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload)
    except TypeError:
        print(f'Got non-json payload. topic={msg.topic}, payload={msg.payload}')
        return

    if msg.topic == 'ha_root':
        # filter.
        if payload['event_type'] == 'state_changed':
            event = payload['event_data']
            event['_timestamp'] = arrow.now().isoformat()
            if 'media_player.' in event['entity_id']:
                publish('di.pubsub.music', action='update', payload=event)
            if event['entity_id'] == 'media_player.sonos_beam':
                set_dict(rkeys['ha_sonos_beam'], event)
            if event['entity_id'] in app_config.monitors.ambient_light_sensors:
                notify('di.pubsub.lux', action='update', payload=event)
            if event['entity_id'] == 'sensor.driplant_soil_cap':
                set_dict(rkeys['ha_driplant_volts'], event)
            if event['entity_id'] in app_config.monitors.presence_sensors:
                notify('di.pubsub.presence', action='update', payload=event)

    if msg.topic == 'octoPrint/hass/printing':
        set_dict(rkeys['octoprint_printing'], payload)
    if msg.topic == 'octoPrint/temperature/bed':
        set_dict(rkeys['octoprint_bedt'], payload)
    if msg.topic == 'octoPrint/temperature/tool0':
        set_dict(rkeys['octoprint_toolt'], payload)
    if msg.topic == 'zigbee2mqtt/enki.rmt.0x03':
        # We will retain the messages with a timeout.
        if payload['action']:
            publish('di.pubsub.remote', action=rmt_enki_keymap.get(payload['action'], 'unknown'))
    if msg.topic == 'zigbee2mqtt/aqara.contact.dishwasher':
        # print('Dishwasher contact:', payload)
        publish('di.pubsub.dishwasher', action='trigger')
    if msg.topic == 'zigbee2mqtt/ikea.rmt.0x01':
        if payload['action']:
            # db.set(rkeys['ha_ikea_rmt_0x01'], msg.payload, px=ttl)
            publish('di.pubsub.remote', action=rmt_ikea_keymap.get(payload['action'], 'unknown'))


if __name__ == '__main__':
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect
    client.on_message = on_message
    client.on_disconnect = on_disconnect

    client.username_pw_set(app_config.ha_mqtt_username, app_config.ha_mqtt_password)
    client.connect(app_config.ha_mqtt_host, app_config.ha_mqtt_port, 60)

    client.loop_forever()
