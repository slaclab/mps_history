import socket, sys, argparse, datetime, errno
from ctypes import *

from mps_database.mps_config import MPSConfig, models
from mps_history.tools import HistorySession, logger


class Message(Structure):
    """
    Class responsible for defining messages coming from the Central Node IOC

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

class HistoryServer:
    """
    Most of this class has been taken from the depreciated EicHistory.py server. 

    Establishes a socket responsible for receiving connections/data from the central node, 
    and sending them off for processing. 
    """
    def __init__(self, host, port, dev):
        self.host = host
        self.port = port
        self.dev = dev
        self.sock = None
        self.logger = logger.Logger(stdout=True, dev=dev)

        self.history_db = HistorySession.HistorySession(dev=dev)
              # create dgram udp socket
        
        print("Host in server: ", self.host)

        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.bind((self.host, self.port))
        
        except socket.error:
            self.logger.log("SOCKET ERROR: Failed to create socket")
            self.logger.log("Exiting -----")
            sys.exit()
        

    def listen_socket(self):
        """
        Endless function that waits for data to be sent over the socket
        """
        while True:
            self.receive_update()

    def receive_update(self):
        """
        Receives data from the socket, puts it into a message object, and sends it to the decoder
        """
        message=Message(0, 0, 0, 0, 0)
        
        data, ipAddr = self.sock.recvfrom(sizeof(Message))
        if data:
            print("Received\n", data)
            message = Message.from_buffer_copy(data)
            print("Message\n", message.type, message.id, message.old_value, message.new_value, message.aux)
            self.decode_message(message)
    
    def decode_message(self, message):
        """
        Determines the type of the message, and sends it to the proper function for processing/including to the db
        """
        if (message.type == 1): # FaultStateType 
            self.history_db.add_fault(message)
        elif (message.type == 2): # BypassStateType
            self.history_db.add_bypass(message)
        elif (message.type == 4): # MitigationType
            self.history_db.add_mitigation(message)
        elif (message.type == 5): # DeviceInput (DigitalChannel)
            self.history_db.add_input(message)
        elif (message.type == 6): # AnalogDevice
            self.history_db.add_analog(message)
        else:
            self.logger.log("DATA ERROR: Bad Message Type", message.to_string())
