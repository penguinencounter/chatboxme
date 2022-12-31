import time
from sqlite3 import connect

import requests

from spymap.structures import DynmapConfiguration

CONFIGURATION_URL = 'https://dynmap.sc3.io/up/configuration'
UPDATE_URL = 'https://dynmap.sc3.io/up/world/{}/{}'  # first {} is world, second {} is last update time


def get_configuration():
    """Get the configuration from the configuration URL."""
    response = requests.get(CONFIGURATION_URL)
    return DynmapConfiguration(response.json())


last_update = 0


def get_updates(conf: DynmapConfiguration) -> dict:
    """Get updates from the update URL."""
    global last_update
    responses = {}
    for world in conf.worlds:
        response = requests.get(UPDATE_URL.format(world.internal, last_update))
        responses[world.internal] = response.json()
    last_update = int(time.time())
    return responses
