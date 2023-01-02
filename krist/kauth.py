# kauth: authenticate with your Krist wallet. Why not.
import re
from typing import *

import requests

from krist.k import send_to

NAMES_TRUSTED = {
    "switchcraft": "kqxhx5yn9v"
}

with open("krist_key.txt") as f:
    PRIVATE = f.read().strip()

last_read = 0


def get_addr():
    resp = requests.post(
        "https://krist.dev/v2",
        data={
            "privatekey": PRIVATE
        }
    )
    return resp.json()['address']


ADDR = get_addr()


def parse_commonmeta(meta: str) -> Tuple[Optional[str], Optional[str], Dict[str, str]]:
    # key1=value1;key2=value2;key3=value3
    # name.kst;key1=value1;key2=value2;key3=value3
    # metaname@name.kst;key1=value1;key2=value2;key3=value3
    if meta is None:
        return None, None, {}
    NAME_SUPPLY_RE = r'^(?:([a-z0-9-_]{1,32})@)?([a-z0-9]{1,64})\.kst'
    m = re.match(NAME_SUPPLY_RE, meta)
    name = None
    metaname = None
    if m is not None:
        name = m.group(2)
        metaname = m.group(1)

        has_data = re.match(r'^(?:[a-z0-9-_]{1,32}@)?[a-z0-9]{1,64}\.kst;', meta)
        if has_data is None:
            return name, metaname, {}
        else:
            meta = meta[has_data.end():]

    data = {}
    for kvp in meta.split(';'):
        if kvp == '':
            continue
        key, value = kvp.split('=')
        data[key] = value

    return name, metaname, data


class SecurityError(Exception):
    pass


def get_refund_address(sent_from: str, metadata: str):
    """
    Validate a transaction and return the address to refund to.
    """
    _, _, data = parse_commonmeta(metadata)
    target = sent_from
    if 'return' in data:
        sus = data['return']
        name = re.match(r'(?:([a-z0-9-_]{1,32})@)?([a-z0-9]{1,64})\.kst', sus)
        if name is not None:
            metaname = name.group(1)
            name = name.group(2)

            # Prevent attacks where a user can send return=<other user>@switchcraft.kst or something to gain access
            if name not in NAMES_TRUSTED:
                return False, target, f"Security error: The authentication server doesn't trust the name {name}.kst; try directly from an address?"
            if NAMES_TRUSTED[name] != sent_from:
                return False, target, f"Security error: The authentication server's records for {name}.kst don't match yours. Try again with a different address."

            target = f'{metaname}@{name}.kst'
    return True, target, "kauth: successful"


KAUTH_META_TOK = "kauth"
KAUTH_OUT_META_TOK = "kauth_for"


last_done = 0


def process(txn: dict):
    ok, refto, message = get_refund_address(txn['from'], txn['metadata'] if 'metadata' in txn else None)
    print(f'  > send {txn["value"]} kst to {refto}')
    send_to(refto, txn['value'], "message=" + message + f";{KAUTH_OUT_META_TOK}=" + str(txn['id']))


def prepare_done():
    global last_done
    resp = requests.get(f'https://krist.dev/lookup/transactions/{ADDR}?order=DESC&limit=500')
    txns = resp.json()['transactions']
    incoming: Set[int] = set()
    outgoing: Set[int] = set()
    for txn in txns:
        if txn['from'] == ADDR:
            is_in = False
            is_out = True
        elif txn['to'] == ADDR:
            is_in = True
            is_out = False
        else:
            continue
        _, _, meta = parse_commonmeta(txn['metadata'] if 'metadata' in txn else None)
        if KAUTH_META_TOK in meta and is_in:
            incoming.add(txn['id'])
        if KAUTH_OUT_META_TOK in meta and is_out:
            try:
                outgoing.add(int(meta[KAUTH_OUT_META_TOK]))
            except ValueError:
                pass

    already_done = outgoing & incoming
    highest_done = max(already_done) if len(already_done) > 0 else 0
    last_done = max(last_done, highest_done)
    print(f'  > ffwd: #{last_done}')


prepare_done()


def read_incoming():
    global last_done
    resp = requests.get(f'https://krist.dev/lookup/transactions/{ADDR}?order=DESC&limit=500')
    txns = resp.json()['transactions']
    txn_cache = {}
    incoming: Set[int] = set()
    outgoing: Set[int] = set()
    for txn in txns:
        if txn['id'] < last_done:
            continue
        if txn['from'] == ADDR:
            direction = 'out'
            is_in = False
            is_out = True
        elif txn['to'] == ADDR:
            direction = 'in'
            is_in = True
            is_out = False
        else:
            raise Exception("Transaction parser: neither from nor to is this address, is the request correct?")
        txn_cache[txn['id']] = txn
        _, _, meta = parse_commonmeta(txn['metadata'] if 'metadata' in txn else None)
        if KAUTH_META_TOK in meta and is_in:
            incoming.add(txn['id'])
            print(f'  > kauth {direction.ljust(3)} #{txn["id"]} {txn["value"]} kst from {txn["from"]}')
        if KAUTH_OUT_META_TOK in meta and is_out:
            try:
                outgoing.add(int(meta[KAUTH_OUT_META_TOK]))
                print(f'  > kauth {direction.ljust(3)} #{txn["id"]} (ref #{meta[KAUTH_OUT_META_TOK]}) {txn["value"]} kst to {txn["to"]}')
            except ValueError:
                print(f"  > {txn['id']} has invalid {KAUTH_OUT_META_TOK} metadata")

    need_to_process = incoming - outgoing
    print(f'  > To process (refund):')
    for txn_id in need_to_process:
        txn = txn_cache[txn_id]
        print(f'  >   {txn_id}')
        process(txn)

    already_done = outgoing & incoming
    highest_done = max(already_done) if len(already_done) > 0 else 0
    last_done = max(last_done, highest_done)
