import ast
import asyncio
import json
import os.path
import re
import time
from hashlib import sha256
from io import BytesIO
from math import floor, ceil
from collections import defaultdict, namedtuple

import requests
import websockets
from PIL import Image, ImageStat

import calc
from typing import *
from websockets.client import WebSocketClientProtocol

with open('key') as f:
    key = f.read().strip()

TARGET = f"wss://chat.sc3.io/v2/{key}"

COMMANDS = defaultdict(list)

if os.path.exists('switchcraft-watches.json'):
    with open('switchcraft-watches.json') as f:
        watches: dict = json.load(f)
else:
    watches = {}


def register(command: str, handler: Callable[[WebSocketClientProtocol, dict, List[str]], Coroutine]):
    COMMANDS[command].append(handler)


async def invoke(sock: WebSocketClientProtocol, data: dict):
    assert 'event' in data.keys() and data['event'] == 'command'
    for handler in COMMANDS[data['command']]:
        await handler(sock, data, data['args'])


async def cmd_calc(sock: WebSocketClientProtocol, ctx: dict, args: List[str]):
    st = ' '.join(args)
    print(f"Calculating {st}")
    print(f"Reply to {ctx['user']['name']} ({ctx['user']['uuid']})")
    # calculate the value
    try:
        response = calc.eval_expr(st)
        print(f"Got {response}")
        # send the response
        await sock.send(json.dumps({
            'type': 'tell',
            'user': ctx['user']['name'],
            'name': 'calc',
            'text': f'&e{st} = {response}',
            'mode': 'format'
        }))
        print('Done')
    except ValueError as e:
        print(f"Got ValueError")
        await sock.send(json.dumps({
            'type': 'tell',
            'user': ctx['user']['name'],
            'name': 'calc',
            'text': f'&aFailed: {e}',
            'mode': 'format'
        }))
        print('Done')
    except TypeError:
        await sock.send(json.dumps({
            'type': 'tell',
            'user': ctx['user']['name'],
            'name': 'calc',
            'text': f'&aFailed: bad input',
            'mode': 'format'
        }))
        print('Done')
    except Exception as e:
        print(e)
        await sock.send(json.dumps({
            'type': 'tell',
            'user': ctx['user']['name'],
            'name': 'calc',
            'text': f'&asomething broke: {e}',
            'mode': 'format'
        }))
        print('Done')


def save_watches():
    with open('switchcraft-watches.json', 'w') as f:
        json.dump(watches, f, indent=4)


async def cmd_watch(sock: WebSocketClientProtocol, ctx: dict, args: List[str]):
    print('watch {}'.format(' '.join(args)))

    # \watch create x z
    # ^watch -7402 9696
    # \watch x z (alias for create)
    # \watch list
    # \watch delete <id>
    # \watch delete all

    # is the first argument valid? (create, list, delete, or a number)
    x = None

    async def not_enough_arguments():
        await sock.send(json.dumps({
            'type': 'tell',
            'user': ctx['user']['name'],
            'name': 'watch',
            'text': r'&cNot enough arguments. Usage: \watch create <x> <z>, \watch list, \watch delete <id>, \watch delete all',
            'mode': 'format'
        }))

    async def too_many_arguments():
        await sock.send(json.dumps({
            'type': 'tell',
            'user': ctx['user']['name'],
            'name': 'watch',
            'text': r'&cToo many arguments. Usage: \watch create <x> <z>, \watch list, \watch delete <id>, \watch delete all',
            'mode': 'format'
        }))

    if len(args) < 1:
        await sock.send(json.dumps({
            'type': 'tell',
            'user': ctx['user']['name'],
            'name': 'watch',
            'text': r'&cwatch: dynmap spy hax; Usage: \watch create <x> <z>, \watch list, \watch delete <id>, \watch delete all',
            'mode': 'format'
        }))
        return
    if args[0] == 'create':
        mode = 'create'
        if len(args) < 3:
            await not_enough_arguments()
            return
        if len(args) > 3:
            await too_many_arguments()
            return
    elif args[0] == 'list':
        mode = 'list'
        if len(args) > 1:
            await too_many_arguments()
            return
    elif args[0] == 'delete':
        mode = 'delete'
        if len(args) < 2:
            await not_enough_arguments()
            return
        if len(args) > 2:
            await too_many_arguments()
            return
    elif calc.is_integer(args[0]):
        mode = 'create'
        x = int(args[0])
        if len(args) < 2:
            await not_enough_arguments()
            return
        if len(args) > 2:
            await too_many_arguments()
            return
    else:
        # fail
        await sock.send(json.dumps({
            'type': 'tell',
            'user': ctx['user']['name'],
            'name': 'watch',
            'text': r'&cFailed: invalid first argument.'
                    r' Usage: \watch create <x> <z>, \watch list, \watch delete <id>, \watch delete all',
            'mode': 'format'
        }))
        return
    if mode == 'create':
        nudge = 0 if x is None else -1
        if x is None:
            if not calc.is_integer(args[1]):
                await sock.send(json.dumps({
                    'type': 'tell',
                    'user': ctx['user']['name'],
                    'name': 'watch',
                    'text': r'&cFailed: x (argument 2) must be an integer',
                    'mode': 'format'
                }))
                return
            x = int(args[1])
        if not calc.is_integer(args[2 + nudge]):
            await sock.send(json.dumps({
                'type': 'tell',
                'user': ctx['user']['name'],
                'name': 'watch',
                'text': rf'&cFailed: z (argument {3 + nudge}) must be an integer',
                'mode': 'format'
            }))
            return
        y = int(args[2 + nudge])
        print(f"Watching {x} {y}")

        # calculate the dynmap position
        dx = floor(x / 32)
        dy = floor(y / -32)
        print(f"Dynamic map position: {dx} {dy}")

        for n in watches.values():
            if n['dx'] == dx and n['dy'] == dy and n['owner'] == ctx['user']['uuid']:
                await sock.send(json.dumps({
                    'type': 'tell',
                    'user': ctx['user']['name'],
                    'name': 'watch',
                    'text': rf'&6already watching this area (try &c\watch delete {n["id"]}&6)',
                    'mode': 'format'
                }))
                return

        # resp = requests.get(f"https://dynmap.sc3.io/tiles/SwitchCraft/flat/0_0/{dx}_{dy}.png")
        top_left_world_corner = (dx * 32, dy * -32 - 1)
        print(f"Top left world corner: {top_left_world_corner}")
        bottom_right_world_corner = (top_left_world_corner[0] + 31, top_left_world_corner[1] - 31)
        print(f"Bottom right world corner: {bottom_right_world_corner}")
        next_id = max(map(lambda e: e['id'], watches.values())) + 1 if len(watches) > 0 else 1
        watch_data_struct = {
            'id': next_id,
            'dx': dx,
            'dy': dy,
            'owner': ctx['user']['uuid'],  # UUID can't change, but name can.
        }

        watches[str(next_id)] = watch_data_struct

        await sock.send(json.dumps({
            'type': 'tell',
            'user': ctx['user']['name'],
            'name': 'watch',
            'text': f'Success. [image](https://dynmap.sc3.io/tiles/SwitchCraft/flat/0_0/{dx}_{dy}.png)',
            'mode': 'markdown'
        }))

        save_watches()
    elif mode == 'list':
        if len(watches) == 0:
            await sock.send(json.dumps({
                'type': 'tell',
                'user': ctx['user']['name'],
                'name': 'watch',
                'text': r'&6No watches',
                'mode': 'format'
            }))
            return
        text = r'&6Watches:'
        for n in watches.values():
            if n['owner'] == ctx['user']['uuid']:
                text += f' &c{n["id"]}&6: (&c{32 * n["dx"]}&6, &c{-32 * (n["dy"] + 1)}&6);'
        await sock.send(json.dumps({
            'type': 'tell',
            'user': ctx['user']['name'],
            'name': 'watch',
            'text': text,
            'mode': 'format'
        }))
    elif mode == 'delete':
        if args[1] == 'all':
            for watch_id, watch_data in watches.copy().items():
                if watch_data['owner'] == ctx['user']['uuid']:
                    del watches[watch_id]
            await sock.send(json.dumps({
                'type': 'tell',
                'user': ctx['user']['name'],
                'name': 'watch',
                'text': r'&6Deleted all of your watches',
                'mode': 'format'
            }))
            save_watches()
            return
        if not calc.is_integer(args[1]):
            await sock.send(json.dumps({
                'type': 'tell',
                'user': ctx['user']['name'],
                'name': 'watch',
                'text': r'&cFailed: id (argument 2) must be an integer',
                'mode': 'format'
            }))
            return
        id_ = int(args[1])
        if str(id_) not in watches:
            await sock.send(json.dumps({
                'type': 'tell',
                'user': ctx['user']['name'],
                'name': 'watch',
                'text': r'&cFailed: no such watch',
                'mode': 'format'
            }))
            return
        if watches[str(id_)]['owner'] != ctx['user']['uuid']:
            await sock.send(json.dumps({
                'type': 'tell',
                'user': ctx['user']['name'],
                'name': 'watch',
                'text': r'&cFailed: you do not own that watch',
                'mode': 'format'
            }))
            return
        del watches[str(id_)]
        await sock.send(json.dumps({
            'type': 'tell',
            'user': ctx['user']['name'],
            'name': 'watch',
            'text': r'&6Deleted watch',
            'mode': 'format'
        }))
        save_watches()
    else:
        print('Not Implemented action {}'.format(mode))


register('calc', cmd_calc)
register('watch', cmd_watch)


NameUUID = namedtuple('NameUUID', ['name', 'uuid'])
player_cache: Set[NameUUID] = set()


async def update_dynmap_data(w):
    print('Updating...')

    if not os.path.exists('map_cache'):
        os.mkdir('map_cache')

    # go over the watch list
    for watch_id, watch_data in watches.copy().items():
        print('Updating: watch {}'.format(watch_id))
        if 'img_hash' not in watch_data:
            watch_data['img_hash'] = None
        if 'queue' not in watch_data:
            watch_data['queue'] = []
        # download the image
        resp = requests.get(
            f"https://dynmap.sc3.io/tiles/SwitchCraft/flat/0_0/{watch_data['dx']}_{watch_data['dy']}.png")
        image = Image.open(BytesIO(resp.content))
        blockmeta = Image.new('RGBA', (32, 32), (0, 0, 0, 0))
        # take every 4x4 pixel block and get the average color
        for x in range(32):
            for y in range(32):
                block = image.crop((x * 4, y * 4, x * 4 + 4, y * 4 + 4))
                average = ImageStat.Stat(block).mean
                blockmeta.putpixel((x, y), tuple(map(int, average)))
        hash_rn = sha256(resp.content).hexdigest()
        # check if the image is different
        if hash_rn != watch_data['img_hash']:
            if os.path.exists(f'map_cache/blocks_{watch_id}.png'):
                old_blockmeta = Image.open(f'map_cache/blocks_{watch_id}.png')
                # check how many pixels are different
                diff = 0
                for x in range(32):
                    for y in range(32):
                        if blockmeta.getpixel((x, y)) != old_blockmeta.getpixel((x, y)):
                            diff += 1
                diff = str(diff)
            else:
                diff = "unknown"
            # if it is, send the new image
            xpos = 32 * watch_data['dx']
            ypos = -32 * (watch_data['dy'] + 1)
            # is the player online?
            if watch_data['owner'] in map(lambda e: e.uuid, player_cache):
                # if so, send the image
                target_name = next(filter(lambda e: e.uuid == watch_data['owner'], player_cache)).name
                print('Sent update to {}'.format(target_name))
                await w.send(json.dumps({
                    'type': 'tell',
                    'user': target_name,
                    'name': 'watch',
                    'text': f'Watch #{watch_id} *({xpos}, {ypos})* triggered (**{diff}** blocks changed): [image](https://dynmap.sc3.io/tiles/SwitchCraft/flat/0_0/{watch_data["dx"]}_{watch_data["dy"]}.png)',
                    'mode': 'markdown'
                }))
            else:
                print('Player not online')
            # update the hash
            watch_data['img_hash'] = hash_rn
        # write hash data
        watches[watch_id] = watch_data
        blockmeta.save(f'map_cache/blocks_{watch_id}.png')
    save_watches()


tasks = {
    30: [
        update_dynmap_data
    ]
}

last_tick = time.time()


async def main():
    global tasks, last_tick, player_cache
    async with websockets.connect(TARGET) as websocket:
        websocket: WebSocketClientProtocol
        while True:
            message = await websocket.recv()
            data = json.loads(message)
            if data['type'] == 'hello':
                if data['ok']:
                    print('OK')
                    break
                else:
                    raise RuntimeError('KO (for some reason, the Hello packet had ok=false).')

        while True:
            try:
                message = await asyncio.wait_for(websocket.recv(), timeout=0.1)
                data: dict = json.loads(message)
                if 'event' in data.keys():
                    if data['event'] == 'command':
                        await invoke(websocket, data)
                    elif data['event'] == 'join':
                        player_cache.add(NameUUID(data['user']['name'], data['user']['uuid']))
                    elif data['event'] == 'leave':
                        player_cache.remove(NameUUID(data['user']['name'], data['user']['uuid']))
                elif 'error' in data.keys():
                    print('Error occurred. {}'.format(data['error']))
                elif 'type' in data.keys() and data['type'] == 'players':
                    player_cache = set(map(lambda package: NameUUID(package['name'], package['uuid']), data['players']))
            except asyncio.TimeoutError:
                # Do other, background tasks here
                current_tick = time.time()
                for wait, jobs in tasks.items():
                    # did we wait long enough?
                    # over the whole numbered seconds between last_tick and current_tick
                    # is that N seconds mod wait == 0?
                    for i in range(ceil(last_tick), floor(current_tick) + 1):
                        if i % wait == 0:
                            for job in jobs:
                                await job(websocket)
                last_tick = current_tick


async def main_ka():
    from websockets.exceptions import ConnectionClosed, ConnectionClosedError, ConnectionClosedOK
    print(f'Keep-alive enabled...')
    while True:
        try:
            await main()
        except ConnectionClosedOK as e:
            print(f'Connection closed (ok) ({e.code}). Reconnecting...')
        except ConnectionClosedError as e:
            print(f'Connection closed (bad) ({e.code}). Reconnecting...')
        except ConnectionClosed as e:
            print(f'Connection closed ({e.code}). Reconnecting...')
        except Exception as e:
            print(f'Unknown exception: {e}. Attempting reconnect...')
        await asyncio.sleep(1)


asyncio.run(main_ka())
