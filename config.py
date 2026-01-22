# NOTE - This file is really only used for simulated data client.py
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
    "mccas0":
    { # TEMP set config to new mps db
        "file_paths":{
            "config":"/usr/local/lcls/physics/mps_configuration/9999-99-99-z.db",
            # "config":"/usr/local/lcls/physics/mps_configuration/current",
            "history":"/u1/lcls/tools/mpsHistoryServer/mps_history_server2",
            "runtime":""
        },
        "file_names":{
            "config":"mps_config-9999-99-99-z.db",
            "history":"mps_history.db",
            "runtime":None
        },
        "logger":{
            "log_directory":"/u1/lcls/tools/mpsHistoryServer/mps_history_server2/logs"
        }
    },

}