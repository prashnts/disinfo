import os
import json

from hub75_websocket_client import Config, main


if __name__ == "__main__":
    try:
        with open(os.environ.get('DI_WEBSOCKET_CLIENT_CONFIG', '.config.json')) as fp:
            conf = Config(**json.load(fp))
    except FileNotFoundError:
        conf = Config()

    main(conf)
