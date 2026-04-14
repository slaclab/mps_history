# MPS History Collector
A barebones receiver of data from the mps central nodes through UDP. 
Then sends the raw data directly to the kafka message brokers of the ELOG. 
Where it will later be processed and written to the ELOG database.

## UDP Socket
As of writing, the socket buffer size default and limit is 212992 (~208KB)
`$ cat /proc/sys/net/core/rmem_max`
212992
`$ cat /proc/sys/net/core/rmem_default`
212992

## Data streaming requirements
1. Message size is 20 bytes (5 ints): 
```
  HistoryMessageType type; // Enumerated value
  uint32_t id;        // MPS database ID for the Fault/Input/Mitigation
  uint32_t oldValue;
  uint32_t newValue;
  uint32_t aux;
```
2. Maximum send rate from MPS Central Nodes = 360hz
And if theres 3 central nodes, then 360*3 = 1,080 messages/sec
3. Total maxmium worse case rate: 1,080 messages/sec * 20 bytes/message = 21,600 bytes/sec (~21KB/s)
4. Buffer can hold 212,992 bytes / 21,600 bytes/sec = ~9.9 secs worth of maximum message rate.
This should be plenty. And since we can expect this program to write the data quickly to the kafka message broker, then the buffer is likely to not fill up. 

### Installing librdkafka dependency locally (Build from source)
Download the preferred version into local dir
1. `mkdir ~/librdkafka && cd ~/librdkafka`
1. `curl -L https://github.com/confluentinc/librdkafka/archive/refs/tags/v2.8.0.tar.gz > kafka.tar.gz`
2. `tar -xzf kafka.tar.gz`
3. `cd librdkafka-2.8.0/`

Build
1. `./configure --prefix=$HOME/librdkafka --enable-ssl`
The prefix specifies the base directory where the library will be installed. Default is usually "/usr/local", which we want to avoid. And adds --enable-ssl adds SASL SCRAM support
2. `make`
3. `make install`
Then confirm the lib, and include are installed. 
Ex: `$ cd ../ && ls`
`include  kafka.tar.gz  lib  librdkafka-2.8.0  share`

Linking
1. Once you're able to install the library, then we want to link it to the mps collector. Thats already done in the Makefile. 

## Development
1. Must link to this library if you want to build the app: https://github.com/confluentinc/librdkafka
2. Use the makefile. at the top of the directory
`make`
`make debug` - this provides some debug messages
3. Note - May need to update to latest mps_database, but for now it is working with the existing logic.The mps_database in this repo is taken from here:

```
[pnispero@lcls-dev3 mps_database]$ git log -n 1
commit 954cca5f6c0334d847d9846ac132ce2feea38c7c
Author: Jeremy Mock <jeremy.a.mock@gmail.com>
Date:   Tue Jul 4 13:29:47 2023 -0700

    get rid of runtime database
[pnispero@lcls-dev3 mps_database]$ pwd
/sdf/home/p/pnispero/afs_stuff/pnispero/mps/mps_database_new/mps_database
[pnispero@lcls-dev3 mps_database]$ git remote -v
origin	git@github.com:slaclab/mps_database.git (fetch)
origin	git@github.com:slaclab/mps_database.git (push)
```
Make sure you clone that mps_database repo into the TOP of this directory before testing. This is temporary, 
will be in a container soon. 

4. Then install the mps_database as a python package
`cd mps_database && pip install -e .`

### Testing locally
1. Use the [docker-compose.yml](mps_collector/test/docker-compose.yml) with `docker compose up -d`
2. (Optional) - open up the kafka UI at http://localhost:8080
3. Build with debug `make debug`
4. Run the history collector `./bin/mps_collector_debug localhost:9094 your_topic 3356 PLAINTEXT "" ""`
5. Run the test [client.py](client.py) `python3 client.py`

If `python3 client.py` throws error with mps_database. Then you can download it from the dev servers onto the top of this repo.

`scp -r YOUR_USERNAME@dev-srv09:/sdf/group/ad/transition/afs/slac.stanford.edu/g/lcls/vol9/package/anaconda/envs/python3.10envs/rhel7/v1.0/lib/python3.10/site-packages/mps_database ./`

6. When done you can do a `docker compose down` assuming your in the mps_collector/ dir

### Testing on dev cluster (devlogin)
1. Build with debug `make debug`
2. Create a file called kafka_password in mps_collector/, in the file add in the password from the vault on secret/ad/accel-webapp-dev/mps-history/application-secrets
2. Run the history collector from top level: 
`/sdf/home/p/pnispero/mps/mps_history/bin/mps_collector_debug /sdf/home/p/pnispero/mps/mps_history/mps_collector/dev.json`
3. Run the test [client.py](client.py) `python3 client.py`
4. The mps processor is always running on accel-webapp-dev cluster, if not then can check the README.md in mps_processor/

### How to view data in kafka instance
1. Install kafkacat `sudo apt-get install kafkacat`
2. 

### How to run on prod (lcls)
1. TODO - make a startup script.


# With authentication
kafkacat -b 172.24.8.129:9094 -X security.protocol=SASL_PLAINTEXT \
  -X sasl.mechanisms=SCRAM-SHA-512 \
  -X sasl.username=mps-data-ingestion-publisher \
  -X sasl.password=<password> \
  -C -t mps-data-ingestion -o beginning