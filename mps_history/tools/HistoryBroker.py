import config, socket, sys, argparse, datetime, errno, traceback, os
from ctypes import *
from datetime import datetime
from time import time

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
    Class responsible for defining messages coming from the Central Node IOCchart
    5 unsigned ints - 20 bytes of data

    type: 1-6 depending on the type of data to be processed
    id: the fault.id - This may be useless to send, as the old/new_value can grab the fault.id as it is a FK in fault_state table, instead use it to confirm it is matching with fault_state table.
    old_value, new_value: fault_state.id for old and new
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
    Processes the data from central_nodes by querying the config DB, then sending it to 
    kubernetes infrastructure -> history DB
    """
    def __init__(self, central_node_data_queue, dev):
        self.central_node_data_queue = central_node_data_queue
        self.dev = dev
        self.sock = None
        self.timestamp = 0
        self.logger = logger.Logger(stdout=True, dev=dev) # TODO - may need to change filenames

        if self.dev:
            self.default_dbs = config.db_info["dev-rhel7"]
        else:
            self.default_dbs = config.db_info["test"]

        self.connect_conf_db()

    def process_queue(self):
        """
        Process any items in the central_node_data_queue
        """
        while True: 
            if self.central_node_data_queue.qsize() > 0:
                message = self.central_node_data_queue.get()
                self.timestamp = datetime.now()
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
        elif (message.type == 5): # ChannelType (DigitalChannel or AnalogChannel)
            data = self.process_channel(message)
        else:
            self.logger.log("DATA ERROR: Bad Message Type", message.to_string())
        print(data)

        # Send the data to the Kubernetes infrastructure
        self.send_data(data)
        return

    def send_data(self, data):
        # TODO - Make tcp/ip server so Claudio mps importer middleware can connect to it
        return

    def process_channel(self, message):
        """
        Processes a channel (analog or digital device)
        Params:
            message: [type(of message), id, old_value, new_value, aux]
        Output:
            fault_info: ["type":"channel", "timestamp": str, "old_state": str, "new_state": str, "channel_number": int,
              "channel_name": str,"card_number": int, "crate_loc": str]
        """
        try:
            channel_id = self.conf_conn.session.query(models.FaultInput)\
                        .filter(models.FaultInput.fault_id==message.id)\
                        .first().channel_id
            channel = self.conf_conn.session.query(models.Channel)\
                        .filter(models.Channel.id==channel_id)\
                        .first()
            app_card = self.conf_conn.session.query(models.ApplicationCard)\
                        .filter(models.ApplicationCard.id==channel.card_id)\
                        .first()
            crate_loc = self.conf_conn.session.query(models.Crate)\
                        .filter(models.Crate.id==app_card.crate_id)\
                        .first().location
            if channel.discriminator == 'digital_channel':
                digital_channel = self.conf_conn.session.query(models.DigitalChannel)\
                        .filter(models.DigitalChannel.id==channel_id)\
                        .first()
                old_state = digital_channel.z_name # z name is zero name, and o_name is one name
                new_state = digital_channel.z_name
                if (message.old_value > 0):
                    old_state = digital_channel.o_name
                if (message.new_value > 0):
                    new_state = digital_channel.o_name
            else: # analog - keep 
                    # This will fail if the values are strings, not ints. TODO: see how it sends info
                    old_state, new_state = hex(message.old_value), hex(message.new_value) 
        except:
            self.logger.log("SESSION ERROR: Add Channel ", message.to_string())
            print(traceback.format_exc())
            return
        channel_info = {"type":"channel", "timestamp": str(self.timestamp), "old_state":old_state, "new_state":new_state, "channel_number":channel.number, "channel_name":channel.name,\
                     "card_number":app_card.number, "crate_loc":crate_loc}
        return channel_info


    def process_fault(self, message):
        """
        Processes a single fault
        Params:
            message: [type(of message), id, old_value, new_value, aux(mitigation_id)]
        Output:
            fault_info: ['type': 'fault', 'active': bool, 'fault_id': int, 'fault_desc': str,
                        'old_state': str, 'new_state': str, 'beam_class': str, 'beam_destination': str]
        """
        try:   
            fault = self.conf_conn.session.query(models.Fault)\
                    .filter(models.Fault.id==message.id).first()
            # Determine if active, the fault id and description(fault.name)
            fault_info = {"type":"fault", "timestamp": str(self.timestamp)}
            if message.new_value == 0:
                f_info = {"active":False, "fault_id":message.id, "fault_desc":("FAULT CLEARED - " + fault.name)}
            else:
                f_info = {"active":True, "fault_id":fault.id, "fault_desc":fault.name}
            fault_info.update(f_info)
            # Determine the new and old fault state names
            old_state = self.get_fault_state_from_fault(message.old_value)
            new_state = self.get_fault_state_from_fault(message.new_value)

            # 1) using the fault_state.id from new_state, it has many mitigation_id
            # 2) each mitigation_id has only 1 beam_destination_id and 1 beam_class_id
            mitigation_ids = self.conf_conn.session.query(models.fault_state.association_table.c.mitigation_id)\
                            .filter(models.fault_state.association_table.c.fault_state_id==message.new_value)\
                            .all()
            mitigation_ids = [*set([mitigation_id[0] for mitigation_id in mitigation_ids])] # remove possible duplicates, Change from tuple "(1,)"" to int "1"

            beams = []
            # Determine the beam class and destinations
            for mitigation_id in mitigation_ids:
                beam_ids = self.conf_conn.session.query(models.Mitigation)\
                            .filter(models.Mitigation.id==mitigation_id)\
                            .first()
                beam_dest = self.conf_conn.session.query(models.BeamDestination.name)\
                            .filter(models.BeamDestination.id==beam_ids.beam_destination.id)\
                            .first()[0] # [0] removes tuple structure
                beam_class = self.conf_conn.session.query(models.BeamClass.name)\
                            .filter(models.BeamClass.id==beam_ids.beam_class.id)\
                            .first()[0]
                beams.append({beam_class, beam_dest})
            f_info = {"old_state":old_state, "new_state":new_state, "beams": beams}
            fault_info.update(f_info)

        except Exception as e:
            self.logger.log("SESSION ERROR: Add Fault ", message.to_string())
            print(traceback.format_exc())
        return fault_info

    def process_bypass(self, message):
        """
        Processes an analog or digital device bypass
        Params:
            message: [type(of message), id, oldvalue, newvalue, aux(expiration time in secs)]        
        Output:
            bypass_info: ['type': 'bypass', 'timestamp' str, 'new_state': str, 'expiration': str, 'description': str]
        """
        timestamp_secs = int(self.timestamp.strftime("%s"))
        expiration = datetime.fromtimestamp(message.aux + timestamp_secs).strftime("%Y-%m-%d %H:%M:%S.%f")

        new_state = self.get_fault_state_from_fault(message.new_value)
        print(new_state)
        try:
            fault_name = self.conf_conn.session.query(models.Fault.name)\
                        .filter(models.Fault.id==message.id).first()[0]
        except:
            self.logger.log("SESSION ERROR: Add Bypass ", message.to_string())
            return
        bypass_info = {"type":"bypass", "timestamp": str(self.timestamp), "new_state":new_state, "expiration":expiration, "description":fault_name}
        return bypass_info

    def get_fault_state_from_fault(self, fstate_id):
        """
        Returns the device state based off of the fault_state.id
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
    
    # TODO - Delete when done testing
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
    
    # TODO - Delete when done testing
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
    
    


