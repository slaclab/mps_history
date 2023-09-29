from confluent_kafka import Producer

def delivery_report(err, msg):
    """
    Kafka delivery handler. Triggered by poll() or flush()
    Called on success or fail of message delivery
    Params: (These params are built into on_delivery callback)
        err (KafkaError): The error that occurred on None on success.
        msg (Message): The message that was produced or failed.
    """
    if err is not None:
        print("Failed to deliver message: %s: %s" % (str(msg), str(err)))
        exit()
    else:
        print("Message produced: %s" % (str(msg)))

conf = {"bootstrap.servers": "172.24.5.197:9094",
        "security.protocol": "SASL_PLAINTEXT",
        "sasl.username": "mps-data-injestion-publisher",
        "sasl.password": "H9MD7vxf9ABPDsKTyxvOtTKL14hCSU8R",
        "sasl.mechanism": "SCRAM-SHA-512" }

producer = Producer(conf)
producer.produce("mps-data-injestion", 
                 value='{"json":"data"}', 
                 key="device-id", 
                 on_delivery=delivery_report)
producer.poll(1) # wait 1 second for event if failed