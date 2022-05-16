from io import DEFAULT_BUFFER_SIZE
import sqlalchemy
from mps_database import mps_config, models

import config
from mps_history.tools import HistorySession
from mps_history.models import analog_history, bypass_history, input_history, fault_history
from mps_database.models import Base

from mps_database.mps_config import MPSConfig
from sqlalchemy import select, exc

from ctypes import *

import socket, random, pprint, struct


def main():
    """
    Main function responsible for calling whatever tools functions you need. 
    """
    #dev should be changed to True if being run on lcls-dev3
    dev = False
    #restart is True if you want tables to be wiped and recreated 
    #THIS DELETES THE CONFIG TABLE SOMEHOW
    restart = False

    if dev:
        env = config.db_info["lcls-dev3"]
        host = "lcls-dev3"
    else:
        env = config.db_info["test"]
        host = '127.0.0.1'
    db_path = env["file_paths"]["history"]

    if restart:
        tables = [analog_history.AnalogHistory.__table__, bypass_history.BypassHistory.__table__, fault_history.FaultHistory.__table__, input_history.InputHistory.__table__]
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
    num_test = 1
    
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect((host, port))
        # TODO: remove test data from this function
        curr = 0
        while curr < num_test:
            for data in generate_test_data(env):
                s.sendall(struct.pack('5I', data[0], data[1], data[2], data[3], data[4]))
            curr +=1 
        #for data in create_bad_data():
            #s.sendall(struct.pack('5I', data[0], data[1], data[2], data[3], data[4]))

    return

def generate_test_data(env):
    """
    Generates a suite of realistic test data for entering into the history db.

    Type number 3 is skipped because it is defined as "BypassValueType" in the central node ioc, and does not appear to be relevant
    """
    filename = env["file_paths"]["config"] + "/" + env["file_names"]["config"]
    print("FINAL ", filename)
    #conf_conn = MPSConfig(filename=filename)
    conf_conn = MPSConfig()
    ad_select = select(models.AnalogDevice.id)
    ad_result = conf_conn.session.execute(ad_select)
    result = [r[0] for r in ad_result]

    ac_select = select(models.AllowedClass.id)
    ac_result = conf_conn.session.execute(ac_select)
    ac = [r[0] for r in ac_result]

    f_select = select(models.Fault.id)
    f_res = conf_conn.session.execute(f_select)
    f = [r[0] for r in f_res]

    analog_select = select(models.AnalogDevice.id)
    an_res = conf_conn.session.execute(analog_select)
    analog = [r[0] for r in an_res]

    device_select = select(models.DeviceInput.id)
    dev_res = conf_conn.session.execute(device_select)
    device = [r[0] for r in dev_res]
    #type, fault.id, old_val, new_val, DeviceState.id(opt)
    """
    Orig faults
    fault = [1, random.randint(1,2144), random.randint(0,1), random.randint(0,1), 0]
    fault_aux = [1, random.randint(1,2144), random.randint(0,1), random.randint(0,1), random.randint(1, 79)]
    fault = [1, random.randint(1,3), random.randint(0,1), random.randint(0,1), 0]
    """
    #FaultType, Fault.id, FaultState.id, FaultState.id, AllowedClass.id
    this_fault = random.choice(f)
    this_bc = random.randint(1, 20)
    second_bc = random.randint(1,20)
    #set fault
    fault_init = [1, this_fault, 0, this_bc, random.choice(ac)]
    #more restrictive
    fault_all = [1, this_fault, this_bc, second_bc, random.choice(ac)]
    #clear fault
    fault_clear = [1, this_fault, second_bc, 0, 0]
    
    active_fault = [1, random.choice(f), random.randint(1,20), random.randint(1,20), random.choice(ac)]

    #BypassStateType, AnalogDevice.id, oldValue, newValue, 0-31
    analog_bypass = [2, random.choice(analog), random.randint(0,1), random.randint(0,1), random.randint(0, 31)]
    #BypassStateType, DeviceInput.id, oldValue, newValue, index(>31)
    digital_bypass = [2, random.choice(device), random.randint(0,1), random.randint(0,1), 32]
    #DeviceInputType, DeviceInput.id, oldValue, newValue, 0
    device_input = [5, random.choice(device), random.randint(0,1), random.randint(0,1), 0]

    #AnalogDeviceType, AnalogDevice.id, oldValue, newValue, 0
    analog = [6, analog, 0, 0, 0]

    #test_data = [fault_all, analog_bypass, digital_bypass, device_input, analog]
    test_data = [fault_init, fault_all, fault_clear, active_fault, analog_bypass, digital_bypass, device_input, analog]
    return test_data

def create_bad_data():
    fault = [1, 23, 23, 23, 0]
    analog_bypass = [2, 434343, 4, 3, 4]
    digital_bypass = [2, 1012, 1, 1, 32]
    device_input = [5, 1012, 2, 1, 0]
    analog = [6, 34343, 3, 0, 0]
    random_data = [54, 3, 2, 3, 2]
    
    test_data = [fault, analog_bypass, digital_bypass, device_input, analog, random_data]
    return test_data

def create_history_tables(tables, env, db_path):
    """
    Creates all tables to be used in the history database.
    Should not be called regularly.
    """
    try:
        filename = db_path + env["file_names"]["history"]
        history_engine = MPSConfig(filename=filename).engine
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
        filename = db_path + env["file_names"]["history"]
        meta.bind = MPSConfig(filename=filename).engine
        meta.drop_all(tables=tables)
    except exc.OperationalError as e:
        print("Database does not exist, cannot delete tables")
    return

if __name__ == "__main__":
    main()


