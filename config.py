db_info  = {
    "container-dev":{  
        "file_paths":{
            "config":"/afs/slac/g/lcls/physics/mps_configuration/current",
            "runtime":None
        },
        "file_names":{
            "config":"mps_config-9999-99-99-z.db",
            "history":"mps_gun_history_7_12_23.db",
            "runtime":None
        },
        "logger":{
            "log_directory":"/app/test_logs"
        }
    },
    "dev-srv09":{
        "file_paths":{
            "config":"/afs/slac/g/lcls/physics/mps_configuration/current",
            # "config":"/sdf/home/p/pnispero/mps/mps_history/mps_configuration",
            "history":"/sdf/home/p/pnispero/mps/mps_history",
            "runtime":"/u1/lcls/physics/mps_manager"
        },
        "file_names":{
            "config":"mps_config-9999-99-99-z.db",
            "history":"mps_gun_history_7_12_23.db",
            "runtime":None
        },
        "logger":{
            "log_directory":"/sdf/home/p/pnispero/mps/mps_history/test_logs/"
        },
        "kafka":{
            "producer_config": {
                "bootstrap.servers": "172.24.5.197:9094",
                "security.protocol": "SASL_PLAINTEXT",
                "sasl.username": "mps-data-injestion-publisher",
                "sasl.password": "H9MD7vxf9ABPDsKTyxvOtTKL14hCSU8R",
                "sasl.mechanism": "SCRAM-SHA-512" 
            },
            "ip": "172.24.5.197:9094",
            "topic": "mps-data-injestion",
            "history_schema" : """
                                {
                                    "id": 1,
                                    "type": "",
                                    "timestamp": "",
                                    "old_state": "",
                                    "new_state": "",
                                    "channel": {        
                                        "number": 1,
                                        "name": "",
                                        "card_number": 1,
                                        "crate_loc": ""
                                    },
                                    "bypass": {
                                        "expiration": "",
                                        "description": ""
                                    },
                                    "fault": {
                                        "id": 1,
                                        "description": "",
                                        "beams": [
                                            {
                                                "class": "",
                                                "destination": ""
                                            }
                                        ],
                                        "active": true
                                    }
                                }
                                """
        }
        # lking dev paths
        # "file_paths":{
        #     #"config":"/afs/slac/g/lcls/physics/mps_configuration/current",
        #     "config":"/afs/slac/g/lcls/physics/mps_configuration/2022-03-21-a",
        #     "history":"/u/cd/lking/mps/mps_history",
        #     "runtime":"/u1/lcls/physics/mps_manager"
        # },
        # "file_names":{
        #     "config":"mps_config-2022-03-21-a.db",
        #     "history":"mps_gun_history.db",
        #     "runtime":None
        # },
        # "logger":{
        #     "log_directory":"/u/cd/lking/mps/mps_logs/mps_history"
        # }
    },
    "dev-rhel7":{
        "file_paths":{
            #"config":"/afs/slac/g/lcls/physics/mps_configuration/current",
            "config":"/sdf/home/p/pnispero/mps/mps_history/mps_configuration",
            "history":"/sdf/home/p/pnispero/mps/mps_history",
            "runtime":"/u1/lcls/physics/mps_manager"
        },
        "file_names":{
            "config":"test.db", #"mps_config-2023-05-22-a.db",
            "history":"mps_gun_history_7_12_23.db",
            "runtime":None
        },
        "logger":{
            "log_directory":"/sdf/home/p/pnispero/mps/mps_history/test_logs/"
        },
        "kafka":{
            "producer_config": {
                "bootstrap.servers": "172.24.5.197:9094",
                "security.protocol": "SASL_PLAINTEXT",
                "sasl.username": "mps-data-injestion-publisher",
                "sasl.password": "H9MD7vxf9ABPDsKTyxvOtTKL14hCSU8R",
                "sasl.mechanism": "SCRAM-SHA-512" 
            },
            "ip": "172.24.5.197:9094",
            "topic": "mps-data-injestion",
            "history_schema" : """
                                {
                                    "id": 1,
                                    "type": "",
                                    "timestamp": "",
                                    "old_state": "",
                                    "new_state": "",
                                    "channel": {        
                                        "number": 1,
                                        "name": "",
                                        "card_number": 1,
                                        "crate_loc": ""
                                    },
                                    "bypass": {
                                        "expiration": "",
                                        "description": ""
                                    },
                                    "fault": {
                                        "id": 1,
                                        "description": "",
                                        "beams": [
                                            {
                                                "class": "",
                                                "destination": ""
                                            }
                                        ],
                                        "active": true
                                    }
                                }
                                """
        }
    },
    "test":{  # My local pc paths
        "file_paths":{
            "config":"/home/pnispero/mps_history/mps_configuration",
            "history":"/home/pnispero/mps_history",
            "runtime":None
        },
        "file_names":{
            "config":"test.db",
            "history":"mps_gun_history_7_12_23.db",
            "runtime":None
        },
        "logger":{
            "log_directory":"/home/pnispero/mps_history/test_logs/"
        }
    },
    "prod":
    {
        "file_paths":{
            "config":"/usr/local/lcls/physics/mps_configuration/current",
            "history":"/u1/lcls/tools/mpsHistoryServer/mps_history_server2",
            "runtime":""
        },
        "file_names":{
            "config":"mps_config-2022-03-21-a.db",
            "history":"mps_history.db",
            "runtime":None
        },
        "logger":{
            "log_directory":"/u1/lcls/tools/mpsHistoryServer/mps_history_server2/logs"
        },
        "kafka":{
            "producer_config": {
                "bootstrap_server_ip": "172.24.5.197:9094",
                "username": "mps-data-injestion-publisher",
                "password": "H9MD7vxf9ABPDsKTyxvOtTKL14hCSU8R",
                "security_protocol": "SASL_SSL",
                "sasl_mechanism": "PLAIN"
            },
            "topic": "mps-data-injestion"
        }
    },

}