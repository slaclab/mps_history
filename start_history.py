import argparse
from mps_history.tools import HistoryBroker
from mps_history.tools import HistoryListener
from multiprocessing import Process
from multiprocessing import Queue
def main():
    parser = argparse.ArgumentParser(description='Receive MPS history messages')
    parser.add_argument('--port', metavar='port', type=int, nargs='?', help='server port (default=3356)')
    parser.add_argument('--host', metavar='host', help='Server Host (default=localhost)')
    parser.add_argument('--database', metavar='db', nargs=1, default='mps_gun_history.db', 
                        help='database file name (e.g. mps_gun_history.db)')
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

    # Currently: database argument isn't used

    """ Begin Multi-Processes """
    central_node_data_queue = Queue()
    # start the workers
    num_workers = 5
    for i in range(num_workers):
        worker_proc = Process(target=worker, args=(i, central_node_data_queue,))
        worker_proc.start()

    # start the listener
    listener_proc = Process(target=listener, args=(central_node_data_queue, args))
    listener_proc.start()

    # wait for listener process to finish
    listener_proc.join()


    """ TEMP """
    print("args:")
    print(args)
    hist = HistoryBroker.HistoryBroker(host, port, dev)
    hist.listen_socket()    
    return
    """ TEMP """

def listener(central_node_data_queue, args):
    """
    A process whose only job is to constantly listen and receive data from central nodes
    through the UDP socket
    
    Params:
        central_node_data_queue: Holds the data to be processed from the workers
    """ 

    print("args:", end="")
    print(args)
    hist = HistoryListener.HistoryListener(args.host, args.port, args.dev, central_node_data_queue)
    hist.listen_socket()
    return

def worker(central_node_data_queue):
    # u

    return

if __name__ == "__main__":
    main()