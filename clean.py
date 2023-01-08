from spymap.based import player_init_tables, fixup_updates, with_player_cursor, with_player_connection


def main():
    with_player_cursor(player_init_tables)()
    with_player_cursor(fixup_updates)()


if __name__ == '__main__':
    main()
