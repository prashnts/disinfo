import paho.mqtt.client as mqtt
import json
import arrow

from .. import config
from ..redis import set_dict, rkeys, db, get_dict, publish

pir_topic_map = {
    'zigbee2mqtt/ikea.pir.salon': 'ha_pir_salon',
    'zigbee2mqtt/ikea.pir.kitchen': 'ha_pir_kitchen',
}

latch_timing = {
    'scene_1': 1_000,
    'scene_3': 10_000,
}

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


def on_connect(client, userdata, flags, rc):
    print('connected!')

    client.subscribe('octoPrint/hass/printing')
    client.subscribe('octoPrint/temperature/bed')
    client.subscribe('octoPrint/temperature/tool0')
    client.subscribe('zigbee2mqtt/enki.rmt.0x03')   # Remote to control the display
    client.subscribe('zigbee2mqtt/ikea.rmt.0x01')   # Kitchen Remote
    client.subscribe('ha_root')   # Get ALL HomeAssistant data.

    for topic in pir_topic_map.keys():
        # subscribe to PIR sensor states
        client.subscribe(topic)

def on_disconnect(client, userdata, rc):
    if rc != 0:
        print('Unexpected MQTT disconnection.')

def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload)
        print('payload', msg.payload)
    except TypeError:
        print(f'Got non-json payload. topic={msg.topic}, payload={msg.payload}')
        return

    if msg.topic == 'ha_root':
        # filter.
        if payload['event_type'] == 'state_changed':
            event = payload['event_data']
            event['_timestamp'] = arrow.now().isoformat()
            if event['entity_id'] == 'media_player.sonos_beam':
                set_dict(rkeys['ha_sonos_beam'], event)
            if event['entity_id'] == 'sensor.enviomental_lux':
                publish('di.pubsub.lux', action='update', payload=event)
            if event['entity_id'] == 'sensor.driplant_soil_cap':
                set_dict(rkeys['ha_driplant_volts'], event)
    if msg.topic == 'octoPrint/hass/printing':
        set_dict(rkeys['octoprint_printing'], payload)
    if msg.topic == 'octoPrint/temperature/bed':
        set_dict(rkeys['octoprint_bedt'], payload)
    if msg.topic == 'octoPrint/temperature/tool0':
        set_dict(rkeys['octoprint_toolt'], payload)
    if msg.topic in pir_topic_map:
        payload['timestamp'] = arrow.now().isoformat()
        set_dict(rkeys[pir_topic_map[msg.topic]], payload)
        publish('di.pubsub.pir', action='update', payload=dict(sensor=pir_topic_map[msg.topic], **payload))
    if msg.topic == 'zigbee2mqtt/enki.rmt.0x03':
        # We will retain the messages with a timeout.
        if payload['action']:
            publish('di.pubsub.remote', action=rmt_enki_keymap.get(payload['action'], 'unknown'))

    if msg.topic == 'zigbee2mqtt/ikea.rmt.0x01':
        if payload['action']:
            # db.set(rkeys['ha_ikea_rmt_0x01'], msg.payload, px=ttl)
            publish('di.pubsub.remote', action=rmt_ikea_keymap.get(payload['action'], 'unknown'))


if __name__ == '__main__':
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message
    client.on_disconnect = on_disconnect

    client.username_pw_set(config.ha_mqtt_username, config.ha_mqtt_password)
    client.connect(config.ha_mqtt_host, config.ha_mqtt_port, 60)

    client.loop_forever()
    print("Exited")
