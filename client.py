from io import DEFAULT_BUFFER_SIZE
import sqlalchemy

""" TEMP """
# Forced config mps_database to point to the new_mpsdb 
import sys
# caution: path[0] is reserved for script path (or '' in REPL)
# sys.path.insert(1, '/sdf/home/p/pnispero/mps/mps_database_new')
sys.path.insert(1, '/home/pnispero/mps_history/mps_database/')
""" TEMP """

from mps_database import mps_config, models
from mps_processor.HistoryMessageType import HistoryMessageType

import config

from mps_database.mps_config import MPSConfig
from sqlalchemy import select, exc

from ctypes import *

import socket, random, pprint, struct
from datetime import datetime
""" TEMP """
import time
""" TEMP """

def main():
    """
    Main function responsible for calling whatever tools functions you need. 
    """
    #dev should be changed to True if being run on dev-srv09
    dev = True
    prod = False
    #restart is True if you want tables to be wiped and recreated 
    #THIS DELETES THE CONFIG TABLE SOMEHOW
    restart = False

    if dev:
        env = config.db_info["dev-srv09"]
        host = "dev-srv09"
    elif prod:
        env = config.db_info["mccas0"]
        host = "mccas0"
    else:
        env = config.db_info["test"]
        host = '127.0.0.1'
    db_path = env["file_paths"]["history"]

    conf_conn = MPSConfig(config.db_info[host]["file_paths"]["config"] + '/' + config.db_info[host]["file_names"]["config"]) # connect to config db

    """ TEMP """
    create_socket(host, env, conf_conn)
    return
    """ TEMP """

    if restart:
        tables = [analog_history.AnalogHistory.__table__, bypass_history.BypassHistory.__table__, fault_history.FaultHistory.__table__, input_history.InputHistory.__table__]
        #db_url = "sqlite:///{path_to_db}".format(path_to_db=db_path)
        #delete_history_db(tables, env, db_path=db_path)
        create_history_tables(tables, env, db_path=db_path)
    create_socket(host, env)
    return

def create_socket(host, env, conf_conn):
    """
    Acts as a client to connect to HistoryServer backend. 

    Creates a socket and sends over generated test insert data.
    """
    port = 3356
    num_test = 1
    
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect((host, port))
        """ TEMP """
        print(host)
        print(port)
        print("connected to socket")
        cur_time = int(datetime.now().strftime("%s"))
        print(cur_time)

        def send(data_set, gap_s):
            for data in data_set:
                s.sendall(struct.pack('5I', *data))
                time.sleep(gap_s)

        # IDs are from mps_config-9999-99-99-z.db
        # Fault 5 = LN49 (SIOC GUNB MP02) Alive: fault states 20 = Is Faulted, 21 = Is Ok
        # Fault 6 = SOL1B (SOLN:GUNB:212) Temperature Interlock: fault states 22 = Is Faulted, 23 = Is Ok
        # Channel 133 = SIOC:GUNB:MP02:HEARTBEAT (digital), channel 1 = SOLN:GUNB:212:I0_BACT (analog)
        # Application card 1 = card number 1, crate L2KA00-0517
        fault_type = HistoryMessageType.FaultStateType.value
        digital_type = HistoryMessageType.DigitalChannelType.value
        analog_type = HistoryMessageType.AnalogChannelType.value

        # Expect at ~20 s: 1 fault summary (5 transitions), 1 channel summary (5 transitions)
        repeated = [[fault_type, 5, 21, 20, 0], [digital_type, 133, 1, 0, 0],
                    [fault_type, 5, 20, 21, 0], [digital_type, 133, 0, 1, 0],
                    [fault_type, 5, 21, 20, 0], [digital_type, 133, 1, 0, 0],
                    [fault_type, 5, 20, 21, 0], [digital_type, 133, 0, 1, 0],
                    [fault_type, 5, 21, 20, 0], [digital_type, 133, 1, 0, 0]]
        # Expect at ~20 s: 1 normal fault entry, 1 normal channel entry
        single = [[fault_type, 6, 23, 22, 0],
                  [analog_type, 1, 0, 1, 0]]
        # Each bypass expires on its own (app card at 4 s, analog at 7 s, digital at 10 s), and its expired
        # message is sent at that expiration time. Expect each entry immediately as it arrives (6 normal entries).
        # [bypass type, id, old, new], seconds until it expires, expired message
        bypass_schedule = [
            ([HistoryMessageType.BypassApplicationType.value, 1, 0, 1], 4,
             [HistoryMessageType.BypassExpiredApplicationType.value, 1, 0, 1, 0]),
            ([HistoryMessageType.BypassAnalogType.value, 6, 1, 0], 7,
             [HistoryMessageType.BypassExpiredFaultType.value, 6, 0, 1, 0]),
            ([HistoryMessageType.BypassDigitalType.value, 5, 20, 21], 10,
             [HistoryMessageType.BypassExpiredFaultType.value, 5, 0, 1, 0]),
        ]
        # Sent 25 s after fault 5's first event, so it opens a new window instead of extending the old one.
        # Expect at ~45 s: 1 normal fault entry
        after_window = [[fault_type, 5, 20, 21, 0]]

        start = time.time()
        send(repeated, 1.1)
        send(single, 0.000001)

        bypass_time = int(time.time())
        send([bypass + [bypass_time + expires_in] for bypass, expires_in, _ in bypass_schedule], 0.000001)
        for _, expires_in, expired in bypass_schedule:
            time.sleep(max(0, bypass_time + expires_in - time.time()))
            print(f"bypass expired after {expires_in} s")
            send([expired], 0.000001)

        print("waiting until the first window has closed")
        time.sleep(max(0, start + 25 - time.time()))
        send(after_window, 0.000001)
        print("done, expect 11 ELOG entries (2 summaries, 9 normal)")

        return """ TEMP"""

        # send in 1000 packets, and calculate the time it takes - the generate_test_data doesnt work for new config db
        # TODO - Remake the generate_test_data for new config DB
        time_begin = time()
        for i in range(1): # each iteration sends 8 packets so 125 * 8 = 1000 packets
            for data in generate_test_data(env, conf_conn): # generates 8 sets of data
                #print(data)
                s.sendall(struct.pack('5I', data[0], data[1], data[2], data[3], data[4]))

        time_end = time()
        print("Time elapsed: ", end="")
        print(time_end - time_begin)
        return
        """ TEMP """
        # TODO: remove test data from this function
        curr = 0
        while curr < num_test:
            for data in generate_test_data(env):
                print(data)
                s.sendall(struct.pack('5I', data[0], data[1], data[2], data[3], data[4]))
            curr +=1 
        #for data in create_bad_data():
            #s.sendall(struct.pack('5I', data[0], data[1], data[2], data[3], data[4]))

    return

def generate_test_data(env, conf_conn):
    """
    Generates a suite of realistic test data for entering into the history db.

    Type number 3 is skipped because it is defined as "BypassValueType" in the central node ioc, and does not appear to be relevant
    """
    generate_time_begin = time()
    filename = env["file_paths"]["config"] + "/" + env["file_names"]["config"]
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
    analog = [6, random.choice(analog), 0, 0, 0]

    #test_data = [fault_all, analog_bypass, digital_bypass, device_input, analog]
    test_data = [fault_init, fault_all, fault_clear, active_fault, analog_bypass, digital_bypass, device_input, analog]
    generate_time_end = time()
    #print("Generate Data Time elapsed: ", end="")
    #print(generate_time_end - generate_time_begin)
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


