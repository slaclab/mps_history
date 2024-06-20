# MPS History Server

## Running the Server
Run the history server with the command:  
`./HistoryServer.sh` 
There should be support for starting in various environments including local, dev, and production. However, this file can be edited to include other environments and parameters as the program changes. 

## Optional Client
### Testing
Included with the history server is a client that can be used for testing the server data flow with semi-realistic data. In this client, a connection to a configuration database is established through the MPS_Config class within the [MPS_Database](https://github.com/slaclab/mps_database/blob/master/mps_database/mps_config.py) module. Then, the appropriate data type(device, channel, etc.) is selected at random, packaged into a struct, and sent over a socket connection via local host. This is repeated multiple times for various different data types supported by the History Server.
### Database Creation/Reset
There is also commented out functionality for creating and resetting the initial History Server Database with the appropriate table schema. 

## Configuration File
The configuration file is responsible for including the needed filenames and paths for logging, and the configuration and history databases. There is separate sections for different environments, and can be edited to include more environments if needed. 
