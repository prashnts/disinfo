import paho.mqtt.client as mqtt
import json
import arrow

from .. import config
from ..redis import set_dict, rkeys, db
from .data_service import get_metro_info

pir_topic_map = {
    'zigbee2mqtt/ikea.pir.salon': 'ha_pir_salon',
    'zigbee2mqtt/ikea.pir.kitchen': 'ha_pir_kitchen',
}

latch_timing = {
    'scene_1': 1_000,
    'scene_3': 10_000,
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

def on_message(client, userdata, msg):
    # print(msg.topic, str(msg.payload))
    if msg.topic == 'ha_root':
        # filter.
        payload = json.loads(msg.payload)
        if payload['event_type'] == 'state_changed':
            event = payload['event_data']
            event['_timestamp'] = arrow.now().isoformat()
            if event['entity_id'] == 'media_player.sonos_beam':
                set_dict(rkeys['ha_sonos_beam'], event)
            if event['entity_id'] == 'sensor.enviomental_lux':
                set_dict(rkeys['ha_enviomental_lux'], event)
            if event['entity_id'] == 'sensor.driplant_soil_cap':
                set_dict(rkeys['ha_driplant_volts'], event)
    if msg.topic == 'octoPrint/hass/printing':
        payload = json.loads(msg.payload)
        set_dict(rkeys['octoprint_printing'], payload)
    if msg.topic == 'octoPrint/temperature/bed':
        payload = json.loads(msg.payload)
        set_dict(rkeys['octoprint_bedt'], payload)
    if msg.topic == 'octoPrint/temperature/tool0':
        payload = json.loads(msg.payload)
        set_dict(rkeys['octoprint_toolt'], payload)
    if msg.topic in pir_topic_map:
        payload = json.loads(msg.payload)
        payload['timestamp'] = arrow.now().isoformat()
        set_dict(rkeys[pir_topic_map[msg.topic]], payload)
    if msg.topic == 'zigbee2mqtt/enki.rmt.0x03':
        # We will retain the messages with a timeout.
        payload = json.loads(msg.payload)
        if payload['action']:
            ttl = config.mqtt_btn_latch_t
            if payload['action'] in latch_timing:
                ttl = latch_timing[payload['action']]
            if payload['action'] == 'scene_2':
                get_metro_info(force=True)
            db.set(rkeys['ha_enki_rmt'], msg.payload, px=ttl)
    if msg.topic == 'zigbee2mqtt/ikea.rmt.0x01':
        payload = json.loads(msg.payload)
        ttl = config.mqtt_btn_latch_t
        if payload['action']:
            if payload['action'] == 'toggle':
                get_metro_info(force=True)
            db.set(rkeys['ha_ikea_rmt_0x01'], msg.payload, px=ttl)


if __name__ == '__main__':
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message

    client.username_pw_set(config.ha_mqtt_username, config.ha_mqtt_password)
    client.connect(config.ha_mqtt_host, config.ha_mqtt_port, 60)

    client.loop_forever()
