import sys

from spymap.based import player_init_tables, with_player_cursor, player_report


def main():
    with_player_cursor(player_init_tables)()
    player_report(sys.argv[1])


if __name__ == '__main__':
    main()
