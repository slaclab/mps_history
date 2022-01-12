import config, traceback, pprint

from mps_history.tools import logger
from mps_database.mps_config import MPSConfig, models


from mps_history.models import fault_history, analog_history, bypass_history, input_history
from sqlalchemy import insert, select


class HistorySession():
    def __init__(self, dev=None):
        self.dev = dev
        self.history_conn = None
        self.conf_conn = None
        print("dev is ", dev)
        self.logger = logger.Logger(stdout=True, dev=dev)

        if self.dev:
            self.default_dbs = config.db_info["lcls-dev3"]
        else:
            self.default_dbs = config.db_info["test"]
        print("Dev is:", dev)
        print(self.default_dbs)

        self.connect_conf_db()
        self.connect_hist_db()

        self.logger.log("LOG: History Session Created")

    def execute_commit(self, to_execute):
        """
        Executes a supplied sql statement in the history database

        Params:
            to_exectue: SQL query to be run through the sqlalchemy history db session/connection
        """
        self.history_conn.session.execute(to_execute)
        self.history_conn.session.commit()
        return
    
    # For all add_xxxx functions, the message format is: [type, id, oldvalue, newvalue, aux(devicestate)]

    def add_fault(self, fault_info):
        """
        Adds a single fault to the fault_history table in the history database
        Adds in the fault description, "inactive"/"active" for the state changes, and the device state name

        Params:
            message: [type(of message), id, old_value, new_value, aux(allowed_class)]
        """
        fault_insert = fault_history.FaultHistory.__table__.insert().values(fault_id=fault_info["fid"], fault_desc=fault_info["fdesc"], old_state=fault_info["old_state"], new_state=fault_info["new_state"], beam_class=fault_info["beam_class"], beam_destination=fault_info["beam_destination"], active=fault_info["active"])
        self.execute_commit(fault_insert)
        return
    
    def set_faults_inactive(self, fid):
        #Look up latest fault with this fault id, set active to inactive
        faults = self.history_conn.session.query(fault_history.FaultHistory).filter(fault_history.FaultHistory.fault_id==fid).filter(fault_history.FaultHistory.active==True).all()
        for fault in faults:
            fault.active = False
            self.history_conn.session.commit()
            print("fault ", fault, fault.id, fault.active)
        return 

    def determine_device_from_fault(self, fstate_id):
        """
        Returns the device state based off of the fault state id
        """
        if fstate_id == 0:
            return "None"
        fault_state = self.conf_conn.session.query(models.FaultState).filter(models.FaultState.id==fstate_id).first()
        device_state = self.conf_conn.session.query(models.DeviceState).filter(models.DeviceState.id==fault_state.device_state_id).first()
        return device_state.name

    def determine_thresholds(self, bits):
        thresholds = ''
        for count, bit in enumerate(str(bin(bits)[::-1])):
            if bit == "1":
                thresholds += ("threshold " + str(count+1) + ",")
        return thresholds[:-1]

    def add_analog(self, ana_info):
        """
        Adds an analog device update into the history database
        Adds in the device channel name, and hex values of the new and old state changes
        
        Params:
            message: [type(of message), id, old_value, new_value, aux]
        """
        analog_insert = analog_history.AnalogHistory.__table__.insert().values(channel=ana_info["channel"], device=ana_info["device"], old_state=ana_info["old_state"], new_state=ana_info["new_state"])
        self.execute_commit(analog_insert)
        return

    def add_bypass(self, bypass_info):
        """
        Adds an analog or digital device bypass into the history database.
        Adds in the device channel name, "active"/"expired" for the state change, and if analog, the integrator auxillary data
        
        Params:
            message: [type(of message), id, oldvalue, newvalue, aux(digital vs analog)]        
        """
        bypass_insert = bypass_history.BypassHistory.__table__.insert().values(bypass_id=bypass_info["channel"], new_state=bypass_info["new_state"], old_state=bypass_info["old_state"], integrator=bypass_info["integrator"])
        self.execute_commit(bypass_insert)
        return
    
    def add_input(self, message):
        """
        Adds a device input into the history database
        Adds in digital channel name, the digital device name, and the names of the new and old digital channels based on their 0/1 values 
        
        Params:
            message: [type(of message), id, oldvalue, newvalue, aux(allowed_class)]        
        """
        try:
            device_input = self.conf_conn.session.query(models.DeviceInput).filter(models.DeviceInput.id==message.id).first()
            channel = self.conf_conn.session.query(models.DigitalChannel).filter(models.DigitalChannel.id==device_input.channel_id).first()   
            digital_device = self.conf_conn.session.query(models.DigitalDevice).filter(models.DigitalDevice.id==device_input.digital_device_id).first()
            
            device = self.conf_conn.session.query(models.Device).filter(models.Device.id==digital_device.id).first()

            if None in [device_input, device, channel]:
                print([device_input, device, channel])
                raise
        except:
            self.logger.log("SESSION ERROR: Add Device Input ", message.to_string())
            print(traceback.format_exc())
            return
        old_name = channel.z_name
        new_name = channel.z_name
        if (message.old_value > 0):
            old_name = channel.o_name
        if (message.new_value > 0):
            new_name = channel.o_name

        input_insert = input_history.InputHistory.__table__.insert().values(new_state=new_name, old_state=old_name, channel=channel.name, device=digital_device.name)
        self.execute_commit(input_insert)
        return 

    def get_fault_log(self, num_faults=10):
        """
        Gets the specified number of recent fault log entries from the history database. Default is 10 entries.

        Params:
            num_faults: (int) Number of fault entries to pull from the database, starting with the most recent. 
        """
        results = self.history_conn.session.query(fault_history.FaultHistory).order_by(fault_history.FaultHistory.timestamp.desc()).limit(num_faults).all()
        return results

    def get_active_faults(self, num_faults=10):
        results = self.history_conn.session.query(fault_history.FaultHistory).filter(fault_history.FaultHistory.active==True).order_by(fault_history.FaultHistory.timestamp.desc()).limit(num_faults).all()
        return results

    def get_all_faults_by_id(self, fault_id):
        """
        Gets all fault entries in the history database based from their fault_id

        Params:
            fault_id
        """
        print("Selecting entries ", fault_id)
        stmt = select(fault_history.FaultHistory.timestamp).where(fault_history.FaultHistory.fault_id == fault_id)
        result = self.history_conn.session.execute(stmt)
        return result.fetchall()

    def get_entry_by_id(self, fault_id):
        """
        Gets a single fault entry from history database based on its unique id
        """
        stmt = select(fault_history.FaultHistory.timestamp).where(fault_history.FaultHistory.id == fault_id)
        result = self.history_conn.session.execute(stmt)
        return result.fetchone()

    def get_config_fault_info(self, fault_id):
        """
        Gets some descriptive information of one fault from the configuration database based on fault id
        """
        stmt = select(models.Fault.id, models.Fault.name, models.Fault.description).where(models.Fault.id == fault_id)
        result = self.conf_conn.session.execute(stmt)
        return result
     
    def connect_hist_db(self):
        """
        Creates a interactable connection to the history database
        """
        db_file = self.default_dbs["file_names"]["history"]
        try:
            self.history_conn = MPSConfig(db_name="history", db_file=db_file, file_path=self.default_dbs["file_paths"]["history"])
        except:
            self.logger.log("DB ERROR: Unable to Connect to Database ", str(db_file))
        return

    def connect_conf_db(self):
        """
        Creates a interactable connection to the configuration database
        """
        #TODO: add cli args later
        db_file = self.default_dbs["file_names"]["config"]
        try:
            self.conf_conn = MPSConfig(db_name="config", db_file=db_file, file_path=self.default_dbs["file_paths"]["config"])
        except:
            self.logger.log("DB ERROR: Unable to Connect to Database ", str(db_file))
        return
    
def main():
    history = HistorySession()
    return


if __name__ == "__main__":
    main()
