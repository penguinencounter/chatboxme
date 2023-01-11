import asyncio
import json
import os.path
import time
from collections import defaultdict, namedtuple
from math import floor, ceil
from sqlite3 import Connection
from typing import *

import websockets
from websockets.client import WebSocketClientProtocol
from websockets.exceptions import InvalidStatusCode

import calc
from krist import kauth
from spymap import based
from spymap.integration import get_configuration, get_updates

DYNMAP_CONF = get_configuration()

with open('key') as f:
    key = f.read().strip()

TARGET = f"wss://chat.sc3.io/v2/{key}"

COMMANDS = defaultdict(list)

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


async def cmd_whereis(sock: WebSocketClientProtocol, ctx: dict, args: List[str]):
    if len(args) != 1:
        await sock.send(json.dumps({
            'type': 'tell',
            'user': ctx['user']['name'],
            'name': 'whereis',
            'text': r'&cFailed: invalid arguments; \whereis <player>',
            'mode': 'format'
        }))
        return
    name = args[0]
    await sock.send(json.dumps({
        'type': 'tell',
        'user': ctx['user']['name'],
        'name': 'whereis',
        'text': based.player_report(name),
        'mode': 'format'
    }))


async def cmd_dbhealth(sock: WebSocketClientProtocol, ctx: dict, _: List[str]):
    print(ctx['user']['name'].lower(), 'requested db health')
    if ctx['user']['name'].lower() != "penguinencounter":
        return
    await sock.send(json.dumps({
        'type': 'tell',
        'user': ctx['user']['name'],
        'name': 'dbhealth',
        'text': based.dbhealth_report(),
        'mode': 'format'
    }))


register('calc', cmd_calc)
register('whereis', cmd_whereis)
register('dbhealth', cmd_dbhealth)


NameUUID = namedtuple('NameUUID', ['name', 'uuid'])
player_cache: Set[NameUUID] = set()


async def process_kauth(_: WebSocketClientProtocol):
    kauth.read_incoming()


async def track(_: WebSocketClientProtocol):
    based.auto_fetch(DYNMAP_CONF)


tasks = {
    2: [
        process_kauth,
        track
    ]
}

last_tick = time.time()


async def main(conn: Connection):
    global tasks, last_tick, player_cache
    cursor = conn.cursor()
    based.player_init_tables(cursor)
#    based.fixup_updates(cursor)
    conn.commit()
    cursor.close()
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
                        if NameUUID(data['user']['name'], data['user']['uuid']) in player_cache:
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
                    if wait == 0:
                        for job in jobs:
                            await job(websocket)
                        return
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
            with based.player_connector() as conn:
                await main(conn)
        except ConnectionClosedOK as e:
            print(f'Connection closed (ok) ({e.code}). Reconnecting...')
        except ConnectionClosedError as e:
            print(f'Connection closed (bad) ({e.code}). Reconnecting...')
        except ConnectionClosed as e:
            print(f'Connection closed ({e.code}). Reconnecting...')
        except InvalidStatusCode as e:
            print(f'Invalid status code ({e.status_code}). Reconnecting...')
        except Exception as e:
            print(f'Unknown exception: {type(e)} {e}. Attempting reconnect...')
            # raise
        await asyncio.sleep(1)


asyncio.run(main_ka())
