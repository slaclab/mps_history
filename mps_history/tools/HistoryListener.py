import socket, sys
from ctypes import *

class Message(Structure):
    """
    Class responsible for defining messages coming from the Central Node IOC
    5 unsigned ints - 20 bytes of data

    type: 1-6 depending on the type of data to be processed
    id: generally corresponds to device id, but changes depending on message type
    old_value, new_value: the data's initial and new values
    aux: auxillary data that may or may not be included, depending on type -  
        Expected data specifics will be specified in the processing functions
    """
    _fields_ = [
        ("type", c_uint),
        ("id", c_uint),
        ("old_value", c_uint),
        ("new_value", c_uint),
        ("aux", c_uint),
        ]
    
    def to_string(self):
        return str(self.type) + " " + str(self.id) + " " + str(self.old_value) + " " + str(self.new_value) + " " + str(self.aux) 

class HistoryListener:
    """
    Most of this class has been taken from the depreciated EicHistory.py server. 

    Establishes a socket responsible for receiving connections/data from the central node, 
    and sending them off for processing. 
    """
    def __init__(self, host, port, dev, central_node_data_queue):
        self.host = host
        self.port = port
        self.dev = dev
        self.central_node_data_queue = central_node_data_queue
        self.sock = None

        """ TEMP """
        self.receive_count = 0
        """ TEMP """
        
        print("Host in server: ", self.host)

        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.bind((self.host, self.port))
        
        except socket.error:
            print("SOCKET ERROR: Failed to create socket")
            print("Exiting -----")
            sys.exit()

    def listen_socket(self):
        """
        Endless function that waits for data to be sent over the socket
        """
        print("Current receive count: " + str(self.receive_count)) # TEMP
        while True:
            self.receive_update()

    def receive_update(self):
        """
        Receives data from the socket, puts it into a message object, and sends it to the central_node_data_queue to be processed
        """
        message=Message(0, 0, 0, 0, 0)
        data, ipAddr = self.sock.recvfrom(sizeof(Message))
        message = Message.from_buffer_copy(data)

        """ TEMP """
        self.receive_count += 1 
        print("Received\n", data) 
        print("Message ", message.type, message.id, message.old_value, message.new_value, message.aux) 
        print(self.receive_count) 
        """ TEMP """

        self.central_node_data_queue.put(message)
        return
        

