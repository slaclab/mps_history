import os
import struct
import config, sys, datetime, traceback
import requests
from ctypes import *
from datetime import datetime
from enum import Enum
from confluent_kafka import Consumer
from sqlalchemy import inspect
from datetime import datetime

from mps_database.mps_config import MPSConfig, models
from sqlalchemy import select

import struct

class Message:
    def __init__(self, type, id, old_value, new_value, aux):
        self.type = type
        self.id = id
        self.old_value = old_value
        self.new_value = new_value
        self.aux = aux
        self.timestamp = None # Will be set after parsing
    
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

class LogbookTag(str, Enum):
    # Theese are the id of the tags, and they can be found in the README.md
    Fault="803bf78d-a718-419d-bd81-979bee35cf54"
    Channel="a45b3865-0e31-4083-be08-0b69274096a8"
    Bypass="5723c868-0b39-4be9-ae08-9d4e5cd8f86f"

class HistoryBroker:
    """
    Processes the data from central_nodes by querying the config DB, then sending it to 
    Kafka -> kubernetes infrastructure -> history DB
    """
    def __init__(self):
        self.dev = os.getenv("HISTORY_DEV")
        self.sock = None
        self.elog_endpoint = "https://accel-webapp-dev.slac.stanford.edu/api/elog-apptoken/v1/entries"

        if self.dev: # This will point to the container filesystem with the config baked in
            self.default_dbs = config.db_info["container-dev"]
        else: # TODO - make this production but for container as well
            self.default_dbs = config.db_info["container-dev"] # Temp set to container-dev for now

        self.connect_conf_db()    
        self.connect_kafka()
        self.test_elog_connection()

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
                    
                    # Get Kafka message timestamp
                    kafka_timestamp = msg.timestamp()
                    timestamp_type = kafka_timestamp[0]  # 0=CreateTime, 1=LogAppendTime
                    timestamp_value = kafka_timestamp[1]  # Timestamp in milliseconds
                    
                    # Convert to readable format
                    timestamp_str = datetime.fromtimestamp(timestamp_value/1000).strftime('%Y-%m-%dT%H:%M:%S.%f')
                    # For the value, try to parse it as your Message struct
                    try:
                        if msg.value():
                            # Try to parse as binary Message struct
                            message_data = self.parse_message(msg.value())
                            # Print message details
                            print(f"\n--- Message at offset {msg.offset()} ---")
                            print(f"Timestamp: {timestamp_str} ({timestamp_value}ms)")
                            print(f"Type: {message_data.type}")
                            print(f"ID: {message_data.id}")
                            print(f"Old Value: {message_data.old_value}")
                            print(f"New Value: {message_data.new_value}")
                            print(f"Aux: {message_data.aux}")

                            message_data.timestamp = timestamp_str
                            
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
                print("== Successfully connected to MPS database and verified access ==")
            else:
                raise Exception("Database connection test failed")
        except Exception as e:
            print(e)
            print("DB ERROR: Unable to Connect to Database ", str(db_file))
            exit()
        return    
    
    def test_database_connection(self):
        """
        Tests if the database connection is working by running a simple query
        """
        try:
            # List all tables in the database
            print("== Initialization: Testing sqlite database connection ==")
            inspector = inspect(self.conf_conn.engine)
            tables = inspector.get_table_names()
            print(f"Tables in database: {tables}")

            return True
        except Exception as e:
            print(f"Database connection test failed: {e}")
            return False
        
    def test_elog_connection(self):
        self.elog_user_password = os.getenv("ELOG_USER_PASSWORD")
        if (self.elog_user_password == None):
            raise ValueError("Missing environment variable - ELOG_USER_PASSWORD")
        self.headers = {"x-vouch-idp-accesstoken": self.elog_user_password}
        test_endpoint = "https://accel-webapp-dev.slac.stanford.edu/api/elog-apptoken/v1/logbooks/684c71350de278523b9f3daf/tags"

        try:
            print("== Initialization: Testing elog connection with a simple GET request ==")
            response = requests.get(test_endpoint, headers=self.headers)
            
            # Try to raise for status
            response.raise_for_status()
            
            print(f"Successfully sent to ELOG API: {response.status_code}")
            print(f"== Ready to write to ELOG API ==")
            return True
        except requests.exceptions.HTTPError as http_err:
            print(f"HTTP Error: {http_err}")
            
            # Print detailed response information
            print(f"Response status code: {response.status_code}")
            print(f"Response reason: {response.reason}")
            
            # Try to get response text (may contain error details)
            try:
                print(f"Response text: {response.text}")
            except:
                print("Could not get response text")
            
            # Try to parse JSON response (may contain error details)
            try:
                print(f"Response JSON: {response.json()}")
            except:
                print("Response is not valid JSON")
            
            print(f"Request URL: {response.request.url}")
            print(f"Request method: {response.request.method}")
            print(f"Request headers: {response.request.headers}")
            print(f"Request body: {response.request.body}")
            
            return False
        except requests.exceptions.ConnectionError as conn_err:
            print(f"Connection Error: {conn_err}")
            return False
        except requests.exceptions.Timeout as timeout_err:
            print(f"Timeout Error: {timeout_err}")
            return False
        except requests.exceptions.RequestException as req_err:
            print(f"Request Error: {req_err}")
            return False
        except Exception as e:
            print(f"General Error: {e}")
            return False

    def parse_message(self, binary_data) -> Message:
        """Parse binary message data into a Message object."""
        try:
            return Message.from_binary(binary_data)
        except Exception as e:
           print(f"Failed to parse message: {str(e)}")
    
    def connect_kafka(self):
        """Connect to the kafka mps data topic"""
        print("== Initialization: Testing kafka connection ==")
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
        print(f"== Ready to consume messages from {topic} kafka ==")

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
            print("DATA ERROR: Bad Message Type", message.to_string())
            return
        print(data) # TEMP

        # Send the data to the Kubernetes infrastructure
        self.send_data(data)
        return

    def send_data(self, data):
        """
        Writes processed data to ELOG backend API based on the message type
        """
        print(f"Writing to the ELOG (mps-history) logbook through backend API for: {data}")

        # Extract relevant information from the data
        data_type = data.get('type', 'unknown')
        timestamp = data.get('timestamp', '0')
        logbook_tag = None
        # Build title and text based on data type
        if data_type == 'bypass':
            bypass_info = data.get('bypass', {})
            bypass_type = bypass_info.get('type', 'unknown')
            
            # Different handling based on bypass type
            if bypass_type == 'fault':
                description = bypass_info.get('description', 'No description')
                expiration = bypass_info.get('expiration', 'No expiration')
                title = f"MPS Bypass: {description}. Expires: {expiration}"
                text = (f"<p><b>Expiration</b>: {expiration}<br>"
                        f"<b>Timestamp</b>: {timestamp}<br>")
                if 'new_state' in data:
                    text += f"<b>New State</b>: {data['new_state']}"
                text += "</p>"

            elif bypass_type == 'application':
                card_number = bypass_info.get('card_number', 'Unknown')
                crate_loc = bypass_info.get('crate_loc', 'Unknown')
                expiration = bypass_info.get('expiration', 'No expiration')
                title = f"MPS Bypass: Application Card {card_number}, Crate {crate_loc}. Expires: {expiration}"
                text = (f"<p><b>Expiration</b>: {expiration}<br>"
                        f"<b>Card Number</b>: {card_number}<br>"
                        f"<b>Crate Location</b>: {crate_loc}<br>"
                        f"<b>Timestamp</b>: {timestamp}</p>")                
            else:
                title = f"MPS Bypass: {bypass_type}"
                text = f"Bypass Details: {str(bypass_info)}\nTimestamp: {timestamp}"

            logbook_tag = LogbookTag.Bypass
                
        elif data_type == 'channel':
            channel_info = data.get('channel', {})
            channel_name = channel_info.get('name', 'Unknown')
            old_state = data.get('old_state', 'Unknown')
            new_state = data.get('new_state', 'Unknown')
            
            title = f"MPS Channel Change: {channel_name}. {old_state} -> {new_state}"
            text = (f"<p><b>Channel</b>: {channel_name}<br>"
                    f"<b>Old State</b>: {old_state}<br>"
                    f"<b>New State</b>: {new_state}<br>"
                    f"<b>Card</b>: {channel_info.get('card_number', 'Unknown')}<br>"
                    f"<b>Location</b>: {channel_info.get('crate_loc', 'Unknown')}<br>"
                    f"<b>Timestamp</b>: {timestamp}</p>")
            logbook_tag = LogbookTag.Channel
                    
        elif data_type == 'fault':
            fault_info = data.get('fault', {})
            fault_id = fault_info.get('id', 'Unknown')
            description = fault_info.get('description', 'No description')
            old_state = data.get('old_state', 'Unknown')
            new_state = data.get('new_state', 'Unknown')
            
            title = f"MPS Fault State Change: {description}. {old_state} -> {new_state}"
            
            # Format the beams information if available
            beams_text = ""
            if 'beams' in fault_info and fault_info['beams']:
                beams_text = "<b>Affected Beam Destinations</b>:<ol>"
                for beam in fault_info['beams']:
                    beams_text += f"<li>{beam.get('destination', 'Unknown')} -> {beam.get('class', 'Unknown')}</li>"
                beams_text += "</ol>"
            text = (f"<p><b>Description</b>: {description}<br>"
                    f"<b>Old State</b>: {old_state}<br>"
                    f"<b>New State</b>: {new_state}<br>"
                    f"<b>Active</b>: {fault_info.get('active', 'Unknown')}<br>"
                    f"{beams_text}"
                    f"<b>Timestamp</b>: {timestamp}")
            logbook_tag = LogbookTag.Fault
        else:
            # Generic handler for other types
            title = f"MPS Event: {data_type}"
            text = f"Event details: {str(data)}"

        try:
            # Initialize with current date/time as fallback
            event_at = datetime.now().strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
            summary_date = datetime.now().strftime('%Y-%m-%d')
            
            # Try to parse the timestamp from the data
            if timestamp and timestamp != '0':
                # Debug the timestamp format
                print(f"Parsing timestamp: '{timestamp}'")
                
                try:
                    # Assume timestamp is in 'YYYY-MM-DD HH:MM:SS.ffffff' format
                    dt = datetime.strptime(timestamp, '%Y-%m-%dT%H:%M:%S.%f')
                    
                    # Format event_at to ISO 8601 with truncated microseconds
                    event_at = dt.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
                    
                    # Format summary_date as just the date part
                    summary_date = dt.strftime('%Y-%m-%d')
                    
                    print(f"Successfully parsed timestamp to: {event_at} and date: {summary_date}")
                except ValueError as ve:
                    # Try alternative format without microseconds
                    try:
                        dt = datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S')
                        event_at = dt.strftime('%Y-%m-%dT%H:%M:%S.000Z')
                        summary_date = dt.strftime('%Y-%m-%d')
                        print(f"Parsed timestamp without microseconds: {event_at} and date: {summary_date}")
                    except Exception as e2:
                        print(f"Failed to parse timestamp with second format: {e2}")
        except Exception as e:
            print(f"Error handling timestamp: {e}")

        # Construct the payload
        payload = {
            "logbooks": ["684c71350de278523b9f3daf"],
            "title": title,
            "text": text,
            "note": "",
            "tags": [logbook_tag.value],
            "attachments": [],
            # "summarizes": { # We can skip this field
            #     "shiftId": "",
            #     "date": summary_date
            # },
            "eventAt": event_at,
            "userIdsToNotify": []
        }
        print(f"Writing this payload to ELOG: {payload}")

        # Send the request
        try:
            print(f"Sending request to: {self.elog_endpoint}")
            print(f"Headers: {self.headers}")
            response = requests.post(self.elog_endpoint, headers=self.headers, json=payload)
            
            print(f"Response status code: {response.status_code}")
            print(f"Response headers: {response.headers}")
            
            # Try to raise for status
            response.raise_for_status()
            
            print(f"Successfully sent to ELOG API: {response.status_code}")
            return True
        except requests.exceptions.HTTPError as http_err:
            print(f"HTTP Error: {http_err}")
            
            # Print detailed response information
            print(f"Response status code: {response.status_code}")
            print(f"Response reason: {response.reason}")
            
            # Try to get response text (may contain error details)
            try:
                print(f"Response text: {response.text}")
            except:
                print("Could not get response text")
            
            # Try to parse JSON response (may contain error details)
            try:
                print(f"Response JSON: {response.json()}")
            except:
                print("Response is not valid JSON")
            
            print(f"Request URL: {response.request.url}")
            print(f"Request method: {response.request.method}")
            print(f"Request headers: {response.request.headers}")
            print(f"Request body: {response.request.body}")
            
            return False
        except requests.exceptions.ConnectionError as conn_err:
            print(f"Connection Error: {conn_err}")
            return False
        except requests.exceptions.Timeout as timeout_err:
            print(f"Timeout Error: {timeout_err}")
            return False
        except requests.exceptions.RequestException as req_err:
            print(f"Request Error: {req_err}")
            return False
        except Exception as e:
            print(f"General Error: {e}")
            print(f"Failed payload: {payload}")
            return False

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
            print("SESSION ERROR: Add Channel ", message.to_string())
            print(traceback.format_exc())
            return
        channel_info = {"type":"channel", "timestamp": str(message.timestamp), "old_state":old_state, "new_state":new_state,\
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
            all_fault_info = {"type":"fault", "timestamp": str(message.timestamp), "old_state":old_state, "new_state":new_state, "fault": {}}
            all_fault_info['fault'].update(f_info)
            all_fault_info['fault'].update(beam_info)

        except Exception as e:
            print("SESSION ERROR: Add Fault ", message.to_string())
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
        expiration = datetime.fromtimestamp(message.aux).strftime('%Y-%m-%dT%H:%M:%S.%f')
        # TODO: Fix issue with timestamp not including precision higher than seconds (i.e. it shows up like 20 secs instead of 20.xxx secs)
        # print(timestamp_secs) # TEMP
        # print(message.aux) # TEMP
        # print(expiration) # TEMP
        try:
            if (message.type == HistoryMessageType.BypassApplicationType.value):
                # TODO: Fix issue with application not being able to be sent because '-1' isn't allowed
                # Get crate id, then get crate location
                crate_id = self.conf_conn.session.query(models.ApplicationCard.crate_id)\
                .filter(models.ApplicationCard.id==message.id)
                crate_loc = self.conf_conn.session.query(models.Crate)\
                .filter(models.Crate.id==crate_id)\
                .first().location
                bypass_info = {"type":"bypass", "timestamp": str(message.timestamp),
                "bypass" : {"type":"application", "expiration":expiration, "card_number":message.id, "crate_loc": crate_loc}}
            elif (message.type == HistoryMessageType.BypassAnalogType.value):
                fault_name = self.conf_conn.session.query(models.Fault.name)\
                .filter(models.Fault.id==message.id).first()[0]
                bypass_info = {"type":"bypass", "timestamp": str(message.timestamp),
                "bypass" : {"type":"fault", "expiration":expiration, "description":fault_name}}
            else: # Digital
                new_state = self.get_fault_state_from_fault(message.new_value)
                fault_name = self.conf_conn.session.query(models.Fault.name)\
                .filter(models.Fault.id==message.id).first()[0]
                bypass_info = {"type":"bypass", "timestamp": str(message.timestamp), "new_state":new_state,
                "bypass" : {"type":"fault", "expiration":expiration, "description":fault_name}}
        except:
            print("SESSION ERROR: Add Bypass ", message.to_string())
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
    main_processor = HistoryBroker()
    main_processor.process_loop()

    return

if __name__ == "__main__":
    main()


