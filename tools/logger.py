import datetime, errno, os
from threading import Lock

class Logger:
    def __init__(self, filename=None, stdout=False):
        self.log_file_lock = Lock()
        self.spacer = "  |  "

        if filename:
            self.filename = filename
        else:
            dev = False
            #dir_name = os.path.dirname(self.log_file_name)
            if dev:
                base_name = "/u/cd/lking/workspace/mps_logs"
                #base_name = "/u1/lcls/physics/mps_database/mps_database" 
            else:
                base_name = "/Users/lking/Documents/Projects/mps_database/test_logs/mps_database"
            # TODO: commented out for testing
            self.filename = '{}-{}'.format(base_name, datetime.datetime.now().strftime('%Y.%m.%d %H:%M:%S'))  
        self.stdout = stdout
        self.connect_file()
        
    def connect_file(self):
        try:
            self.log_file = open(self.filename, 'a')
        except IOError as e:
            if e.errno == errno.EACCES:
                print('ERROR: No permission to write file {}'.format(self.filename))
            else:
                print('ERROR: errno={}, cannot write to file {}'.format(e.errno, self.filename))
            exit(1)
        return 

    def log(self, message, data=""):
        printable = message + self.spacer + data
        self.log_file_lock.acquire()
        if self.filename != None:
            self.log_file.write('[{}] {}\n'.format(datetime.datetime.now().strftime('%Y.%m.%d %H:%M:%S'),
                                                str(printable)))
            
        if self.stdout:
            print('[{}] {}'.format(datetime.datetime.now().strftime('%Y.%m.%d %H:%M:%S'),
                                    str(printable)))
        self.log_file_lock.release()
        return