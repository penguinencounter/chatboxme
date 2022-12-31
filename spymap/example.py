from spymap import integration

if __name__ == '__main__':
    conf = integration.get_configuration()
    while True:
        updates = integration.get_updates(conf)
