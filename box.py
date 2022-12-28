import ast
import asyncio
import json

import websockets

import calc

with open('key') as f:
    key = f.read().strip()

TARGET = f"wss://chat.sc3.io/v2/{key}"


async def main():
    async with websockets.connect(TARGET) as websocket:
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
            message = await websocket.recv()
            data: dict = json.loads(message)
            if 'event' in data.keys() and data['event'] == 'command':
                if data['command'] == 'calc':
                    st = ' '.join(data['args'])
                    print(f"Calculating {st}")
                    # calculate the value
                    try:
                        response = calc.eval_expr(st)
                        print(f"Got {response}")
                        print(f"Reply to {data['user']['name']} ({data['user']['uuid']})")
                        # send the response
                        await websocket.send(json.dumps({
                            'type': 'tell',
                            'user': data['user']['name'],
                            'name': 'calc',
                            'text': f'&e{st} = {response}',
                            'mode': 'format'
                        }))
                        print('Done')
                    except ValueError as e:
                        print(f"Got ValueError")
                        print(f"Reply to {data['user']['name']} ({data['user']['uuid']})")
                        await websocket.send(json.dumps({
                            'type': 'tell',
                            'user': data['user']['name'],
                            'name': 'calc',
                            'text': f'&aFailed: {e}',
                            'mode': 'format'
                        }))
                        print('Done')
                    except TypeError as e:
                        print(f"Reply to {data['user']['name']} ({data['user']['uuid']})")
                        await websocket.send(json.dumps({
                            'type': 'tell',
                            'user': data['user']['name'],
                            'name': 'calc',
                            'text': f'&aFailed: bad input',
                            'mode': 'format'
                        }))
                        print('Done')
                    except Exception as e:
                        print(e)
                        await websocket.send(json.dumps({
                            'type': 'tell',
                            'user': data['user']['name'],
                            'name': 'calc',
                            'text': f'&asomething broke: {e}',
                            'mode': 'format'
                        }))
                        print('Done')
            elif 'error' in data.keys():
                print('uh oh', data['error'])


asyncio.run(main())
