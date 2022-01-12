import socket, sys, argparse, datetime, errno, traceback
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

        #Listeners for the various message types
        self.fault_listeners = []
        self.mitigation_listeners = []
        self.input_listeners = []
        self.bypass_listeners = []

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
        
    def subscribe(self, msg_type, connector):
        if (msg_type == 1): # FaultStateType 
            self.fault_listeners.append[connector]
        elif (msg_type == 2): # BypassStateType
            self.bypass_listeners.append[connector]
        elif (msg_type == 5): # DeviceInput (DigitalChannel)
            self.input_listeners.append[connector]
        elif (msg_type == 6): # AnalogDevice
            self.analog_listeners.append[connector]
        else:        
            print("ERROR: message type ", msg_type, " not valid for subscriptions")
        return    

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


    def process_fault(self, message):
        """
        Adds a single fault to the fault_history table in the history database
        Adds in the fault description, "inactive"/"active" for the state changes, and the device state name

        Params:
            message: [type(of message), id, old_value, new_value, aux(allowed_class)]
        """
        try:      
            fault = self.conf_conn.session.query(models.Fault).filter(models.Fault.id==message.id).first()
            # Determine the fault id and description
            if message.new_value == 0:
                fault_info = {"fid":message.id, "fdesc":("FAULT CLEARED - " + fault.description)}
                #TODO: make previous entry inactive
                self.set_faults_inactive(message.id)
                active = False
            else:
                fault_info = {"fid":fault.id, "fdesc":fault.description}
                active = True

            #Determine the new and old fault state names
            old_state = self.determine_device_from_fault(message.old_value)
            new_state = self.determine_device_from_fault(message.new_value)

            # Using the allowed class(aux) determine the beam class and destination
            if message.aux > 0:
                allowed_class = self.conf_conn.session.query(models.AllowedClass).filter(models.AllowedClass.id==message.aux).first()
                beam_dest = self.conf_conn.session.query(models.BeamDestination).filter(models.BeamDestination.id==allowed_class.beam_destination_id).first().name
                beam_class = self.conf_conn.session.query(models.BeamClass).filter(models.BeamClass.id==allowed_class.beam_class_id).first().name
            else:
                allowed_class = "GOOD"
                beam_dest = "ALL"
                beam_class = "FULL"
            if None in [beam_dest, beam_class, old_state, new_state]:
                print([beam_dest, beam_class, fault, old_state, new_state])
                raise
            fault_info["old_state"]=old_state, fault_info["new_state"]=new_state, fault_info["beam_class"]=beam_class, fault_info["beam_destination"]=beam_dest, fault_info["active"]=active
        except Exception as e:
            self.logger.log("SESSION ERROR: Add Fault ", message.to_string())
            print(traceback.format_exc())
            return
        return fault_info


    def process_analog(self, message):
        """
        Adds an analog device update into the history database
        Adds in the device channel name, and hex values of the new and old state changes
        
        Params:
            message: [type(of message), id, old_value, new_value, aux]
        """
        try:
            analog_device = self.conf_conn.session.query(models.AnalogDevice).filter(models.AnalogDevice.id==message.id).first()
            channel = self.conf_conn.session.query(models.AnalogChannel).filter(models.AnalogChannel.id==analog_device.channel_id).first()
            device = self.conf_conn.session.query(models.Device).filter(models.Device.id==analog_device.id).first()

            if None in [device, channel]:
                print([device, channel])
                raise            
            # This will fail if the values are strings, not ints. TODO: see how it sends info
            old_value, new_value = hex(message.old_value), hex(message.new_value)
        except:
            self.logger.log("SESSION ERROR: Add Analog ", message.to_string())
            print(traceback.format_exc())
            return
        ana_info = {"channel":channel.name, "device":device.name, "old_state":old_value, "new_state":new_value}
        return ana_info

def process_bypass(self, message):
        """
        Adds an analog or digital device bypass into the history database.
        Adds in the device channel name, "active"/"expired" for the state change, and if analog, the integrator auxillary data
        
        Params:
            message: [type(of message), id, oldvalue, newvalue, aux(digital vs analog)]        
        """
        # Determine active/expiration status
        old_name, new_name = "active", "active"
        if message.old_value == 0: old_name = "expired"
        if message.new_value == 0: new_name = "expired"
        try:
            # Device is digital
            if message.aux > 31:
                device_input = self.conf_conn.session.query(models.DeviceInput).filter(models.DeviceInput.id==message.id).first()
                channel = self.conf_conn.session.query(models.DigitalChannel).filter(models.DigitalChannel.id==device_input.channel_id).first()
            # Device is analog
            else:
                analog_device = self.conf_conn.session.query(models.AnalogDevice).filter(models.AnalogDevice.id==message.id).first()
                channel = self.conf_conn.session.query(models.AnalogChannel).filter(models.AnalogChannel.id==analog_device.channel_id).first()
            if not channel:
                raise
        except:
            self.logger.log("SESSION ERROR: Add Bypass ", message.to_string())
            print(traceback.format_exc())
            return
        bypass_info = {"channel":channel.name, "new_state":new_name, "old_state":old_name, "integrator":message.aux}
        return bypass_info
