import config, sys, datetime, traceback
from ctypes import *
from datetime import datetime

""" TEMP """
# Forced config mps_database to point to the new_mpsdb 
import sys
# caution: path[0] is reserved for script path (or '' in REPL)
sys.path.insert(1, '/u/cd/pnispero/mps/mps_database_new')
""" TEMP """

from mps_database.mps_config import MPSConfig, models
from mps_history.tools import logger
from sqlalchemy import select

from confluent_kafka import Producer
import json

class HistoryBroker:
    """
    Processes the data from central_nodes by querying the config DB, then sending it to 
    Kafka -> kubernetes infrastructure -> history DB
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

        self.connect_kafka()
        self.connect_conf_db()

    def connect_kafka(self):
        """
        Creates an interactable connection to Kafka through a boostrap_server
        """
        self.kafka_topic = self.default_dbs["kafka"]["topic"]
        self.kafka_producer_config = self.default_dbs["kafka"]["producer_config"]
        print(self.kafka_producer_config)

        self.kafka_producer = Producer(self.kafka_producer_config)

        # Send initial message to see if connection is valid
        #self.kafka_producer.produce(self.kafka_topic, value="test", on_delivery=self.delivery_report)
        #self.kafka_producer.poll(1) # wait 1 second for event if failed

        # TODO - send in an initial dummy data to test connection
        # First try out each field as a false item. (to see what the error message is)
        return
    
    def delivery_report(self, err, msg):
        """
        Kafka delivery handler. Triggered by poll() or flush()
        Called on success or fail of message delivery
        Params: (These params are built into on_delivery callback)
            err (KafkaError): The error that occurred on None on success.
            msg (Message): The message that was produced or failed.
        """
        if err is not None:
            print("Failed to deliver message: %s: %s" % (str(msg), str(err)))
            self.logger.log("KAFKA ERROR: Unable to Connect to Kafka Server", str(self.kafka_ip))
            exit()
        else: # TODO: may omit this else if messages spams console
            print("Message produced: %s" % (str(msg)))
    

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
        elif (message.type == 3 or message.type == 4): # ChannelType (DigitalChannel or AnalogChannel)
            data = self.process_channel(message)
        else:
            self.logger.log("DATA ERROR: Bad Message Type", message.to_string())
        print(data)

        # Send the data to the Kubernetes infrastructure
        #self.send_data(data) 
        return

    def send_data(self, data):
        """
        Serializes data, then sends to Kafka topic
        """
        # 1) See how you can send/pack the data - you might want to use packing in multi-processing since it takes time
        # take a look at libraries that can do packing like https://protobuf.dev/ or https://flatbuffers.dev/
        # TODO: Keep it as JSON to send, although its a bit bulky, its quick to process since the data is already a dict
            # May use a different serializing method if too bulky. Maybe pickle. But if after consumed on Claudio end
            # the data is converted to BSON and is smaller, then it should not matter. 
        record_data = json.dumps(data).encode('utf-8')
        self.kafka_producer.produce(self.kafka_topic, value=record_data, on_delivery=self.delivery_report)
        self.kafka_producer.poll() # Trigger delivery report

        return

    def process_channel(self, message):
        """
        Processes a channel (analog or digital device)
        Params:
            message: [type(of message), id, old_value, new_value]
        Output:
            channel_info: ["type":"channel", "timestamp": str, "old_state": str, "new_state": str, "channel_number": int,
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
        channel_info = {"type":"channel", "timestamp": str(self.timestamp), "old_state":old_state, "new_state":new_state,\
                         "channel": {"number":channel.number, "name":channel.name,"card_number":app_card.number, "crate_loc":crate_loc}}
        return channel_info


    def process_fault(self, message):
        """
        Processes a single fault
        Params:
            message: [type(of message), id, old_value, new_value, aux(mitigation_id)]
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

    def process_bypass(self, message):
        """
        Processes an analog or digital device bypass
        Params:
            message: [type(of message), id, newvalue, aux(expiration time in secs)]        
        Output:
            bypass_info: ['type': 'bypass', 'timestamp' str, 'new_state': str, 'expiration': str, 'description': str]
        """
        timestamp_secs = int(self.timestamp.strftime("%s"))
        expiration = datetime.fromtimestamp(message.aux + timestamp_secs).strftime("%Y-%m-%d %H:%M:%S.%f")

        # old_state not necessary
        new_state = self.get_fault_state_from_fault(message.new_value)
        print(new_state)
        try:
            fault_name = self.conf_conn.session.query(models.Fault.name)\
                        .filter(models.Fault.id==message.id).first()[0]
        except:
            self.logger.log("SESSION ERROR: Add Bypass ", message.to_string())
            return
        bypass_info = {"type":"bypass", "timestamp": str(self.timestamp), "new_state":new_state,
                        "bypass" : {"expiration":expiration, "description":fault_name}}
        return bypass_info

    def get_fault_state_from_fault(self, fstate_id):
        """
        Returns the fault state based off the fault_state.id
        """
        if fstate_id == 0:
            return "None"
        fault_state = self.conf_conn.session.query(models.FaultState).filter(models.FaultState.id==fstate_id).first()
        return fault_state.name
    
    
    


