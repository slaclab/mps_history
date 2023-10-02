import config
from confluent_kafka import Producer
import json

class HistorySender:
    """
    Establishes a connection to kafka cluster, and sends data out to them to write to History DB
    """
    def __init__(self, processed_data_queue, dev):
        self.processed_data_queue = processed_data_queue

        self.dev = dev
        if self.dev:
            self.default_dbs = config.db_info["dev-rhel7"]
        else:
            self.default_dbs = config.db_info["test"]

        self.connect_kafka()

    def delivery_report_test(self, err, msg):
        """
        Kafka delivery handler. Exits program when fail to send.
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
        else: # TODO: may omit this else if messages spams console
            print("Message produced: %s" % (str(msg)))

    def connect_kafka(self):
        """
        Creates an interactable connection to Kafka through a boostrap_server
        """
        self.kafka_ip = self.default_dbs["kafka"]["ip"]
        self.kafka_topic = self.default_dbs["kafka"]["topic"]
        self.kafka_producer_config = self.default_dbs["kafka"]["producer_config"]
        print(self.kafka_producer_config)

        self.kafka_producer = Producer(self.kafka_producer_config)

        # Send initial message to see if connection is valid
        self.kafka_producer.produce(self.kafka_topic, value='{"json":"data"}', on_delivery=self.delivery_report_test)
        self.kafka_producer.poll(1) # wait 1 second for event if failed
        
        return

    def process_queue(self):
        """
        Process any items in the processed_data_queue
        """
        while True: 
            if self.processed_data_queue.qsize() > 0:
                message = self.processed_data_queue.get()
                print("Sender received message! ", end="")
                print("current queue size: " + str(self.processed_data_queue.qsize()), end=" ")
                print("Message ", message)
            
                self.send_data(message)
    
    def send_data(self, data):
        """
        Serializes data, then sends to Kafka topic
        """
        # TODO: Keep it as JSON to send, although its a bit bulky, its quick to process since the data is already a dict
            # May use a different serializing method if too bulky. take a look at libraries that can do packing like
            # https://msgpack.org/index.html or https://protobuf.dev/ or https://flatbuffers.dev/
        record_data = json.dumps(data)
        self.kafka_producer.produce(self.kafka_topic, value=record_data, on_delivery=self.delivery_report)
        self.kafka_producer.poll() # Trigger delivery report
        

