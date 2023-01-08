import random
import time
from datetime import datetime
from sqlite3 import connect, Connection, Cursor
from typing import Optional

import requests

from spymap import integration
from spymap.structures import DynmapPlayerListing, DynmapConfiguration, DynmapPlayer


def player_connector() -> Connection:
    return connect('p.db')


CREATE = {
    "LatestPosition": "CREATE TABLE IF NOT EXISTS LatestPosition (uuid TEXT PRIMARY KEY, username TEXT, timestamp TEXT DEFAULT CURRENT_TIMESTAMP, x REAL, y REAL, z REAL, world TEXT)",
    "Updates": "CREATE TABLE IF NOT EXISTS Updates (ord INTEGER PRIMARY KEY, uuid TEXT, username TEXT, timestamp TEXT DEFAULT CURRENT_TIMESTAMP, x REAL, y REAL, z REAL, world TEXT)",
    "NameUUID": "CREATE TABLE IF NOT EXISTS NameUUID (uuid TEXT PRIMARY KEY, username TEXT, last_refresh TEXT DEFAULT CURRENT_TIMESTAMP)"
}

ADDITIONAL_CREATE = {
    "fixup": CREATE["Updates"].replace("Updates", "fixup")
}

OUTDATED_NAME_TIME = 60 * 60 * 24
TSTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"


def player_init_tables(cur: Cursor):
    for table, sql in CREATE.items():
        cur.execute(sql)


def fixup_updates(cur: Cursor):
    start = time.time()
    print("Reorganizing Updates table...")
    cur.execute("DROP TABLE IF EXISTS fixup")
    cur.execute(ADDITIONAL_CREATE["fixup"])
    counter = 1
    for row in cur.execute("SELECT uuid, username, x, y, z, world FROM Updates ORDER BY ord ASC").fetchall():
        if counter % 100 == 0:
            print(f"\rFixup: Processed {counter} rows...".ljust(50), end='', flush=True)
        cur.execute("INSERT INTO fixup (ord, uuid, username, x, y, z, world) VALUES (?, ?, ?, ?, ?, ?, ?)", (counter, ) + row)
        counter += 1
    print(f"\rFixup: Processed {counter} rows.".ljust(50), flush=True)
    cur.execute("DROP TABLE IF EXISTS Updates")
    cur.execute("ALTER TABLE fixup RENAME TO Updates")
    cur.execute("DROP TABLE IF EXISTS fixup")
    stop = time.time()
    print(f"Fixup took {stop - start:.2f} seconds")


def get_uuid(cur: Cursor, username: str) -> Optional[str]:
    uuid = cur.execute("SELECT uuid, last_refresh FROM NameUUID WHERE username LIKE ?", (username,)).fetchone()
    if uuid is not None:
        exp = datetime.strptime(uuid[1], TSTAMP_FORMAT)
        if (datetime.now() - exp).total_seconds() < OUTDATED_NAME_TIME:
            return uuid[0]
    resp = requests.get(f"https://api.mojang.com/users/profiles/minecraft/{username}")
    if resp.status_code == 200:
        uuid = resp.json()['id']
        cur.execute("DELETE FROM NameUUID WHERE username LIKE ?", (username,))
        cur.execute("INSERT OR REPLACE INTO NameUUID (uuid, username) VALUES (?, ?)", (uuid, username))
    elif resp.status_code == 404:
        if uuid is not None:
            return uuid[0]
        return None
    else:
        return None
    return uuid


last_fix = time.time()


def apply_update(cur: Cursor, conf: DynmapConfiguration, update_data: DynmapPlayerListing):
    global last_fix
    # prepare to update
    next_ord = cur.execute("SELECT MAX(ord) FROM Updates").fetchone()[0]
    next_ord = next_ord if next_ord is not None else 0
    for player in update_data.players:
        player: DynmapPlayer
        if player.account is None:
            continue
        if player.world not in map(lambda x: x.internal, conf.worlds):
            continue  # not a world where positional data is provided
        uuid = get_uuid(cur, player.account)
        if uuid is None:
            continue
        last_update = cur.execute(
            "SELECT x, y, z, world FROM LatestPosition WHERE uuid=?", (uuid,)
        ).fetchone()
        cur.execute(
            "INSERT OR REPLACE INTO LatestPosition (uuid, username, x, y, z, world) VALUES (?, ?, ?, ?, ?, ?)",
            (uuid, player.account, player.x, player.y, player.z, player.world)
        )
        # get the last update
        if last_update is None or last_update[0] != player.x or last_update[1] != player.y or last_update[2] != player.z or last_update[3] != player.world:
            next_ord += 1
            cur.execute(
                "INSERT INTO Updates (ord, uuid, username, x, y, z, world) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (next_ord, uuid, player.account, player.x, player.y, player.z, player.world)
            )
    last_fix = time.time()


def auto_fetch(conf: DynmapConfiguration):
    start = time.time()
    upd = list(integration.get_updates(conf).values())[0]
    pud = DynmapPlayerListing(upd)

    with player_connector() as conn:
        cur = conn.cursor()
        player_init_tables(cur)
        apply_update(cur, conf, pud)
        conn.commit()
        cur.close()
    stop = time.time()
    print(f"Tracking update took {stop - start:.2f} seconds")


EASTER_EGG = {
    'switchcraft3': lambda: random.choice(['TODO: get lemmmy to provide easter egg text']),
}


def pack_cursor(fn):
    def wrapper(*args, **kwargs):
        with player_connector() as conn:
            cur = conn.cursor()
            ret = fn(*args, cur=cur, **kwargs)
            conn.commit()
            cur.close()
        return ret
    return wrapper


def player_report(username: str):
    start = time.time()
    output = '&8' + EASTER_EGG.get(username.lower(), lambda: f"-")() + '&f\n'
    with player_connector() as conn:
        cur = conn.cursor()

        uuid = get_uuid(cur, username)

        latest = cur.execute("SELECT x, y, z, world, timestamp FROM LatestPosition WHERE uuid=?", (uuid,)).fetchone()
        if latest is None or uuid is None:
            output += f"&cno data for {username}\n"
        else:
            timestamp = datetime.strptime(latest[4], TSTAMP_FORMAT)

            # format days/hours/min/sec
            timestamp = (datetime.utcnow() - timestamp).total_seconds()

            time_color_1 = "&7" if timestamp < 10 else "&e" if timestamp < 30 else "&c"
            time_color_2 = "&8" if timestamp < 10 else "&6" if timestamp < 30 else "&4"
            days = int(timestamp // (60 * 60 * 24))
            timestamp %= 60 * 60 * 24
            hours = int(timestamp // (60 * 60))
            timestamp %= 60 * 60
            minutes = int(timestamp // 60)
            timestamp %= 60
            seconds = int(timestamp)

            dhms = f"{days}d " if days > 0 else ""
            dhms += f"{hours}h " if hours > 0 or len(dhms) > 0 else ""
            dhms += f"{minutes}m " if minutes > 0 or len(dhms) > 0 else ""
            dhms += f"{seconds}s"
            output += f"&a{username} {time_color_2}last seen {time_color_1}{dhms}{time_color_2} ago\n"
            output += f"&7(&c{latest[0]:.2f}&7, &c{latest[1]:.2f}&7, &c{latest[2]:.2f}&7) in &a{latest[3]}\n"
        cur.close()
    output += f"&8last update &7{time.time()-last_fix:.1f}s &8ago\n"
    stop = time.time()
    print(f"Tracking report took {stop - start:.2f} seconds")
    return output


def dbhealth_report() -> str:
    output = "&8-&f\n"
    with player_connector() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM LatestPosition")
        output += f"&a{cur.fetchone()[0]} &7players tracked\n"
        cur.execute("SELECT COUNT(*) FROM Updates")
        rows = cur.fetchone()[0]
        output += f"&a{rows} &7tracking updates ("
        cur.execute("SELECT MAX(ord) FROM Updates")
        last_id = cur.fetchone()[0]
        output += f"&a{last_id} &7last id)\n"
        eff = rows / last_id if last_id > 0 else 0
        output += f"    &a{eff:03.2%} &7ID efficiency\n"
        cur.execute("SELECT COUNT(*) FROM NameUUID")
        output += f"&a{cur.fetchone()[0]} &7names tracked\n"
        cur.close()
    return output


if __name__ == '__main__':
    print('loading configuration')
    config = integration.get_configuration()
    print('downloading update data...')
    updates = list(integration.get_updates(config).values())[0]
    player_update_data = DynmapPlayerListing(updates)

    print('starting database...')
    c = player_connector()
    cu = c.cursor()
    player_init_tables(cu)
    c.commit()

    print('applying update data...')
    apply_update(cu, config, player_update_data)
    c.commit()

    print('done')
    cu.close()
    c.close()
