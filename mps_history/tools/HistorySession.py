import config, traceback, pprint

from mps_history.tools import logger, HistoryAPI


class HistorySession():
    def __init__(self, dev=None):
        self.dev = dev
        print("dev is ", dev)
        self.logger = logger.Logger(stdout=True, dev=dev)

        self.history_api = None
        self.connect_hist_api()

        print("Dev is:", dev)

        self.logger.log("LOG: History Session Created")
    
    # For all add_xxxx functions, the message format is: [type, id, oldvalue, newvalue, aux(devicestate)]
     
    def connect_hist_api(self):
        """
        Connects to the api for the history database
        """
        try:
            self.history_api = HistoryAPI.HistoryAPI(dev=self.dev)
        except:
            self.logger.log("DB ERROR: Unable to Connect to History API")

    def receive_data(self, data):
        if data["type"] == "analog":
            self.history_api.add_analog(data)
        elif data["type"] == "bypass":
            self.history_api.add_bypass(data)
        elif data["type"] == "fault":
            self.history_api.add_fault(data)
        elif data["type"] == "input":
            self.history_api.add_input(data)
        return

"""
def main():
    history = HistorySession()
    return


if __name__ == "__main__":
    main()
"""
