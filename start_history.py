import argparse
from mps_history.tools import HistoryBroker

def main():
    parser = argparse.ArgumentParser(description='Receive MPS history messages')
    parser.add_argument('--port', metavar='port', type=int, nargs='?', help='server port (default=3356)')
    parser.add_argument('--host', metavar='host', help='Server Host (default=localhost)')
    parser.add_argument('--database', metavar='db', nargs=1, default='mps_gun_history.db', 
                        help='database file name (e.g. mps_gun_history.db)')
    parser.add_argument('--dev', action='store_true', help='flag for lcls-dev3 db paths')
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

    if args.dev:
        dev = True
    else:
        dev = False

    hist = HistoryBroker.HistoryBroker(host, port, dev)
    hist.listen_socket()    
    return



if __name__ == "__main__":
    main()