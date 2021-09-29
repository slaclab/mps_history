from io import DEFAULT_BUFFER_SIZE
import sqlalchemy
from mps_database import mps_config, models

import config
from tools import HistorySession
from models import analog_history, bypass_history, input_history, fault_history, mitigation_history
from mps_database.models import Base

from mps_database.mps_config import MPSConfig
from sqlalchemy import select, exc

from ctypes import *

import socket, random, pprint, struct


def main():
    """
    Main function responsible for calling whatever tools functions you need. 
    """
    dev = True
    restart = True

    if dev:
        env = config.db_info["lcls-dev3"]
        host = "lcls-dev3"
    else:
        env = config.db_info["test"]
        host = '127.0.0.1'
    db_path = env["file_paths"]["history"]

    if restart:
        tables = [analog_history.AnalogHistory.__table__, bypass_history.BypassHistory.__table__, fault_history.FaultHistory.__table__, input_history.InputHistory.__table__, mitigation_history.MitigationHistory.__table__]
        #db_url = "sqlite:///{path_to_db}".format(path_to_db=db_path)
        #delete_history_db(tables, env, db_path=db_path)
        create_history_tables(tables, env, db_path=db_path)
    create_socket(host, env)
    return

def create_socket(host, env):
    """
    Acts as a client to connect to HistoryServer backend. 

    Creates a socket and sends over generated test insert data.
    """

    port = 3356
    
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect((host, port))
        # TODO: remove test data from this function
        for data in generate_test_data(env):
            s.sendall(struct.pack('5I', data[0], data[1], data[2], data[3], data[4]))
        for data in create_bad_data():
            s.sendall(struct.pack('5I', data[0], data[1], data[2], data[3], data[4]))

    return

def generate_test_data(env):
    """
    Generates a suite of realistic test data for entering into the history db.

    Type number 3 is skipped because it is defined as "BypassValueType" in the central node ioc, and does not appear to be relevant
    """
    conf_conn = MPSConfig(db_name="config", db_file=env["file_names"]["config"], file_path=env["file_paths"]["config"])
    ad_select = select(models.AnalogDevice.id)
    ad_result = conf_conn.session.execute(ad_select)
    result = [r[0] for r in ad_result]


    #type, fault.id, old_val, new_val, DeviceState.id(opt)
    """
    Orig faults
    fault = [1, random.randint(1,2144), random.randint(0,1), random.randint(0,1), 0]
    fault_aux = [1, random.randint(1,2144), random.randint(0,1), random.randint(0,1), random.randint(1, 79)]
    """
    fault = [1, random.randint(1,3), random.randint(0,1), random.randint(0,1), 0]
    fault_aux = [1, random.randint(1,3), random.randint(0,1), random.randint(0,1), random.randint(1, 79)]
    #BypassStateType, AnalogDevice.id, oldValue, newValue, 0-31
    analog_bypass = [2, random.choice(result), random.randint(0,1), random.randint(0,1), random.randint(0, 31)]
    #BypassStateType, DeviceInput.id, oldValue, newValue, index(>31)
    digital_bypass = [2, random.randint(1,1011), random.randint(0,1), random.randint(0,1), 32]
    #MitigationType, BeamDestination.id, BeamClass.id (oldValue), BeamClass.id (newValue), 0
    mitigation = [4, random.randint(1,4), random.randint(1,11), random.randint(1,11), 0]
    #DeviceInputType, DeviceInput.id, oldValue, newValue, 0
    device_input = [5, random.randint(1,1011), random.randint(0,1), random.randint(0,1), 0]
    #AnalogDeviceType, AnalogDevice.id, oldValue, newValue, 0
    analog = [6, random.choice(result), 0, 0, 0]
    test_data = [fault, fault_aux, analog_bypass, digital_bypass, mitigation, device_input, analog]
    pprint.pprint(test_data)
    return test_data

def create_bad_data():
    fault = [1, 23, 23, 23, 0]
    analog_bypass = [2, 434343, 4, 3, 4]
    digital_bypass = [2, 1012, 1, 1, 32]
    mitigation = [4, 5, 8, 8, 0]
    device_input = [5, 1012, 2, 1, 0]
    analog = [6, 34343, 3, 0, 0]
    random_data = [54, 3, 2, 3, 2]
    
    test_data = [fault, analog_bypass, digital_bypass, mitigation, device_input, analog, random_data]
    return test_data

def create_history_tables(tables, env, db_path):
    """
    Creates all tables to be used in the history database.
    Should not be called regularly.
    """
    try:
        history_engine = MPSConfig(db_file=env["file_names"]["history"], db_name="history", file_path=db_path).last_engine
        Base.metadata.create_all(history_engine, tables=tables)
    except:
         print("ERROR: Unable to create tables in mps_gun_history.db")
    return

def delete_history_db(tables, env, db_path):
    """
    Deletes all data in tables in the history database. 
    Note: Does not remove empty table definitions from db.
    """
    #Add function to delete all tables/rows
    try:
        meta = models.Base.metadata
        meta.bind = MPSConfig(db_file=env["file_names"]["history"], db_name="history", file_path=db_path).last_engine
        meta.drop_all(tables=tables)
    except exc.OperationalError as e:
        print("Database does not exist, cannot delete tables")
    return

if __name__ == "__main__":
    main()


