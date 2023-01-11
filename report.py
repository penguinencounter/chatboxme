from spymap.based import player_init_tables, with_player_cursor, dbhealth_report


def main():
    with_player_cursor(player_init_tables)()
    dbhealth_report()


if __name__ == '__main__':
    main()
