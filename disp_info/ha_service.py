import paho.mqtt.client as mqtt
import json

from . import config
from .redis import set_dict, rkeys

def on_connect(client, userdata, flags, rc):
    print('connected!')

    client.subscribe('octoPrint/hass/printing')
    client.subscribe('zigbee2mqtt/ikea.pir.salon')

def on_message(client, userdata, msg):
    print(msg.topic, str(msg.payload))
    if msg.topic == 'octoPrint/hass/printing':
        payload = json.loads(msg.payload)
        set_dict(rkeys['octoprint_printing'], payload)
    if msg.topic == 'zigbee2mqtt/ikea.pir.salon':
        payload = json.loads(msg.payload)
        set_dict(rkeys['ha_pir_salon'], payload)


if __name__ == '__main__':
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message

    client.username_pw_set(config.ha_mqtt_username, config.ha_mqtt_password)
    client.connect(config.ha_mqtt_host, config.ha_mqtt_port, 60)

    client.loop_forever()
