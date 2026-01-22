/*
mps_collector.cpp 

DESC: Main program to receive data from MPS Central Nodes via UDP
    and write to ELOG Kafka via TCP to be later processed.

Reference: https://github.com/confluentinc/librdkafka/blob/master/examples/producer.cpp
*/
#include <iostream>
#include <string>
#include <cstdlib>
#include <csignal>
#include <cstring>
#include <sys/socket.h>
#include <netinet/in.h>
#include <unistd.h>
#include <rdkafkacpp.h>
#include <arpa/inet.h> // For inet_ntop
#include <cadef.h> // For EPICS channel access
#include <chrono>
#include "json.hpp"
#include <fstream>
#include <stdexcept>

enum HistoryMessageType {
  FaultStateType = 1,     // Fault change state (Faulted/Not Faulted)
  BypassDigitalType,      // Bypass digital fault
  BypassAnalogType,       // Bypass analog fault
  BypassApplicationType,  // Bypass analog fault
  DigitalChannelType,     // Change in digital channel
  AnalogChannelType,      // Change in analog device threshold status
};

typedef struct {
  HistoryMessageType type;
  uint32_t id;        // MPS database ID for the Fault/Input/Mitigation
  uint32_t oldValue;
  uint32_t newValue;
  uint32_t aux;

  void print() {
    std::cout << "[MSG] type=" << type
              << ", id=" << id
              << ", old=" << oldValue
              << ", new=" << newValue
              << ", aux=" << aux << std::endl;
  }
} Message;

// For clean shutdown - Set run to 0 exits the main while loop. 
static volatile sig_atomic_t run = 1;
static void sigterm(int sig) {
  run = 0;
}

// Delivery report callback
class DeliveryReportCallback : public RdKafka::DeliveryReportCb {
public:
  void dr_cb(RdKafka::Message &message) {
    if (message.err())
      std::cerr << "% Message delivery failed: " << message.errstr() << std::endl;
    else
      std::cerr << "% Message delivered to topic " << message.topic_name()
                << " [" << message.partition() << "] at offset "
                << message.offset() << std::endl;
  }
};

// Optional: Message counter for statistics
class MessageStats {
public:
  MessageStats() : message_count(0), bytes_received(0) {}
  
  void update(size_t bytes) {
    message_count++;
    bytes_received += bytes;
    
    // Print stats every 1000 messages
    if (message_count % 1000 == 0) {
      std::cout << "Stats: Received " << message_count << " messages (" 
                << bytes_received << " bytes)" << std::endl;
    }
  }
  
private:
  uint64_t message_count;
  uint64_t bytes_received;
};

static std::string dir_of(const std::string& path)
{
    auto p = path.find_last_of("/\\");
    return (p == std::string::npos) ? "." : path.substr(0, p);
}

static std::string join_path(const std::string& baseDir, const std::string& maybeRelative)
{
    if (maybeRelative.empty()) return maybeRelative;
    // absolute path?
    if (maybeRelative[0] == '/') return maybeRelative;
    return baseDir + "/" + maybeRelative;
}

static std::string read_first_line(const std::string& path)
{
    std::ifstream in(path);
    if (!in) throw std::runtime_error("can't open file: " + path);
    std::string s;
    std::getline(in, s);
    return s;
}

struct Config {
    std::string brokers, topic;
    std::string security_protocol, sasl_username, sasl_password, sasl_mechanism;
    int udp_port = 0;
    std::string hb_pv;
    int hb_period_sec = 1;
};

static Config load_config_json(const std::string& config_path)
{
    std::ifstream f(config_path);
    if (!f) throw std::runtime_error("can't open config: " + config_path);

    nlohmann::json j;
    f >> j;

    Config c;
    c.brokers = j.at("brokers").get<std::string>();
    c.topic   = j.at("topic").get<std::string>();

    c.security_protocol = j.at("security_protocol").get<std::string>();
    c.sasl_username     = j.at("sasl_username").get<std::string>();
    c.sasl_mechanism    = j.at("sasl_mechanism").get<std::string>();

    c.udp_port = j.at("udp_port").get<int>();

    c.hb_pv         = j.at("hb_pv").get<std::string>();
    c.hb_period_sec = j.at("hb_period_sec").get<int>();

    // secret file path: allow relative to config location
    std::string base = dir_of(config_path);
    std::string pwfile = j.at("sasl_password_file").get<std::string>();
    pwfile = join_path(base, pwfile);
    c.sasl_password = read_first_line(pwfile);

    return c;
}

void ca_check(int status, const char* what)
{
    if (status != ECA_NORMAL) {
        std::cerr << what << ": " << ca_message(status) << std::endl;
    }
}

void configure_kafka(RdKafka::Conf &conf, std::string brokers, std::string security_protocol,
                     std::string sasl_username, std::string sasl_password, std::string sasl_mechanism) {
  // Create Kafka configuration
  // RdKafka::Conf *conf = RdKafka::Conf::create(RdKafka::Conf::CONF_GLOBAL);
  std::string errstr;
  // Configure Kafka
  if (conf.set("bootstrap.servers", brokers, errstr) != RdKafka::Conf::CONF_OK) {
    std::cerr << errstr << std::endl;
    exit(1);
  }
  
  // Configure Kafka with SASL
  if (conf.set("security.protocol", security_protocol, errstr) != RdKafka::Conf::CONF_OK) {
    std::cerr << "Failed to set security.protocol: " << errstr << std::endl;
    exit(1);
  }

  if (conf.set("sasl.mechanism", sasl_mechanism, errstr) != RdKafka::Conf::CONF_OK) {
    std::cerr << "Failed to set sasl.mechanism: " << errstr << std::endl;
    exit(1);
  }

  if (conf.set("sasl.username", sasl_username, errstr) != RdKafka::Conf::CONF_OK) {
    std::cerr << "Failed to set sasl.username: " << errstr << std::endl;
    exit(1);
  }

  if (conf.set("sasl.password", sasl_password, errstr) != RdKafka::Conf::CONF_OK) {
    std::cerr << "Failed to set sasl.password: " << errstr << std::endl;
    exit(1);
  }

  // Set delivery report callback (store pointer to dr_cb)
  static DeliveryReportCallback dr_cb; // Set to static so it lives for programs lifetime
  if (conf.set("dr_cb", &dr_cb, errstr) != RdKafka::Conf::CONF_OK) {
    std::cerr << errstr << std::endl;
    exit(1);
  }

  // Optional performance settings
  if (conf.set("queue.buffering.max.messages", "100000", errstr) != RdKafka::Conf::CONF_OK) {
    std::cerr << errstr << std::endl;
    exit(1);
  }

  if (conf.set("batch.num.messages", "10000", errstr) != RdKafka::Conf::CONF_OK) {
    std::cerr << errstr << std::endl;
    exit(1);
  }

}

int main(int argc, char **argv) {
  if (argc != 2) {
    std::cerr << "Usage: " << argv[0] << " /full/path/to/config.json\n";
    std::cerr << "Example: " << argv[0] << " /sdf/home/p/pnispero/mps/mps_history/mps_collector/prod.json\n";
    return 1;
  }
  Config cfg = load_config_json(argv[1]);

  // Set up signal handlers
  signal(SIGINT, sigterm);
  signal(SIGTERM, sigterm);

  // Configure kafka
  RdKafka::Conf *conf = RdKafka::Conf::create(RdKafka::Conf::CONF_GLOBAL);
  configure_kafka(*conf, cfg.brokers, cfg.security_protocol, cfg.sasl_username, cfg.sasl_password, cfg.sasl_mechanism);

  // Create producer
  std::string errstr;
  RdKafka::Producer *producer = RdKafka::Producer::create(conf, errstr);
  if (!producer) {
    std::cerr << "Failed to create producer: " << errstr << std::endl;
    exit(1);
  }
  delete conf;

  // Verify connection to Kafka
  std::cout << "Verifying Kafka connection..." << std::endl;
  RdKafka::Metadata *metadata = NULL;
  RdKafka::ErrorCode err = producer->metadata(
    true,     // all_topics
    NULL,     // only_topic (no specific topic)
    &metadata, // metadata_p (output parameter)
    10000     // timeout_ms
  );
  if (err != RdKafka::ERR_NO_ERROR) {
      std::cerr << "Failed to get metadata: " << RdKafka::err2str(err) << std::endl;
      std::cerr << "Cannot connect to Kafka cluster at " << cfg.brokers << std::endl;
      delete producer;
      delete conf;
      exit(1);
  }
  
  std::cout << "Successfully connected to Kafka cluster with " 
            << metadata->brokers()->size() << " broker(s)" << std::endl;
  
  // Check if topic exists
  bool topic_exists = false;
  for (auto topic_it = metadata->topics()->begin(); 
        topic_it != metadata->topics()->end(); ++topic_it) {
      if ((*topic_it)->topic() == cfg.topic) {
          topic_exists = true;
          std::cout << "Topic '" << cfg.topic << "' exists with " 
                  << (*topic_it)->partitions()->size() << " partition(s)" << std::endl;
          break;
      }
  }
  
  if (!topic_exists) {
      std::cout << "Topic '" << cfg.topic << "' does not exist yet, it will be auto-created if enabled" << std::endl;
  }

  // Create UDP socket
  int sock_fd = socket(AF_INET, SOCK_DGRAM, 0);
  if (sock_fd < 0) {
    std::cerr << "Failed to create socket" << std::endl;
    delete producer;
    exit(1);
  }

  // Optional: Set UDP receive buffer size
  int rcvbuf = 212992; // Match system maximum
  if (setsockopt(sock_fd, SOL_SOCKET, SO_RCVBUF, &rcvbuf, sizeof(rcvbuf)) < 0) {
    std::cerr << "Warning: Failed to set socket receive buffer size" << std::endl;
  }

  // Check actual buffer size (for information)
  int actual_size;
  socklen_t size_len = sizeof(actual_size);
  if (getsockopt(sock_fd, SOL_SOCKET, SO_RCVBUF, &actual_size, &size_len) == 0) {
      // Linux reports twice the actual size in getsockopt
      std::cout << "UDP buffer size: " << actual_size/2 << " bytes" << std::endl;
  }

  // Bind UDP socket
  struct sockaddr_in server_addr;
  std::memset(&server_addr, 0, sizeof(server_addr));
  server_addr.sin_family = AF_INET;
  server_addr.sin_addr.s_addr = INADDR_ANY;
  server_addr.sin_port = htons(cfg.udp_port);

  if (bind(sock_fd, (struct sockaddr*)&server_addr, sizeof(server_addr)) < 0) {
    std::cerr << "Failed to bind socket" << std::endl;
    close(sock_fd);
    delete producer;
    exit(1);
  }

  std::cout << "UDP collector started on port " << cfg.udp_port 
            << ", forwarding to Kafka topic: " << cfg.topic << std::endl;

  // Buffer for incoming messages
  // Important: The buffer is specifically sized for your Message struct
  char buffer[sizeof(Message)];
  struct sockaddr_in client_addr;
  socklen_t client_len = sizeof(client_addr);
  
  // For select()
  fd_set readfds;
  struct timeval tv;
  
  // Statistics tracking
  MessageStats stats;


  // Channel access setup
  chid hb_ch = nullptr;

  ca_check(ca_context_create(ca_enable_preemptive_callback), "ca_context_create");

  // connection handler optional; can pass nullptr
  ca_check(ca_create_channel(cfg.hb_pv.c_str(), nullptr, nullptr, CA_PRIORITY_DEFAULT, &hb_ch),
          "ca_create_channel(HB)");

  // wait for name resolution + connect (don’t hang forever)
  int st = ca_pend_io(2.0);
  if (st != ECA_NORMAL) {
      std::cerr << "WARNING: heartbeat PV " << cfg.hb_pv <<" not connected: " << ca_message(st) << std::endl;
      // You can continue running; CA will keep trying to connect in the background.
  }

  long hb = 0;
  auto last_hb = std::chrono::steady_clock::now();

  // Main loop that runs forever unless process is terminated or crashes
  while (run) {
    // Set up select (Non-blocking I/O with timeout)
    // Without select, if you just did a recvfrom, the program is stuck waiting for data, and no
    // Kafka callbacks can be performed (at the end of this loop the poll()). 
    FD_ZERO(&readfds);
    FD_SET(sock_fd, &readfds);
    
    // Set timeout (100ms)
    tv.tv_sec = 0;
    tv.tv_usec = 100000;

    // Block until data arrives or 100ms timeout passes
    int ret = select(sock_fd + 1, &readfds, NULL, NULL, &tv);
    
    if (ret < 0) {
      if (errno != EINTR) {
        std::cerr << "Select error: " << strerror(errno) << std::endl;
      }
    } else if (ret > 0 && FD_ISSET(sock_fd, &readfds)) {
      // Data available - receive message
      ssize_t bytes_received = recvfrom(sock_fd, buffer, sizeof(Message), 0,
                                      (struct sockaddr*)&client_addr, &client_len);
      
      if (bytes_received == sizeof(Message)) {
        // Properly received a complete Message struct
        Message* message = reinterpret_cast<Message*>(buffer);

        // Optional: Debug/logging
        #ifdef DEBUG
            char client_ip[INET_ADDRSTRLEN];
            inet_ntop(AF_INET, &(client_addr.sin_addr), client_ip, INET_ADDRSTRLEN);
            
            std::cout << "Received message from " << client_ip << ":" << ntohs(client_addr.sin_port) << std::endl;
            message->print();
            std::cout << "Message printed successfully" << std::endl;
        #endif  

        // Update statistics
        stats.update(bytes_received);
        std::cout << "Statistics updated, preparing to produce to Kafka..." << std::endl;
        
      // Make the produce call safer by catching any errors
      RdKafka::ErrorCode err;
      retry_produce:
      try {
          err = producer->produce(
              cfg.topic,
              RdKafka::Topic::PARTITION_UA,
              RdKafka::Producer::RK_MSG_COPY, // Use COPY flag to ensure data is copied
              buffer, sizeof(Message),
              NULL, 0,  // No key
              0,        // Use current timestamp
              NULL,     // No headers
              NULL);    // No opaque
      } catch (const std::exception& e) {
          std::cerr << "Exception in produce call: " << e.what() << std::endl;
          continue;
      } catch (...) {
          std::cerr << "Unknown exception in produce call" << std::endl;
          continue;
      }

        if (err != RdKafka::ERR_NO_ERROR) {
          if (err == RdKafka::ERR__QUEUE_FULL) {
            // Queue full, wait and retry
            /* If the internal queue is full, wait for
            * messages to be delivered and then retry.
            * The internal queue represents both
            * messages to be sent and messages that have
            * been sent or failed, awaiting their
            * delivery report callback to be called.
            *
            * The internal queue is limited by the
            * configuration property
            * queue.buffering.max.messages and queue.buffering.max.kbytes */
            producer->poll(1000); /*block for max 1000ms*/
            goto retry_produce;
          } else {
            std::cerr << "Failed to produce message: " << RdKafka::err2str(err) << std::endl;
          }
        }
      } else if (bytes_received > 0) {
        // Received data but not the expected size
        std::cerr << "Warning: Received " << bytes_received << " bytes, expected " 
                  << sizeof(Message) << " bytes" << std::endl;
      }
    }
    
    // Process delivery reports
    producer->poll(0);

    // Heartbeat update
    auto now = std::chrono::steady_clock::now();
    if (now - last_hb >= std::chrono::seconds(cfg.hb_period_sec)) {
        last_hb = now;
        hb++;

        // Only try if CA thinks it is connected
        if (hb_ch && ca_state(hb_ch) == cs_conn) {
            int rc = ca_put(DBR_LONG, hb_ch, &hb);
            if (rc != ECA_NORMAL) {
                std::cerr << "HB ca_put failed: " << ca_message(rc) << std::endl;
            }
            ca_flush_io(); // push it out promptly
        }
    }

  }

  // Clean shutdown
  std::cout << "Shutting down..." << std::endl;
  
  // Flush any remaining messages
  std::cout << "Flushing remaining messages..." << std::endl;
  producer->flush(10 * 1000 /* wait for max 10 seconds */);

  // Clean up channel access
  if (hb_ch) ca_clear_channel(hb_ch);
  ca_context_destroy();

  if (producer->outq_len() > 0) {
    std::cerr << producer->outq_len() << " message(s) were not delivered" << std::endl;
  }

  // Clean up
  close(sock_fd);
  delete producer;

  return 0;
}