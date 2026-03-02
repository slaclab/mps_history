#!/usr/bin/env python

from confluent_kafka import Consumer
from enum import Enum
import struct

# Message type enum values (match your C++ enum)
class HistoryMessageType(Enum):
  FaultStateType=1         # Fault change state (Faulted/Not Faulted)
  BypassDigitalType=2      # Bypass digital fault
  BypassAnalogType=3       # Bypass analog fault
  BypassApplicationType=4  # Bypass analog fault
  DigitalChannelType=5     # Change in digital channel
  AnalogChannelType=6      # Change in analog device threshold status

def parse_message(binary_data):
    """Parse binary message data into a dictionary."""
    # Make sure we have enough data
    if len(binary_data) < 20:  # 5 uint32_t fields * 4 bytes
        return {"error": f"Message too short: {len(binary_data)} bytes"}
    
    try:
        # Unpack 5 uint32_t values (5 'I' values in struct format)
        # '<' means little-endian
        type_val, id_val, old_val, new_val, aux_val = struct.unpack('<IIIII', binary_data)
        
        return {
            "type": type_val,
            "id": id_val,
            "oldValue": old_val,
            "newValue": new_val,
            "aux": aux_val
        }
    except struct.error as e:
        return {"error": f"Failed to parse message: {str(e)}"}

if __name__ == '__main__':

    config = {
        # User-specific properties that you must set
        'bootstrap.servers': 'localhost:9094',
        'sasl.username':     '',
        'sasl.password':     '',

        # Fixed properties
        'security.protocol': 'PLAINTEXT',
        'sasl.mechanisms':   'PLAIN',
        'group.id':          'kafka-python-getting-started',
        'auto.offset.reset': 'earliest'
    }

    # Remove SASL settings if not using authentication
    if not config['sasl.username']:
        config.pop('sasl.username')
        config.pop('sasl.password')
        config.pop('sasl.mechanisms', None)

    # Create Consumer instance
    consumer = Consumer(config)

    # Subscribe to topic
    topic = "your_topic"
    consumer.subscribe([topic])

    # Poll for new messages from Kafka and print them.
    try:
        while True:
            msg = consumer.poll(1.0)
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
                        message_data = parse_message(msg.value())
                        
                        # Print message details
                        print(f"\n--- Message at offset {msg.offset()} ---")
                        if "error" in message_data:
                            print(f"Error parsing message: {message_data['error']}")
                            print(f"Raw data (hex): {msg.value().hex()}")
                        else:
                            print(f"Type: {message_data['type']}")
                            print(f"ID: {message_data['id']}")
                            print(f"Old Value: {message_data['oldValue']}")
                            print(f"New Value: {message_data['newValue']}")
                            print(f"Aux: {message_data['aux']}")
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
        consumer.close()