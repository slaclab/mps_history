
""" TEMP """
import struct

import inspect
print(inspect.getfile(MPSConfig))
print(inspect.getfile(models))

class Message(Structure):
    """
    Class responsible for defining messages coming from the Central Node IOCchart
    5 unsigned ints - 20 bytes of data

    type: 1-6 depending on the type of data to be processed
    id: the fault.id - This may be useless to send, as the old/new_value can grab the fault.id as it is a FK in fault_state table, instead use it to confirm it is matching with fault_state table.
    old_value, new_value: fault_state.id for old and new
    aux: auxillary data that may or may not be included, depending on type -  
        Expected data specifics will be specified in the processing functions
    """
    _fields_ = [
        ("type", c_uint),
        ("id", c_uint),
        ("old_value", c_uint),
        ("new_value", c_uint),
        ("aux", c_uint),
        ]
    
    def to_string(self):
        return str(self.type) + " " + str(self.id) + " " + str(self.old_value) + " " + str(self.new_value) + " " + str(self.aux) 
""" TEMP """

# Formalize this later - or just copy and paste this piece into init of historyBroker
def test_channel():
        message = Message(5, 600, 1, 0, 0)  # analog channel
        message = Message(5, 702, 1, 0, 17)  # digital channel
        message = Message(5, 220, 0, 0, 9)  # digital channel
        self.timestamp = str(datetime.now())
        """ <<<<< Once finished - Place this query block into process_channel() <<<<< """

        # TODO - Make function "process_channel"
        # this channel is determined by the message.new_state 
        # for the new_state and old_state ensure that if channel.type == digital, you query the o_name and z_name as whats passed in is either 1 or 0
        # 

        try:
            channel_id = self.conf_conn.session.query(models.FaultInput)\
                        .filter(models.FaultInput.fault_id==message.id)\
                        .first().channel_id
            print(channel_id)
            channel = self.conf_conn.session.query(models.Channel)\
                        .filter(models.Channel.id==channel_id)\
                        .first()
            print(channel.name)
            print(channel.number)
            print(channel.card_id)

            
            app_card = self.conf_conn.session.query(models.ApplicationCard)\
                        .filter(models.ApplicationCard.id==channel.card_id)\
                        .first()
            print(app_card)
            print(app_card.number)
            print(app_card.crate_id)
            crate_loc = self.conf_conn.session.query(models.Crate)\
                        .filter(models.Crate.id==app_card.crate_id)\
                        .first().location
            print(crate_loc)
            print(channel.discriminator)
            if channel.discriminator == 'digital_channel':
                digital_channel = self.conf_conn.session.query(models.DigitalChannel)\
                        .filter(models.DigitalChannel.id==channel_id)\
                        .first()
                print(digital_channel)
                old_state = digital_channel.z_name
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
        channel_info = {"type":"channel", "timestamp": self.timestamp, "old_state":old_state, "new_state":new_state, "channel_number":channel.number, "channel_name":channel.name,\
                        "card_number":app_card.number, "crate_loc":crate_loc}
        print(channel_info)
        #return channel_info

def test_fault():        
    message = Message(1, 140, 16, 3, 1063) # fault

    self.timestamp = str(datetime.now())
    """ <<<<< Once finished - Place this query block into process_fault() <<<<< """
    try:   
        fault = self.conf_conn.session.query(models.Fault)\
                .filter(models.Fault.id==message.id).first()
        print(fault)

        # Determine if active, the fault id and description(fault.name)
        fault_info = {"type":"fault", "timestamp": str(self.timestamp)}
        if message.new_value == 0:
            f_info = {"active":False, "fault_id":message.id, "fault_desc":("FAULT CLEARED - " + fault.name)}
        else:
            f_info = {"active":True, "fault_id":fault.id, "fault_desc":fault.name}
        fault_info.update(f_info)
        # Determine the new and old fault state names
        old_state = self.get_fault_state_from_fault(message.old_value)
        new_state = self.get_fault_state_from_fault(message.new_value)
        
        print(old_state)
        print(new_state)

        # 1) using the fault_state.id from new_state, it has many mitigation_id
        # 2) each mitigation_id has only 1 beam_destination_id and 1 beam_class_id
        mitigation_ids = self.conf_conn.session.query(models.fault_state.association_table.c.mitigation_id)\
                        .filter(models.fault_state.association_table.c.fault_state_id==message.new_value)\
                        .all()
        print(mitigation_ids)
        mitigation_ids = [*set([mitigation_id[0] for mitigation_id in mitigation_ids])] # remove possible duplicates, Change from tuple "(1,)"" to int "1"
        print(mitigation_ids)

        beams = []
        # Determine the beam class and destinations
        # SELECT name instead of SELECT * for performance. 
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
            beams.append({beam_class, beam_dest})
        print(beams)
        if None in [beam_dest, beam_class, old_state, new_state]:
            print([beam_dest, beam_class, fault, old_state, new_state])
            raise
        f_info = {"old_state":old_state, "new_state":new_state, "beams": beams}
        fault_info.update(f_info)

    except Exception as e:
        self.logger.log("SESSION ERROR: Add Fault ", message.to_string())
        print(traceback.format_exc())
    print(fault_info)
    return
    return fault_info

def test_bypass():
    message = Message(2, 378, 0, 10, 50)  # bypass
    self.timestamp = datetime.now()
    print(self.timestamp)
    """ <<<<< Once finished - Place this query block into process_bypass() <<<<< """
    """
    Adds an analog or digital device bypass into the history database.
    Params:
        message: [type(of message), id, oldvalue, newvalue, aux(expiration time in secs)]        
    Output:
        bypass_info: ['type': 'bypass', 'timestamp', str, 'new_state': str, 'expiration': str, 'description': str]
    """
    # we only care about new state, so leave old_state empty
    # aux is the bypass expiration in seconds
    # so add expiration + now() and convert to datetime obj (to get the exact time it expires)
    
    # convert current_timestamp to secs
    timestamp_secs = int(self.timestamp.strftime("%s"))
    print("timestamp_secs =", timestamp_secs)
    expiration = datetime.fromtimestamp(message.aux + timestamp_secs).strftime("%Y-%m-%d %H:%M:%S.%f")
    print("expiration =", expiration)

    new_state = self.get_fault_state_from_fault(message.new_value)
    print(new_state)
    try:
        fault_name = self.conf_conn.session.query(models.Fault.name)\
                    .filter(models.Fault.id==message.id).first()[0]
    except:
        self.logger.log("SESSION ERROR: Add Bypass ", message.to_string())
        return
    # channel is the same as bypass_id in this situation
    bypass_info = {"type":"bypass", "timestamp": str(self.timestamp), "new_state":new_state, "expiration":expiration, "description":fault_name}
    print(bypass_info)
    return bypass_info

    """ TEMP """       