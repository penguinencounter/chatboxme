"""
krist interface
https://krist.dev
"""
import re
import time

import requests

TRANSFER_TO = "kpk8qmvoy7"
with open("krist_key.txt") as f:
    PRIVATE = f.read().strip()


def get_addr():
    resp = requests.post(
        "https://krist.dev/v2",
        data={
            "privatekey": PRIVATE
        }
    )
    return resp.json()['address']


ADDR = get_addr()


def send_to(address: str, amount: int, meta: str = '') -> None:
    """
    Send krist to an address.
    """
    resp = requests.post(
        "https://krist.dev/transactions",
        data={
            "privatekey": PRIVATE,
            "to": address,
            "amount": amount,
            "metadata": meta
        },
    )
    return resp.json()['ok']


last_check_in = 0


def initialize():
    global last_check_in
    resp = requests.get("https://krist.dev/lookup/transactions/" + ADDR + "?order=DESC")
    txns = resp.json()['transactions']
    most_recent = max(txns, key=lambda txn: txn['id'])
    last_check_in = most_recent['id']


def check_contents():
    """
    Check the contents of the krist wallet.
    Send all contents to the transfer address.
    """
    global last_check_in
    resp = requests.get("https://krist.dev/lookup/transactions/" + ADDR + "?order=DESC")
    incoming = []
    max_id = last_check_in
    data = resp.json()
    for transaction in data['transactions']:
        if transaction['id'] > last_check_in:
            if transaction['to'] == ADDR:
                incoming.append(transaction)
        max_id = max(max_id, transaction['id'])
    last_check_in = max_id
    print(f'{len(incoming)} incoming transactions')
    refunded = 0
    kept = 0
    for transaction in incoming:
        return_addr = transaction['from']
        if transaction['metadata'] is not None:
            if "donate=true" in transaction['metadata']:
                kept += 1
                continue
            m = re.search('return=(.+?);', transaction['metadata'])
            if m is not None:
                print(f'  > refund target changed to {m.group(1)}')
                return_addr = m.group(1)
        refunded += 1
        print(f'  > send {transaction["value"]} kst to {return_addr}')
        send_to(return_addr, transaction['value'])
    print(f'{refunded} refunded, {kept} kept')

    resp = requests.get("https://krist.dev/addresses/" + ADDR)
    data = resp.json()['address']
    if data['balance'] > 0:
        send_to(TRANSFER_TO, data['balance'])
        print(f"Sent {data['balance']} krist to {TRANSFER_TO}.")
