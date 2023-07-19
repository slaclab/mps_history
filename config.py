db_info  = {
    "dev-rhel7":{
        "file_paths":{
            #"config":"/afs/slac/g/lcls/physics/mps_configuration/current",
            "config":"/u/cd/pnispero/mps/mps_history/mps_configuration",
            "history":"/u/cd/pnispero/mps/mps_history",
            "runtime":"/u1/lcls/physics/mps_manager"
        },
        "file_names":{
            "config":"test.db", #"mps_config-2023-05-22-a.db",
            "history":"mps_gun_history_7_12_23.db",
            "runtime":None
        },
        "logger":{
            "log_directory":"/u/cd/pnispero/mps/mps_history/test_logs/"
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
    "test":{ 
        "file_paths":{
            "config":"/u/cd/pnispero/mps/mps_history/mps_configuration",
            "history":"/u/cd/pnispero/mps/mps_history",
            "runtime":None
        },
        "file_names":{
            "config":"mps_config-2023-05-22-a.db",
            "history":"mps_gun_history_7_12_23.db",
            "runtime":None
        },
        "logger":{
            "log_directory":"/u/cd/pnispero/mps/mps_history/test_logs/"
        }
        # lking filepaths
        # "file_paths":{
        #     "config":"/Users/lking/Documents/Projects/mps_database/mps_database",
        #     "history":"/Users/lking/Documents/Projects/mps_database/mps_database",
        #     "runtime":None
        # },
        # "file_names":{
        #     "config":"mps_config_imported.db",
        #     "history":"mps_gun_history.db",
        #     "runtime":None
        # },
        # "logger":{
        #     "log_directory":"/Users/lking/Documents/Projects/mps_database/test_logs/mps_history-"
        # }
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
        }
    },

}