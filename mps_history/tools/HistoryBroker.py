import config, socket, sys, argparse, datetime, errno, traceback
from ctypes import *

from mps_database.mps_config import MPSConfig, models
from mps_history.models import fault_history
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

class HistoryBroker:
    """
    Most of this class has been taken from the depreciated EicHistory.py server. 

    Establishes a socket responsible for receiving connections/data from the central node, 
    and sending them off for processing. 
    """
    def __init__(self, host, port, dev):
        self.host = host
        self.port = port
        self.sub_port = "123456"
        self.dev = dev
        self.sock = None
        self.logger = logger.Logger(stdout=True, dev=dev)

        if self.dev:
            self.default_dbs = config.db_info["lcls-dev3"]
        else:
            self.default_dbs = config.db_info["test"]
        print("Dev is:", dev)
        self.connect_conf_db()

        #Listeners for the various message types
        history_session = HistorySession.HistorySession(dev=dev)

        self.fault_listeners = [history_session]
        self.analog_listeners = [history_session]
        self.input_listeners = [history_session]
        self.bypass_listeners = [history_session]
              # create dgram udp socket
        
        print("Host in server: ", self.host)

        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.bind((self.host, self.port))
        
        except socket.error:
            self.logger.log("SOCKET ERROR: Failed to create socket")
            self.logger.log("Exiting -----")
            sys.exit()

    def create_subscriber_socket(self):
        try:
            self.sub_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sub_sock.bind((self.host, self.sub_port))
        
        except socket.error:
            self.logger.log("SOCKET ERROR: Failed to create socket")
            self.logger.log("Exiting -----")
            sys.exit()
        return

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
    
    def connect_conf_db(self):
        """
        Creates a interactable connection to the configuration database
        """
        #TODO: add cli args later
        db_file = self.default_dbs["file_names"]["config"]
        try:
            self.conf_conn = MPSConfig(db_name="config", db_file=db_file, file_path=self.default_dbs["file_paths"]["config"])
        except:
            self.logger.log("DB ERROR: Unable to Connect to Database ", str(db_file))
        return    

    def decode_message(self, message):
        """
        Determines the type of the message, and sends it to the proper function for processing/including to the db
        """
        if (message.type == 1): # FaultStateType 
            data = self.process_fault(message)
            listeners = self.fault_listeners
        elif (message.type == 2): # BypassStateType
            data = self.process_bypass(message)
            listeners = self.bypass_listeners
        elif (message.type == 5): # DeviceInput (DigitalChannel)
            data = self.process_input(message)
            listeners = self.input_listeners
        elif (message.type == 6): # AnalogDevice
            data = self.process_analog(message)
            listeners = self.analog_listeners
        else:
            self.logger.log("DATA ERROR: Bad Message Type", message.to_string())
        # Send the data to the relevant listeners
        self.send_data(data, listeners)
        return

    def send_data(self, data, listeners):
        for listener in listeners:
            listener.receive_data(data)
        return

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
                fault_info = {"type":"fault", "active":False, "fid":message.id, "fdesc":("FAULT CLEARED - " + fault.description)}
            else:
                fault_info = {"type":"fault", "active":True, "fid":fault.id, "fdesc":fault.description}

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
            f_info = {"old_state":old_state, "new_state":new_state, "beam_class":beam_class, "beam_destination":beam_dest}
            fault_info.update(f_info)
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
        ana_info = {"type":"analog", "channel":channel.name, "device":device.name, "old_state":old_value, "new_state":new_value}
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
        bypass_info = {"type":"bypass", "channel":channel.name, "new_state":new_name, "old_state":old_name, "integrator":message.aux}
        return bypass_info

    def process_input(self, message):
        """
        Adds a device input into the history database
        Adds in digital channel name, the digital device name, and the names of the new and old digital channels based on their 0/1 values 
        
        Params:
            message: [type(of message), id, oldvalue, newvalue, aux(allowed_class)]        
        """
        try:
            device_input = self.conf_conn.session.query(models.DeviceInput).filter(models.DeviceInput.id==message.id).first()
            channel = self.conf_conn.session.query(models.DigitalChannel).filter(models.DigitalChannel.id==device_input.channel_id).first()   
            digital_device = self.conf_conn.session.query(models.DigitalDevice).filter(models.DigitalDevice.id==device_input.digital_device_id).first()
            
            device = self.conf_conn.session.query(models.Device).filter(models.Device.id==digital_device.id).first()

            if None in [device_input, device, channel]:
                print([device_input, device, channel])
                raise
        except:
            self.logger.log("SESSION ERROR: Add Device Input ", message.to_string())
            print(traceback.format_exc())
            return
        old_name = channel.z_name
        new_name = channel.z_name
        if (message.old_value > 0):
            old_name = channel.o_name
        if (message.new_value > 0):
            new_name = channel.o_name

        input_info = {"type":"input", "new_state":new_name, "old_state":old_name, "channel":channel.name, "device":digital_device.name}
        return input_info

    def determine_device_from_fault(self, fstate_id):
        """
        Returns the device state based off of the fault state id
        """
        if fstate_id == 0:
            return "None"
        fault_state = self.conf_conn.session.query(models.FaultState).filter(models.FaultState.id==fstate_id).first()
        device_state = self.conf_conn.session.query(models.DeviceState).filter(models.DeviceState.id==fault_state.device_state_id).first()
        return device_state.name
