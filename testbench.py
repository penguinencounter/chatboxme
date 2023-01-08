import random
from typing import List

from spymap import integration
from spymap.based import player_init_tables, fixup_updates, with_player_cursor, with_player_connection, apply_update, \
    dbhealth_report, player_report
from spymap.structures import DynmapPlayerListing, DynmapPlayer


def main():
    with_player_cursor(player_init_tables)()
    with_player_cursor(fixup_updates)()
    config = integration.get_configuration()
    upddat = list(integration.get_updates(config).values())[0]
    upddat = DynmapPlayerListing(upddat)
    with_player_cursor(apply_update)(conf=config, update_data=upddat)
    players: List[DynmapPlayer] = list(upddat.players)
    players.sort(key=lambda x: x.account)
    dbhealth_report()
    for player in players:
        player_report(player.account)


if __name__ == '__main__':
    main()
