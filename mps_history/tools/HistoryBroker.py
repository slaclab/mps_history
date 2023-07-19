import config, socket, sys, argparse, datetime, errno, traceback, os
from ctypes import *

""" TEMP """
# Forced config mps_database to point to the new_mpsdb 
import sys
# caution: path[0] is reserved for script path (or '' in REPL)
sys.path.insert(1, '/u/cd/pnispero/mps/mps_database_new')
""" TEMP """

from mps_database.mps_config import MPSConfig, models
#from mps_history.models import fault_history
from mps_history.tools import logger
from sqlalchemy import select

""" TEMP """
import struct

import inspect
print(inspect.getfile(MPSConfig))
print(inspect.getfile(models))

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
""" TEMP """



class HistoryBroker:
    """
    Most of this class has been taken from the depreciated EicHistory.py server. 

    Processes the data from central_nodes by querying the config DB, then sending it to 
    kubernetes infrastructure -> history DB
    """
    def __init__(self, central_node_data_queue, dev):
        self.central_node_data_queue = central_node_data_queue
        self.dev = dev
        self.sock = None
        self.logger = logger.Logger(stdout=True, dev=dev) # TODO - may need to change filenames

        if self.dev:
            self.default_dbs = config.db_info["dev-rhel7"]
        else:
            self.default_dbs = config.db_info["test"]

        self.connect_conf_db()

        # """ TEMP """
        message = Message(2, 378, 0, 0, 17)  

        """ <<<<< Once finished - Place this query block into process_input() <<<<< """
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
            return
        old_name = channel.z_name
        new_name = channel.z_name
        if (message.old_value > 0):
            old_name = channel.o_name
        if (message.new_value > 0):
            new_name = channel.o_name

        input_info = {"type":"input", "new_state":new_name, "old_state":old_name, "channel":channel.name, "device":digital_device.name}
        return input_info
        
        """ >>>>> Once finished - Place this query block into process_input() >>>>> """


        """ TEMP """
        

    def process_queue(self):
        """
        Process any items in the central_node_data_queue
        """
        
        if not self.central_node_data_queue.empty():
            message = self.central_node_data_queue.get()
            print("Worker received message! ", end="")
            print("current queue size: " + str(self.central_node_data_queue.qsize()), end=" ")
            print("Message ", message.type, message.id, message.old_value, message.new_value, message.aux)
           
            self.decode_message(message)

    
    def connect_conf_db(self):
        """
        Creates a interactable connection to the configuration database
        """
        #TODO: add cli args later
        db_file = self.default_dbs["file_paths"]["config"] + "/" + self.default_dbs["file_names"]["config"]
        print(db_file)
        try:
            self.conf_conn = MPSConfig(db_file)
        except Exception as e:
            print(e)
            self.logger.log("DB ERROR: Unable to Connect to Database ", str(db_file))
            exit()
        return    

    def decode_message(self, message):
        """
        Determines the type of the message, and sends it to the proper function for processing/including to the db
        """
        if (message.type == 1): # FaultStateType 
            data = self.process_fault(message)
        elif (message.type == 2): # BypassStateType
            data = self.process_bypass(message)
        elif (message.type == 5): # DeviceInput (DigitalChannel)
            data = self.process_input(message)
        elif (message.type == 6): # AnalogDevice
            data = self.process_analog(message)
        else:
            self.logger.log("DATA ERROR: Bad Message Type", message.to_string())
        print(data)

        # TODO - Send the data to the Kubernetes infrastructure
        # self.send_data(data, listeners)
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
            message: [type(of message), id, old_value, new_value, aux(mitigation_id)]
        Output:
            fault_info: ['type': 'fault', 'active': bool, 'fault_id': int, 'fault_desc': str,
                        'old_state': str, 'new_state': str, 'beam_class': str, 'beam_destination': str]
        """
        try:   
            fault = self.conf_conn.session.query(models.Fault).\
            filter(models.Fault.id==message.id).first()

            # Determine the fault id and description(fault.name)
            if message.new_value == 0:
                fault_info = {"type":"fault", "active":False, "fault_id":message.id, "fault_desc":("FAULT CLEARED - " + fault.name)}
            else:
                fault_info = {"type":"fault", "active":True, "fault_id":fault.id, "fault_desc":fault.name}

            # Determine the new and old fault state names
            old_state = self.get_fault_state_from_fault(message.old_value)
            new_state = self.get_fault_state_from_fault(message.new_value)

            if message.aux > 0:
                # aux value is the id from association_mitigation, which needs to join with mitigation, which needs to join with beam_dest and beam_class
                mitigation_id = self.conf_conn.session.query(models.fault_state.association_table)\
                                .filter(models.fault_state.association_table.c.id==message.aux)\
                                .first().mitigation_id
                beam_dest_id = self.conf_conn.session.query(models.Mitigation)\
                                .filter(models.Mitigation.id==mitigation_id)\
                                .first().beam_destination_id
                beam_class_id = self.conf_conn.session.query(models.Mitigation)\
                                .filter(models.Mitigation.id==mitigation_id)\
                                .first().beam_class_id
                beam_dest = self.conf_conn.session.query(models.BeamDestination)\
                    .filter(models.BeamDestination.id==beam_dest_id)\
                    .first().name
                beam_class = self.conf_conn.session.query(models.BeamClass)\
                    .filter(models.BeamClass.id==beam_class_id)\
                    .first().name
            else:
                beam_dest = "ALL"
                beam_class = "FULL"
            if None in [beam_dest, beam_class, old_state, new_state]:
                print([beam_dest, beam_class, fault, old_state, new_state])
                raise
            f_info = {"old_state":old_state, "new_state":new_state, "beam_class":beam_class, "beam_destination":beam_dest}
            fault_info.update(f_info)
        except:
            self.logger.log("SESSION ERROR: Add Fault ", message.to_string())
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
            return
        ana_info = {"type":"analog", "channel":channel.name, "device":device.name, "old_state":old_value, "new_state":new_value}
        return ana_info

    def process_bypass(self, message):
        """
        Adds an analog or digital device bypass into the history database.
        Adds in the device channel name, "active"/"expired" for the state change, and if analog, the integrator auxillary data
        
        Params:
            message: [type(of message), id, oldvalue, newvalue, aux(digital vs analog)]        
        Output:
            bypass_info: ['type': 'bypass', 'channel': str, 'old_state': str, 'new_state': str, 'integrator': int]
        """
       # Determine active/expiration status
        old_state, new_state = "active", "active"
        if message.old_value == 0: old_state = "expired"
        if message.new_value == 0: new_state = "expired"
        try:
            channel_id = self.conf_conn.session.query(models.FaultInput).\
                        filter(models.FaultInput.id==message.id).first().channel_id
            channel_name = self.conf_conn.session.query(models.Channel).\
                        filter(models.Channel.id==channel_id).first().name
        except:
            self.logger.log("SESSION ERROR: Add Bypass ", message.to_string())
            return
        # channel is the same as bypass_id in this situation
        bypass_info = {"type":"bypass", "channel":channel_name, "old_state":old_state, "new_state":new_state, "integrator":message.aux}
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
            return
        old_name = channel.z_name
        new_name = channel.z_name
        if (message.old_value > 0):
            old_name = channel.o_name
        if (message.new_value > 0):
            new_name = channel.o_name

        input_info = {"type":"input", "new_state":new_name, "old_state":old_name, "channel":channel.name, "device":digital_device.name}
        return input_info

    def get_fault_state_from_fault(self, fstate_id):
        """
        Returns the device state based off of the fault state id
        """
        if fstate_id == 0:
            return "None"
        fault_state = self.conf_conn.session.query(models.FaultState).filter(models.FaultState.id==fstate_id).first()
        return fault_state.name
    
    # TODO - Delete when done testing
    def determine_device_from_fault(self, fstate_id):
        """
        Returns the device state based off of the fault state id
        """
        if fstate_id == 0:
            return "None"
        fault_state = self.conf_conn.session.query(models.FaultState).filter(models.FaultState.id==fstate_id).first()
        device_state = self.conf_conn.session.query(models.DeviceState).filter(models.DeviceState.id==fault_state.device_state_id).first()
        return device_state.name

