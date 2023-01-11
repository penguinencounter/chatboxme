import random
from typing import List

from spymap import integration
from spymap.based import player_init_tables, fixup_updates, with_player_cursor, with_player_connection, apply_update, \
    dbhealth_report, player_report
from spymap.structures import DynmapPlayerListing, DynmapPlayer


def main():
    with_player_cursor(player_init_tables)()
    dbhealth_report()


if __name__ == '__main__':
    main()
