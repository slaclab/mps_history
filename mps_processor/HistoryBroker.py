import os
import struct
import time
import config, sys, datetime, traceback
import requests
from collections import deque
from ctypes import *
from itertools import chain
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo
from confluent_kafka import Consumer, KafkaException, TopicPartition
from confluent_kafka import Message as KafkaMessage
from sqlalchemy import inspect

from mps_database.mps_config import MPSConfig, models
from sqlalchemy import select
from mps_processor.HistoryMessageType import HistoryMessageType
from mps_processor.summary_window import LOCAL_TZ, SummaryWindow, WindowEvent

import struct

KAFKA_TOPIC = "mps-data-ingestion"
GROUP_ID = "mps-data-ingestion-publisher-group"
RETRY_DELAY_MIN_S = 5
RETRY_DELAY_MAX_S = 60
# Grouped into summary windows; everything else (bypasses) is posted individually
WINDOWED_TYPES = frozenset({HistoryMessageType.FaultStateType, HistoryMessageType.DigitalChannelType,
                            HistoryMessageType.AnalogChannelType})


class Message:
    def __init__(self, type: int, id: int, old_value: int, new_value: int, aux: int) -> None:
        self.type = type
        self.id = id
        self.old_value = old_value
        self.new_value = new_value
        self.aux = aux
        self.timestamp: str | None = None # Display string, set after parsing
        self.event_time: datetime | None = None # timezone-aware datetime from the Kafka message timestamp
    
    @classmethod
    def from_binary(cls, binary_data: bytes) -> "Message":
        if len(binary_data) < 20:
            raise ValueError(f"Message too short: {len(binary_data)} bytes")
        
        # Unpack 5 uint32_t values (5 'I' values in struct format)
        # '<' means little-endian
        type_val, id_val, old_val, new_val, aux_val = struct.unpack('<IIIII', binary_data)
        return cls(type_val, id_val, old_val, new_val, aux_val)
        
    def to_string(self) -> str:
        return f"Message(type={self.type}, id={self.id}, old_value={self.old_value}, new_value={self.new_value}, aux={self.aux})"

class HistoryBroker:
    """
    Processes the data from central_nodes by consuming messages from
    Kafka -> Process -> write to ELOG
    """
    def __init__(self, config_db_filepath: str, dev: bool = False) -> None:
        self.dev = dev
        self.sock = None
        if self.dev:
            self.elog_api_base = "https://accel-webapp-dev.slac.stanford.edu/api/elog-apptoken/v1/"
        else:
            self.elog_api_base = "https://accel-webapp.slac.stanford.edu/api/elog-apptoken/v1/"

        self.elog_endpoint = self.elog_api_base + "entries"

        self.windows: dict[tuple[HistoryMessageType, int], SummaryWindow] = {}  # (msg type, fault/channel id) -> open SummaryWindow
        self.outbox: deque[SummaryWindow] = deque()  # closed windows (and bypasses) waiting to be posted, oldest first
        self.consumed: dict[int, int] = {}   # partition -> offset after the last consumed message
        self.committed: dict[int, int] = {}  # partition -> last committed offset
        self.paused: bool = False            # consumer paused while the outbox can't be posted
        self.retry_at: float = 0.0
        self.retry_delay: int = RETRY_DELAY_MIN_S

        self.connect_conf_db(config_db_filepath)    
        self.connect_kafka()
        self.test_elog_connection()

    def process_loop(self) -> None:
        """
        Consume from Kafka and write to the ELOG until interrupted.
        """
        try:
            while True:
                self.heartbeat()
                self.poll()
                self.flush_outbox()
        except KeyboardInterrupt:
            pass
        finally:
            # Open windows and the outbox are not committed, so they are rebuilt from Kafka on restart
            self.consumer.close()

    def heartbeat(self) -> None:
        # Touch heartbeat file so the Kubernetes livenessProbe can verify the loop is alive
        Path("/tmp/healthy").touch()

    def decode(self, msg: KafkaMessage) -> Message | None:
        """Parse a Kafka message into a Message with its event time, or None if it has no usable payload."""
        if not msg.value():
            return None
        message = self.parse_message(msg.value())
        if message is None:
            return None
        message.event_time = datetime.fromtimestamp(msg.timestamp()[1] / 1000, tz=timezone.utc)
        message.timestamp = message.event_time.astimezone(LOCAL_TZ).strftime('%Y-%m-%d %I:%M:%S %p')
        return message

    def poll(self) -> None:
        """Read one message: add a fault/channel event to its window, or queue a bypass to post now."""
        msg = self.consumer.poll(1.0)
        if msg is None:
            # Caught up with Kafka: only now is wall clock a valid event clock.
            # During a backlog replay every event is "old", so windows close on event time instead.
            self.close_expired(datetime.now(timezone.utc))
            self.commit_done()
            return
        if msg.error():
            print(f"ERROR: {msg.error()}")
            return
        self.consumed[msg.partition()] = msg.offset() + 1

        message = self.decode(msg)
        if message is None:
            return
        print(f"[{msg.partition()}:{msg.offset()}] {message.event_time.isoformat()} {message.to_string()}")
        self.close_expired(message.event_time)

        processed_event = self.process_message(message)
        if processed_event is None:
            print(f"PROCESSING ERROR at offset {msg.offset()} — skipping unprocessable message")
            return

        event = WindowEvent(message.event_time, HistoryMessageType(message.type), processed_event, msg.partition(), msg.offset())
        if event.msg_type not in WINDOWED_TYPES:
            self.outbox.append(SummaryWindow(event))  # bypass: one-event window, posted right away
            return
        # Fault and channel ids come from different tables, so the type is part of the window id
        window_id = (event.msg_type, message.id)
        if window_id in self.windows:
            self.windows[window_id].add(event)
        else:
            self.windows[window_id] = SummaryWindow(event)

    def close_expired(self, now: datetime) -> None:
        """Move every window that is WINDOW_TIME past its first event to the outbox, oldest first."""
        expired_window_ids = []
        for window_id, window in self.windows.items():
            if window.is_expired(now):
                expired_window_ids.append(window_id)

        expired_window_ids.sort(key=lambda window_id: self.windows[window_id].start)

        for window_id in expired_window_ids:
            self.outbox.append(self.windows.pop(window_id))

    def flush_outbox(self) -> None:
        """Post closed windows in order; on failure retry with backoff and stop consuming meanwhile."""
        posted = False
        while self.outbox and time.monotonic() >= self.retry_at:
            window = self.outbox[0]
            if not self.post_window(window):
                print(f"ELOG post failed for window starting {window.start.isoformat()}; "
                      f"retrying in {self.retry_delay} s")
                self.retry_at = time.monotonic() + self.retry_delay
                self.retry_delay = min(self.retry_delay * 2, RETRY_DELAY_MAX_S)
                self.set_paused(True)
                break
            self.outbox.popleft()
            posted = True
            self.retry_delay = RETRY_DELAY_MIN_S
            self.heartbeat()
        if posted:
            self.commit_done()
        if not self.outbox:
            self.set_paused(False)

    def commit_done(self) -> None:
        """
        Commit each partition up to its oldest event that is not posted yet (open window or outbox).
        Kafka commits are cumulative, so nothing after that point can be committed, even if posted.
        """
        offsets = dict(self.consumed)
        for window in chain(self.windows.values(), self.outbox):
            for e in window.events:
                offsets[e.partition] = min(offsets[e.partition], e.offset)
        changed_offsets = {}
        for partition, offset in offsets.items():
            if self.committed.get(partition) != offset:
                changed_offsets[partition] = offset

        if not changed_offsets:
            return
        try:
            self.consumer.commit(offsets=[TopicPartition(KAFKA_TOPIC, p, o) for p, o in changed_offsets.items()],
                                 asynchronous=False)
            self.committed.update(changed_offsets)
        except KafkaException as e:
            print(f"Kafka commit failed ({e}); these messages may be posted again after a restart")

    def set_paused(self, paused: bool) -> None:
        """Stop fetching while the ELOG is failing, but keep polling so we stay in the group."""
        if paused == self.paused:
            return
        assignment = self.consumer.assignment()
        if paused:
            self.consumer.pause(assignment)
        else:
            self.consumer.resume(assignment)
        self.paused = paused

    def post_window(self, window: SummaryWindow) -> bool:
        """One entry per window: the normal entry if it has one event, else a summary entry."""
        if not window.is_summary:
            return self.send_data(window.events[0].processed_event)
        tag = self.elog_fault_tag_id if window.events[0].msg_type is HistoryMessageType.FaultStateType \
            else self.elog_channel_tag_id
        return self.post_entry(window.title(), window.body_html(), [tag], window.start)
    
    def connect_conf_db(self, config_db_filepath: str) -> None:
        """
        Creates a interactable connection to the configuration database
        """
        try:
            # Create connection
            self.conf_conn = MPSConfig(config_db_filepath)
            
            # Test connection by running a simple query
            test_successful = self.test_database_connection()
            
            if test_successful:
                print("== Successfully connected to MPS database and verified access ==")
            else:
                raise Exception("Database connection test failed - ", config_db_filepath)
        except Exception as e:
            print(e)
            print("DB ERROR: Unable to Connect to Database ", str(config_db_filepath))
            exit()
        return    
    
    def test_database_connection(self) -> bool:
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
        
    def test_elog_connection(self) -> bool:
        self.elog_user_password = os.getenv("ELOG_USER_PASSWORD")
        if (self.elog_user_password == None):
            raise ValueError("Missing environment variable - ELOG_USER_PASSWORD")
        self.elog_history_logbook_id = os.getenv("ELOG_HISTORY_LOGBOOK_ID")
        if (self.elog_history_logbook_id == None):
            raise ValueError("Missing environment variable - ELOG_HISTORY_LOGBOOK_ID")
        self.elog_bypass_tag_id = os.getenv("ELOG_BYPASS_TAG_ID")
        if (self.elog_bypass_tag_id == None):
            raise ValueError("Missing environment variable - ELOG_BYPASS_TAG_ID")
        self.elog_channel_tag_id = os.getenv("ELOG_CHANNEL_TAG_ID")
        if (self.elog_channel_tag_id == None):
            raise ValueError("Missing environment variable - ELOG_CHANNEL_TAG_ID")
        self.elog_fault_tag_id = os.getenv("ELOG_FAULT_TAG_ID")
        if (self.elog_fault_tag_id == None):
            raise ValueError("Missing environment variable - ELOG_FAULT_TAG_ID")
        self.headers = {"x-vouch-idp-accesstoken": self.elog_user_password}
        test_endpoint = f"{self.elog_api_base}/logbooks/{self.elog_history_logbook_id}/tags"

        try:
            print("== Initialization: Testing elog connection with a simple GET request ==")
            response = requests.get(test_endpoint, headers=self.headers, timeout=15)
            
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

    def parse_message(self, binary_data: bytes) -> Message | None:
        """Parse binary message data into a Message object."""
        try:
            return Message.from_binary(binary_data)
        except Exception as e:
           print(f"Failed to parse message: {str(e)}")
    
    def connect_kafka(self) -> None:
        """Connect to the kafka mps data topic"""
        print("== Initialization: Testing kafka connection ==")
        sasl_password = os.getenv("KAFKA_PASSWORD")
        if (sasl_password == None):
            raise ValueError("Missing environment variable - KAFKA_PASSWORD")
        kafka_bootstrap_server = os.getenv("KAFKA_BOOTSTRAP_SERVER")
        if (kafka_bootstrap_server == None):
            raise ValueError("Missing environment variable - KAFKA_BOOTSTRAP_SERVER")

        config: dict[str, str | bool] = {
            # User-specific properties that you must set
            'bootstrap.servers': kafka_bootstrap_server,
            'sasl.username':     'mps-data-ingestion-publisher',
            'sasl.password':     sasl_password,

            # Fixed properties
            'security.protocol': 'SASL_PLAINTEXT',
            'sasl.mechanisms':   'SCRAM-SHA-512',
            # Disable auto-commit so we only commit after a successful ELOG write (at-least-once delivery)
            'enable.auto.commit': False
        }

        # Remove SASL settings if not using authentication
        if not config['sasl.username']:
            config.pop('sasl.username')
            config.pop('sasl.password')
            config.pop('sasl.mechanisms', None)

        self.consumer = Consumer({**config, 'group.id': GROUP_ID})
        self.consumer.subscribe([KAFKA_TOPIC])
        print(f"== Ready to consume messages from {KAFKA_TOPIC} kafka ==")

    def process_message(self, message: Message) -> dict | None:
        """
        Looks up the message in the config DB and returns the dict used to render its ELOG entry,
        or None if the message can't be processed.
        """
        if (message.type == HistoryMessageType.FaultStateType.value): # FaultStateType
            processed_event = self.process_fault(message)
        elif (message.type == HistoryMessageType.BypassAnalogType.value or message.type == HistoryMessageType.BypassDigitalType.value\
              or message.type == HistoryMessageType.BypassApplicationType.value ): # BypassStateType
            processed_event = self.process_bypass(message)
        elif (message.type == HistoryMessageType.DigitalChannelType.value or message.type == HistoryMessageType.AnalogChannelType.value): # ChannelType (DigitalChannel or AnalogChannel)
            processed_event = self.process_channel(message)
        elif (message.type == HistoryMessageType.BypassExpiredFaultType.value or message.type == HistoryMessageType.BypassExpiredApplicationType.value): # BypassExpiredType
            processed_event = self.process_bypass_expired(message)
        else:
            print("DATA ERROR: Bad Message Type", message.to_string())
            return None

        if processed_event is not None:
            processed_event['event_time'] = message.event_time
        return processed_event

    def send_data(self, processed_event: dict) -> bool:
        """
        Writes processed data to ELOG backend API based on the message type
        """
        print(f"Writing to the ELOG (mps-history) logbook through backend API for: {processed_event}")

        # Extract relevant information from the data
        data_type = processed_event.get('type', 'unknown')
        timestamp = processed_event.get('timestamp', '0')
        logbook_tag = None
        # Build title and text based on data type
        if data_type == 'bypass':
            bypass_info = processed_event.get('bypass', {})
            bypass_type = bypass_info.get('type', 'unknown')
            
            # Different handling based on bypass type
            if bypass_type == 'fault':
                description = bypass_info.get('description', 'No description')
                expiration = bypass_info.get('expiration', 'No expiration')
                title = f"MPS New Bypass: {description}. Expires at: {expiration}"
                text = (f"<p><b>Expiration</b>: {expiration}<br>"
                        f"<b>Timestamp</b>: {timestamp}<br>")
                if 'new_state' in processed_event:
                    text += f"<b>New State</b>: {processed_event['new_state']}"
                text += "</p>"

            elif bypass_type == 'application':
                card_number = bypass_info.get('card_number', 'Unknown')
                crate_loc = bypass_info.get('crate_loc', 'Unknown')
                expiration = bypass_info.get('expiration', 'No expiration')
                title = f"MPS New Bypass: Application Card {card_number}, Crate {crate_loc}. Expires at: {expiration}"
                text = (f"<p><b>Expiration</b>: {expiration}<br>"
                        f"<b>Card Number</b>: {card_number}<br>"
                        f"<b>Crate Location</b>: {crate_loc}<br>"
                        f"<b>Timestamp</b>: {timestamp}</p>")                
            else: # Default
                title = f"MPS New Bypass: {bypass_type}"
                text = f"Bypass Details: {str(bypass_info)}\nTimestamp: {timestamp}"

            logbook_tag = self.elog_bypass_tag_id
        elif data_type == "bypass_expired":
            bypass_info = processed_event.get('bypass', {})
            bypass_type = bypass_info.get('type', 'unknown')

            # Different handling based on bypass type
            if bypass_type == 'fault':
                description = bypass_info.get('description', 'No description')
                title = f"MPS Bypass Expired: {description}."
                text = (f"<p><b>Expired</b>: {timestamp}<br>")
                if 'new_state' in processed_event:
                    text += f"<b>New State</b>: {processed_event['new_state']}"
                text += "</p>"

            elif bypass_type == 'application':
                card_number = bypass_info.get('card_number', 'Unknown')
                crate_loc = bypass_info.get('crate_loc', 'Unknown')
                title = f"MPS Bypass Expired: Application Card {card_number}, Crate {crate_loc}."
                text = (f"<p><b>Expired</b>: {timestamp}<br>"
                        f"<b>Card Number</b>: {card_number}<br>"
                        f"<b>Crate Location</b>: {crate_loc}<br>")                
            else: # Default
                title = f"MPS Bypass Expired: {bypass_type}"
                text = f"Bypass Details: {str(bypass_info)}\nTimestamp: {timestamp}"

            logbook_tag = self.elog_bypass_tag_id
        elif data_type == 'channel':
            channel_info = processed_event.get('channel', {})
            channel_name = channel_info.get('name', 'Unknown')
            old_state = processed_event.get('old_state', 'Unknown')
            new_state = processed_event.get('new_state', 'Unknown')
            
            title = f"MPS Channel Change: {channel_name}. {old_state} -> {new_state}"
            text = (f"<p><b>Channel</b>: {channel_name}<br>"
                    f"<b>Old State</b>: {old_state}<br>"
                    f"<b>New State</b>: {new_state}<br>"
                    f"<b>Card</b>: {channel_info.get('card_number', 'Unknown')}<br>"
                    f"<b>Location</b>: {channel_info.get('crate_loc', 'Unknown')}<br>"
                    f"<b>Link Node ID</b>: {channel_info.get('link_node_id', 'Unknown')}<br>"
                    f"<b>Timestamp</b>: {timestamp}</p>")
            logbook_tag = self.elog_channel_tag_id
                    
        elif data_type == 'fault':
            fault_info = processed_event.get('fault', {})
            fault_id = fault_info.get('id', 'Unknown')
            description = fault_info.get('description', 'No description')
            old_state = processed_event.get('old_state', 'Unknown')
            new_state = processed_event.get('new_state', 'Unknown')
            
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
            logbook_tag = self.elog_fault_tag_id
        else:
            # Generic handler for other types
            title = f"MPS Event: {data_type}"
            text = f"Event details: {str(processed_event)}"

        return self.post_entry(title, text, [logbook_tag], processed_event.get('event_time'))

    def post_entry(self, title: str, text: str, tags: list[str], event_time: datetime | None = None) -> bool:
        """Create an ELOG entry. Returns True on success."""
        if event_time is None:
            event_time = datetime.now(timezone.utc)
        payload = {
            "logbooks": [self.elog_history_logbook_id],
            "title": title,
            "text": text,
            "note": "",
            "tags": [tag for tag in tags if tag],
            "attachments": [],
            "eventAt": event_time.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z',
            "userIdsToNotify": []
        }
        print(f"Posting ELOG entry: {title}")
        return self.elog_post(self.elog_endpoint, json=payload) is not None

    def elog_post(self, url: str, **kwargs: Any) -> requests.Response | None:
        """POST to the ELOG API. Returns the response, or None on any failure. Never logs the auth header."""
        try:
            response = requests.post(url, headers=self.headers, timeout=15, **kwargs)
        except requests.exceptions.RequestException as e:
            print(f"ELOG request to {url} failed: {e}")
            return None
        if not response.ok:
            print(f"ELOG HTTP error {response.status_code} {response.reason} from {url}: {response.text[:500]}")
            return None
        return response

    def process_channel(self, message: Message) -> dict | None:
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
                    old_state = "Is Ok" if message.old_value == 0 else "Is Faulted"
                    new_state = "Is Ok" if message.new_value == 0 else "Is Faulted"
            link_node_id = self.conf_conn.session.query(models.LinkNode)\
                        .filter(models.LinkNode.crate_id==app_card.crate_id)\
                        .first().lnid

        except:
            print("SESSION ERROR: Add Channel ", message.to_string())
            print(traceback.format_exc())
            return
        channel_info = {"type":"channel", "timestamp": str(message.timestamp), "old_state":old_state, "new_state":new_state,\
                         "channel": {"id":message.id, "number":channel.number, "name":channel.name,"card_number":app_card.number, "crate_loc":crate_loc, "link_node_id": link_node_id}}
        return channel_info


    def process_fault(self, message: Message) -> dict | None:
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
                f_info = {"id":message.id, "name":fault.name, "description":("FAULT CLEARED - " + fault.name), "active":False}
            else:
                f_info = {"id":fault.id, "name":fault.name, "description":fault.name, "active":True}

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

    def process_bypass(self, message: Message) -> dict | None:
        """
        Processes an analog/digital fault or application card bypass
        Params:
            message: [type(of message), id, newvalue, aux(expiration time in secs, already accounts for time since 1970)]        
        Output:
            bypass_info: ['type': 'bypass', 'timestamp' str, 'new_state': str, 'expiration': str, 'description': str]
        """
        expiration = datetime.fromtimestamp(message.aux, tz=ZoneInfo("America/Los_Angeles")).strftime('%Y-%m-%d %I:%M:%S %p')
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
    
    def process_bypass_expired(self, message: Message) -> dict | None:
        """
        Processes an analog/digital fault or application card expired bypass
        Params:
            message: [type(of message), id]        
        Output:
            bypass_info: ['type': 'bypass', 'timestamp' str, 'expiration': str, 'description': str]
        """
        try:
            if (message.type == HistoryMessageType.BypassExpiredApplicationType.value):
                # Get crate id, then get crate location
                crate_id = self.conf_conn.session.query(models.ApplicationCard.crate_id)\
                .filter(models.ApplicationCard.id==message.id)
                crate_loc = self.conf_conn.session.query(models.Crate)\
                .filter(models.Crate.id==crate_id)\
                .first().location
                bypass_info = {"type":"bypass_expired", "timestamp": str(message.timestamp),
                "bypass" : {"type":"application", "card_number":message.id, "crate_loc": crate_loc}}
            elif (message.type == HistoryMessageType.BypassExpiredFaultType.value):
                fault_name = self.conf_conn.session.query(models.Fault.name)\
                .filter(models.Fault.id==message.id).first()[0]
                bypass_info = {"type":"bypass_expired", "timestamp": str(message.timestamp),
                "bypass" : {"type":"fault", "description":fault_name}}
        except:
            print("SESSION ERROR: Add Bypass ", message.to_string())
            return
        return bypass_info

    def get_fault_state_from_fault(self, fstate_id: int) -> str:
        """
        Returns the fault state based off the fault_state.id
        """
        if fstate_id == 0:
            return "None"
        fault_state = self.conf_conn.session.query(models.FaultState).filter(models.FaultState.id==fstate_id).first()
        return fault_state.name
    
def main() -> None:
    main_processor = HistoryBroker()
    main_processor.process_loop()

    return

if __name__ == "__main__":
    main()


