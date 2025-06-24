import argparse
from mps_processor import HistoryBroker
def main():
    parser = argparse.ArgumentParser(description='Receive MPS history messages')
    parser.add_argument('--port', metavar='port', type=int, nargs='?', help='server port (default=3356)')
    parser.add_argument('--host', metavar='host', help='Server Host (default=localhost)')
    parser.add_argument('--database', metavar='db', nargs=1, default='mps_gun_history.db', 
                        help='database file name (e.g. mps_gun_history.db)') # Currently: database argument isn't used
    parser.add_argument('--dev', action='store_true', help='flag for dev-rhel7 db paths')
    args = parser.parse_args()

    #host = socket.gethostname()
    if args.host:
        host = args.host
    else:
        host = '127.0.0.1'

    #Set default port number
    if args.port:
        port = args.port
    else:    
        port=3356

    # Set dev mode
    if args.dev:
        dev = True
    else:
        dev = False

    main_processor = HistoryBroker.HistoryBroker()
    main_processor.process_loop()

    return

if __name__ == "__main__":
    main()