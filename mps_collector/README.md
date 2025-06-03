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

## Development
1. Must link to this library if you want to build the app: https://github.com/confluentinc/librdkafka
2. Use the makefile.
`make`
`make debug` - this provides some debug messages

### Installing librdkafka locally (Build from source)
Download the preferred version into local dir
1. `mkdir ~/librdkafka && cd ~/librdkafka`
1. `curl -L https://github.com/confluentinc/librdkafka/archive/refs/tags/v2.8.0.tar.gz > kafka.tar.gz`
2. `tar -xzf kafka.tar.gz`
3. `cd librdkafka-2.8.0/`

Build
1. `./configure --prefix=$HOME/librdkafka`
The prefix specifies the base directory where the library will be installed. Default is usually "/usr/local", which we want to avoid
2. `make`
3. `make install`
Then confirm the lib, and include are installed. 
Ex: `$ cd ../ && ls`
`include  kafka.tar.gz  lib  librdkafka-2.8.0  share`

Linking
1. Once you're able to install the library, then we want to link it to the mps collector. Thats already done in the Makefile. 

### Testing locally
1. Use the [docker-compose.yml](mps_collector/README.md) with `docker compose up -d`
2. (Optional) - open up the kafka UI at http://localhost:8080
3. Build with debug `cd mps_collecor/src && make debug`
4. Run the history collector `./mps_collector_debug localhost:9094 your_topic 3356 PLAINTEXT "" ""`
5. Run the test [client.py](client.py) `python3 client.py`

If `python3 client.py` throws error with mps_database. Then you can download it from the dev servers onto the top of this repo.

`scp -r YOUR_USERNAME@dev-srv09:/sdf/group/ad/transition/afs/slac.sta
nford.edu/g/lcls/vol9/package/anaconda/envs/python3.10envs/rhel7/v1.0/lib/python3.10/site-packag
es/mps_database ./`
