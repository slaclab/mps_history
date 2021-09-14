import argparse
from tools import HistoryServer

def main():
    parser = argparse.ArgumentParser(description='Receive MPS history messages')
    parser.add_argument('--port', metavar='port', type=int, nargs='?', help='server port (default=3356)')
    parser.add_argument('--database', metavar='db', nargs=1, default='mps_gun_history.db', 
                        help='database file name (e.g. mps_gun_history.db)')
    args = parser.parse_args()

    #host = socket.gethostname()
    host = '127.0.0.1'

    #Set default port number
    if args.port:
        port = args.port
    else:    
        port=1234

    hist = HistoryServer.HistoryServer(host, port)
    hist.listen_socket()    
    return



if __name__ == "__main__":
    main()