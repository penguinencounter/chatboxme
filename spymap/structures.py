"""
watch v1.1 - the "spy on your friends" dynmap interface
"""
import base64
import json
from collections import namedtuple
from io import BytesIO
from math import floor
from typing import *

from PIL import Image, ImageStat
from aiohttp import ClientSession

from spymap.tools import get_batch

DynmapWorld = namedtuple('DynmapWorld', ['internal', 'external'])

DynmapPlayer = namedtuple('DynmapPlayer', ['world', 'x', 'y', 'z', 'account'])


class DynmapConfiguration:
    def __init__(self, configuration_data: dict):
        self.worlds: Tuple[DynmapWorld, ...] = tuple(map(
            lambda world: DynmapWorld(world['name'], world['title']),
            configuration_data['worlds']
        ))


def drop_excess(block: dict, fds: list):
    return {k: v for k, v in block.items() if k in fds}


class DynmapPlayerListing:
    # noinspection PyTypeChecker
    def __init__(self, player_data: dict):
        self.players: Tuple[DynmapPlayer, ...] = tuple(map(lambda x: DynmapPlayer(**drop_excess(x, DynmapPlayer._fields)), player_data['players']))


class WatchedChunk:
    def __init__(self, dx: int, dz: int):
        self.x = dx
        self.z = dz

    @classmethod
    def from_coordinates(cls, x: int, z: int):
        dx = floor(x / 32)
        dz = floor(z / -32)
        return cls(dx, dz)

    def __eq__(self, other):
        return self.x == other.x and self.z == other.z

    def __hash__(self):
        return hash((self.x, self.z))

    def __repr__(self):
        return f'WatchedChunk({self.x}, {self.z})'

    def get_url(self, world: DynmapWorld):
        return f'https://dynmap.sc3.io/tiles/{world.internal}/flat/0_0/{self.x}_{self.z}.png'

    @staticmethod
    def unitify(chunk_image: Image.Image):
        result = Image.new('RGBA', (32, 32))

        for x in range(32):
            for z in range(32):
                block = chunk_image.crop((x * 4, z * 4, x * 4 + 4, z * 4 + 4))
                average = ImageStat.Stat(block).mean
                result.putpixel((x, z), tuple(map(int, average)))

        return result

    @staticmethod
    async def fetch_group(group: "List[WatchedChunk]"):
        async with ClientSession() as session:
            responses = await get_batch(list(map(lambda chunk: chunk.get_url(), group)), session)
        responses = list(map(lambda response: (response[0], Image.open(BytesIO(response[1]))), responses))
        return list(map(lambda response: (response[0], WatchedChunk.unitify(response[1])), responses))


class ZoneRect(namedtuple("ZoneRect", ['x1', 'z1', 'x2', 'z2'])):
    def is_within(self, x, z):
        return self.x1 <= x <= self.x2 and self.z1 <= z <= self.z2


class Zone:
    def __init__(self, name: str, rects: List[ZoneRect], players: List[str] = None):
        self.name = name
        self.rects = rects
        self.players_inside = [] if players is None else players

    def is_within(self, x, z):
        return any(map(lambda rect: rect.is_within(x, z), self.rects))

    def add_player(self, player):
        if player not in self.players_inside:
            self.players_inside.append(player)

    def remove_player(self, player):
        if player in self.players_inside:
            self.players_inside.remove(player)

    # Not protected; name begins with _ to prevent name conflicts in namedtuple
    # noinspection PyProtectedMember
    def dump(self) -> dict:
        return {
            'name': self.name,
            'rects': list(map(lambda rect: rect._asdict(), self.rects)),
            'players_inside': self.players_inside
        }

    @classmethod
    def load(cls, data: dict):
        return cls(data['name'], list(map(lambda rect: ZoneRect(**rect), data['rects'])), data['players_inside'])

    @classmethod
    def import_(cls, name, encoded_zones: str):
        decoded = base64.b64decode(encoded_zones)
        HEADER = b'zonev1;'
        assert decoded.startswith(HEADER)
        data = decoded[len(HEADER):]
        return cls(name, list(map(lambda d: ZoneRect(**d), json.loads(data))))


class MembershipTier(namedtuple("MembershipTier", ['name', 'permissions', 'base_area', 'base_zones'])):
    ENTER = 1 << 0
    EXIT = 1 << 1
    COMPLEX_ZONES = 1 << 2
    TIMING = 1 << 3

    NOTHING = 0

    def permitted(self, permissions: int):
        return permissions & self.permissions == self.permissions


class MembershipTiers:
    ADMIN = MembershipTier('admin', MembershipTier.ENTER | MembershipTier.EXIT | MembershipTier.COMPLEX_ZONES | MembershipTier.TIMING, 100_000, 100)

    DEFAULT = MembershipTier('', MembershipTier.NOTHING, 0, 0)
    BASIC = MembershipTier('basic', MembershipTier.ENTER, 100, 3)
    BASIC_PLUS = MembershipTier('basic+', MembershipTier.ENTER | MembershipTier.COMPLEX_ZONES, 1_000, 10)
    STANDARD = MembershipTier('standard', MembershipTier.ENTER | MembershipTier.EXIT | MembershipTier.COMPLEX_ZONES, 10_000, 100)
    PREMIUM = MembershipTier('premium', MembershipTier.ENTER | MembershipTier.EXIT | MembershipTier.COMPLEX_ZONES | MembershipTier.TIMING, 100_000, 1000)
    EXTREME = MembershipTier('extreme', MembershipTier.ENTER | MembershipTier.EXIT | MembershipTier.COMPLEX_ZONES | MembershipTier.TIMING, 1_000_000, 10_000)


class Member:
    def __init__(self, name: str):
        self.name = name
        self.components = MembershipTiers.DEFAULT  # Bitfield
        self.area_limit = 0
        self.zoning_limit = 0
