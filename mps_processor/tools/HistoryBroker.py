import os
import struct
import config, sys, datetime, traceback
from ctypes import *
from datetime import datetime
from enum import Enum
from confluent_kafka import Consumer
from sqlalchemy import inspect
""" TEMP """
# Forced config mps_database to point to the new_mpsdb 
import sys
# caution: path[0] is reserved for script path (or '' in REPL)
# sys.path.insert(1, '/sdf/home/p/pnispero/mps/mps_database_new')
sys.path.insert(1, '/home/pnispero/mps_history/mps_database/')
""" TEMP """

from mps_database.mps_config import MPSConfig, models
from mps_processor.tools import logger
from sqlalchemy import select

import struct

class Message:
    def __init__(self, type, id, old_value, new_value, aux):
        self.type = type
        self.id = id
        self.old_value = old_value
        self.new_value = new_value
        self.aux = aux
    
    @classmethod
    def from_binary(cls, binary_data):
        if len(binary_data) < 20:
            raise ValueError(f"Message too short: {len(binary_data)} bytes")
        
        # Unpack 5 uint32_t values (5 'I' values in struct format)
        # '<' means little-endian
        type_val, id_val, old_val, new_val, aux_val = struct.unpack('<IIIII', binary_data)
        return cls(type_val, id_val, old_val, new_val, aux_val)
        
    def to_string(self):
        return f"Message(type={self.type}, id={self.id}, old_value={self.old_value}, new_value={self.new_value}, aux={self.aux})"

class HistoryMessageType(Enum):
  FaultStateType=1         # Fault change state (Faulted/Not Faulted)
  BypassDigitalType=2      # Bypass digital fault
  BypassAnalogType=3       # Bypass analog fault
  BypassApplicationType=4  # Bypass analog fault
  DigitalChannelType=5     # Change in digital channel
  AnalogChannelType=6      # Change in analog device threshold status

class HistoryBroker:
    """
    Processes the data from central_nodes by querying the config DB, then sending it to 
    Kafka -> kubernetes infrastructure -> history DB
    """
    def __init__(self):
        self.dev = os.getenv("HISTORY_DEV")
        self.sock = None
        self.timestamp = 0
        self.logger = logger.Logger(stdout=True, dev=self.dev) # TODO - may need to change filenames

        if self.dev:
            self.default_dbs = config.db_info["dev-rhel7"]
        else:
            self.default_dbs = config.db_info["test"]

        self.connect_conf_db()    
        self.connect_kafka()

    def process_loop(self):
        """
        Process any new messages from Kafka
        """
        # Poll for new messages from Kafka and print them.
        try:
            while True:
                msg = self.consumer.poll(1.0)
                if msg is None:
                    # Initial message consumption may take up to
                    # `session.timeout.ms` for the consumer group to
                    # rebalance and start consuming
                    print("Waiting...")
                elif msg.error():
                    print(f"ERROR: {msg.error()}")
                else:
                    # Process the message
                    key = msg.key().decode('utf-8') if msg.key() else None
                    
                    # For the value, try to parse it as your Message struct
                    try:
                        if msg.value():
                            # Try to parse as binary Message struct
                            message_data = self.parse_message(msg.value())
                            # Print message details
                            print(f"\n--- Message at offset {msg.offset()} ---")
                            print(f"Type: {message_data.type}")
                            print(f"ID: {message_data.id}")
                            print(f"Old Value: {message_data.old_value}")
                            print(f"New Value: {message_data.new_value}")
                            print(f"Aux: {message_data.aux}")
                            
                            self.decode_message(message_data)

                        else:
                            print(f"Consumed event with null value from topic {msg.topic()}")
                    except Exception as e:
                        # If binary parsing fails, try to decode as string
                        try:
                            value = msg.value().decode('utf-8') if msg.value() else None
                            print(f"Consumed event from topic {msg.topic()}: key = {key} value = {value}")
                        except UnicodeDecodeError:
                            # If not valid UTF-8, show as hex
                            hex_value = msg.value().hex() if msg.value() else None
                            print(f"Consumed binary event from topic {msg.topic()}: key = {key} value (hex) = {hex_value}")
        except KeyboardInterrupt:
            pass
        finally:
            # Leave group and commit final offsets
            self.consumer.close()
    
    def connect_conf_db(self):
        """
        Creates a interactable connection to the configuration database
        """
        db_file = self.default_dbs["file_paths"]["config"] + "/" + self.default_dbs["file_names"]["config"]
        print(db_file)
        try:
            # Create connection
            self.conf_conn = MPSConfig(db_file)
            
            # Test connection by running a simple query
            test_successful = self.test_database_connection()
            
            if test_successful:
                print("Successfully connected to MPS database and verified access")
            else:
                raise Exception("Database connection test failed")
        except Exception as e:
            print(e)
            self.logger.log("DB ERROR: Unable to Connect to Database ", str(db_file))
            exit()
        return    
    
    def test_database_connection(self):
        """
        Tests if the database connection is working by running a simple query
        """
        try:
            # List all tables in the database
            inspector = inspect(self.conf_conn.engine)
            tables = inspector.get_table_names()
            print(f"Tables in database: {tables}")
            

            channel = self.conf_conn.session.query(models.Channel)\
                        .filter(models.Channel.id==1)\
                        .first()
            return True
        except Exception as e:
            print(f"Database connection test failed: {e}")
            return False

    def parse_message(self, binary_data) -> Message:
        """Parse binary message data into a Message object."""
        try:
            return Message.from_binary(binary_data)
        except Exception as e:
           print(f"Failed to parse message: {str(e)}")
    
    def connect_kafka(self):
        """Connect to the kafka mps data topic"""
        sasl_password = os.getenv("KAFKA_PASSWORD")
        if (sasl_password == None):
            raise ValueError("Missing environment variable - KAFKA_PASSWORD")

        config = {
            # User-specific properties that you must set
            'bootstrap.servers': '172.24.8.129:9094',
            'sasl.username':     'mps-data-injestion-publisher',
            'sasl.password':     sasl_password,

            # Fixed properties
            'security.protocol': 'SASL_PLAINTEXT',
            'sasl.mechanisms':   'SCRAM-SHA-512',
            'group.id':          'mps-data-injestion-publisher-group'
        }

        # Remove SASL settings if not using authentication
        if not config['sasl.username']:
            config.pop('sasl.username')
            config.pop('sasl.password')
            config.pop('sasl.mechanisms', None)

        # Create Consumer instance
        self.consumer = Consumer(config)

        # Subscribe to topic
        topic = "mps-data-injestion"
        self.consumer.subscribe([topic])

    def decode_message(self, message: Message):
        """
        Determines the type of the message, and sends it to the proper function for processing/including to the db
        """
        print("decodeing message") # TEMP
        if (message.type == HistoryMessageType.FaultStateType.value): # FaultStateType 
            data = self.process_fault(message)
        elif (message.type == HistoryMessageType.BypassAnalogType.value or message.type == HistoryMessageType.BypassDigitalType.value\
              or message.type == HistoryMessageType.BypassApplicationType.value ): # BypassStateType
            data = self.process_bypass(message)
        elif (message.type == HistoryMessageType.DigitalChannelType.value or message.type == HistoryMessageType.AnalogChannelType.value): # ChannelType (DigitalChannel or AnalogChannel)
            data = self.process_channel(message)
        else:
            self.logger.log("DATA ERROR: Bad Message Type", message.to_string())
            return
        print(data) # TEMP

        # Send the data to the Kubernetes infrastructure
        self.send_data(data)
        return

    def send_data(self, data):
        # TODO: Update this to write to the ELOG backend API
        """
        Writes processed data to ELOG backend API
        """
        print(f"Writing to ELOG (mps-history) logbook thorugh backend API for: {data}")
        # self.processed_data_queue.put(data)
        return

    def process_channel(self, message: Message):
        """
        Processes a channel (analog or digital device)
        Params:
            message: [type(of message), id (channel.id), old_value, new_value]
        Output:
            channel_info: ["type":"channel", "timestamp": str, "old_state": str, "new_state": str, "channel_number": int,
              "channel_name": str,"card_number": int, "crate_loc": str]
        """
        try:
            channel = self.conf_conn.session.query(models.Channel)\
                        .filter(models.Channel.id==message.id)\
                        .first()
            app_card = self.conf_conn.session.query(models.ApplicationCard)\
                        .filter(models.ApplicationCard.id==channel.card_id)\
                        .first()
            crate_loc = self.conf_conn.session.query(models.Crate)\
                        .filter(models.Crate.id==app_card.crate_id)\
                        .first().location
            if channel.discriminator == 'digital_channel':
                digital_channel = self.conf_conn.session.query(models.DigitalChannel)\
                        .filter(models.DigitalChannel.id==message.id)\
                        .first()
                old_state = digital_channel.z_name # z name is zero name, and o_name is one name
                new_state = digital_channel.z_name
                if (message.old_value > 0):
                    old_state = digital_channel.o_name
                if (message.new_value > 0):
                    new_state = digital_channel.o_name
            else: # analog
                    old_state, new_state = hex(message.old_value), hex(message.new_value) 
        except:
            self.logger.log("SESSION ERROR: Add Channel ", message.to_string())
            print(traceback.format_exc())
            return
        channel_info = {"type":"channel", "timestamp": str(self.timestamp), "old_state":old_state, "new_state":new_state,\
                         "channel": {"number":channel.number, "name":channel.name,"card_number":app_card.number, "crate_loc":crate_loc}}
        return channel_info


    def process_fault(self, message: Message):
        """
        Processes a single fault
        Params:
            message: [type(of message), id, old_value, new_value]
        Output:
            all_fault_info: ['type': 'fault', 'timestamp': str, 'old_state': str, 'new_state': str, 
                         'fault': {'id': int, 'description': str, 'active': bool, 'beams' : ['class': str, 'destination': str]} ]
        """
        try:   
            fault = self.conf_conn.session.query(models.Fault)\
                    .filter(models.Fault.id==message.id).first()
            
            # Determine the new and old fault state names
            old_state = self.get_fault_state_from_fault(message.old_value)
            new_state = self.get_fault_state_from_fault(message.new_value)
        
            # Determine if active, the fault id and description(fault.name)
            if message.new_value == 0:
                f_info = {"id":message.id, "description":("FAULT CLEARED - " + fault.name), "active":False}
            else:
                f_info = {"id":fault.id, "description":fault.name, "active":True}

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
                beams.append({"class": beam_class, "destination": beam_dest})
            beam_info = {"beams": beams}
            all_fault_info = {"type":"fault", "timestamp": str(self.timestamp), "old_state":old_state, "new_state":new_state, "fault": {}}
            all_fault_info['fault'].update(f_info)
            all_fault_info['fault'].update(beam_info)

        except Exception as e:
            self.logger.log("SESSION ERROR: Add Fault ", message.to_string())
            print(traceback.format_exc())
            return
        return all_fault_info

    def process_bypass(self, message: Message):
        """
        Processes an analog/digital fault or application card bypass
        Params:
            message: [type(of message), id, newvalue, aux(expiration time in secs, already accounts for time since 1970)]        
        Output:
            bypass_info: ['type': 'bypass', 'timestamp' str, 'new_state': str, 'expiration': str, 'description': str]
        """
        expiration = datetime.fromtimestamp(message.aux).strftime("%Y-%m-%d %H:%M:%S.%f")
        # TODO: Fix issue with timestamp not including precision higher than seconds (i.e. it shows up like 20 secs instead of 20.xxx secs)
        # print(timestamp_secs) # TEMP
        # print(message.aux) # TEMP
        # print(expiration) # TEMP
        try:
            if (message.type == HistoryMessageType.BypassApplicationType.value):
                # TODO: Fix issue with application not being able to be sent because '-1' isn't allowed
                bypass_info = {"type":"bypass", "timestamp": str(self.timestamp),
                "bypass" : {"type":"application", "expiration":expiration, "card_number":message.id}}
            elif (message.type == HistoryMessageType.BypassAnalogType.value):
                fault_name = self.conf_conn.session.query(models.Fault.name)\
                .filter(models.Fault.id==message.id).first()[0]
                bypass_info = {"type":"bypass", "timestamp": str(self.timestamp),
                "bypass" : {"type":"fault", "expiration":expiration, "description":fault_name}}
            else: # Digital
                new_state = self.get_fault_state_from_fault(message.new_value)
                fault_name = self.conf_conn.session.query(models.Fault.name)\
                .filter(models.Fault.id==message.id).first()[0]
                bypass_info = {"type":"bypass", "timestamp": str(self.timestamp), "new_state":new_state,
                "bypass" : {"type":"fault", "expiration":expiration, "description":fault_name}}
        except:
            self.logger.log("SESSION ERROR: Add Bypass ", message.to_string())
            return
        return bypass_info

    def get_fault_state_from_fault(self, fstate_id):
        """
        Returns the fault state based off the fault_state.id
        """
        if fstate_id == 0:
            return "None"
        fault_state = self.conf_conn.session.query(models.FaultState).filter(models.FaultState.id==fstate_id).first()
        return fault_state.name
    
def main():
    hist = HistoryBroker()
    hist.process_queue()

    return

if __name__ == "__main__":
    main()


