import paho.mqtt.client as mqtt
import json

from . import config
from .redis import set_dict, rkeys, db

topic_key_map = {
    'octoPrint/hass/printing': 'octoprint_printing',
    'zigbee2mqtt/ikea.pir.salon': 'ha_pir_salon',
    'zigbee2mqtt/enki.rmt.0x03': 'ha_enki_rmt',
}

def on_connect(client, userdata, flags, rc):
    print('connected!')

    client.subscribe('octoPrint/hass/printing')
    client.subscribe('zigbee2mqtt/ikea.pir.salon')
    client.subscribe('zigbee2mqtt/enki.rmt.0x03')   # Remote to control the display

def on_message(client, userdata, msg):
    print(msg.topic, str(msg.payload))
    if msg.topic == 'octoPrint/hass/printing':
        payload = json.loads(msg.payload)
        set_dict(rkeys['octoprint_printing'], payload)
    if msg.topic == 'zigbee2mqtt/ikea.pir.salon':
        payload = json.loads(msg.payload)
        set_dict(rkeys['ha_pir_salon'], payload)
    if msg.topic == 'zigbee2mqtt/enki.rmt.0x03':
        # We will retain the messages with a timeout.
        payload = json.loads(msg.payload)
        if payload['action']:
            ttl = 300
            if payload['action'] == 'scene_1':
                ttl = 1000
            db.set(rkeys['ha_enki_rmt'], msg.payload, px=ttl)
        # set_dict(rkeys['ha_enki_rmt'], payload)


if __name__ == '__main__':
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message

    client.username_pw_set(config.ha_mqtt_username, config.ha_mqtt_password)
    client.connect(config.ha_mqtt_host, config.ha_mqtt_port, 60)

    client.loop_forever()
