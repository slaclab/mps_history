import argparse
from mps_history.tools import HistoryBroker, HistoryListener, HistorySender
from multiprocessing import Process
from multiprocessing import Queue
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

    """ Begin Multi-Processes """
    central_node_data_queue = Queue() # Holds the data to be processed by workers
    processed_data_queue = Queue() # Holds the data to be sent to History DB
    # start the listener
    listener_proc = Process(name="listener", target=listener, args=(central_node_data_queue, args,))
    listener_proc.start()
    # start the sender
    # sender_proc = Process(name="sender", target=sender, args=(processed_data_queue, dev,))
    #sender_proc.start()
    # start the workers
    num_workers = 1 # adjust the number if needed, but keep it < cpu cores available (16 cores is current hardware)
    for i in range(num_workers):
        worker_name = "worker_" + str(i)
        worker_proc = Process(name=worker_name, target=worker, args=(central_node_data_queue, processed_data_queue, dev,))
        worker_proc.daemon = True # Ensures workers do not affect listener process
        worker_proc.start()

    # main process - wait for listener process to finish
    # it doesnt actually finish, so this .join() ensures this server runs forever unless terminated
    listener_proc.join()
    # sender_proc.join()
    return


def listener(central_node_data_queue, args):
    """
    A process whose job is to constantly listen and receive data from central nodes
    through the UDP socket and write data to a queue
    
    Params:
        central_node_data_queue: Holds the data to be processed from the workers
        args: Contains host, port, and dev data
    """ 

    print("args:", end="")
    print(args)
    hist = HistoryListener.HistoryListener(args.host, args.port, args.dev, central_node_data_queue)
    hist.listen_socket()
    return

def sender(processed_data_queue, dev):
    """
    A process whose job is to read processed data from workers, and send it to kafka -> History DB
    
    Params:
        processed_data_queue: Holds the data to be sent to History DB
        dev: Boolean to specify dev mode
    """ 

    hist = HistorySender.HistorySender(processed_data_queue, dev)
    hist.process_queue()
    return

def worker(central_node_data_queue, processed_data_queue, dev):
    """
    A process whose job is to take data from the central_node_data_queue, process the data,
    then send it over to the kubernetes infrastructure to write to History DB. 
    
    Params:
        central_node_data_queue: Holds the data to be processed from the workers
        dev: Boolean to specify dev mode
    """ 
    print("Worker process started")
    hist = HistoryBroker.HistoryBroker(central_node_data_queue, processed_data_queue, dev)
    hist.process_queue()

    return

if __name__ == "__main__":
    main()