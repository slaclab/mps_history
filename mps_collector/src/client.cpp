#include <iostream>
#include <string>
#include <cstdlib>
#include <cstring>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <unistd.h>

// Same Message structure definition as your collector
enum HistoryMessageType {
  FaultStateType = 1,
  BypassDigitalType,
  BypassAnalogType,
  BypassApplicationType,
  DigitalChannelType,
  AnalogChannelType,
};

typedef struct {
  HistoryMessageType type;
  uint32_t id;
  uint32_t oldValue;
  uint32_t newValue;
  uint32_t aux;
} Message;

int main(int argc, char** argv) {
  if (argc != 3) {
    std::cerr << "Usage: " << argv[0] << " <collector_ip> <collector_port>\n";
    return 1;
  }
  
  std::string collector_ip = argv[1];
  int collector_port = std::atoi(argv[2]);
  
  // Create socket
  int sock_fd = socket(AF_INET, SOCK_DGRAM, 0);
  if (sock_fd < 0) {
    std::cerr << "Failed to create socket\n";
    return 1;
  }
  
  // Set up target address
  struct sockaddr_in target_addr;
  std::memset(&target_addr, 0, sizeof(target_addr));
  target_addr.sin_family = AF_INET;
  target_addr.sin_port = htons(collector_port);
  
  if (inet_pton(AF_INET, collector_ip.c_str(), &target_addr.sin_addr) <= 0) {
    std::cerr << "Invalid address: " << collector_ip << "\n";
    close(sock_fd);
    return 1;
  }
  
  // Create a simple message
  Message msg;
  msg.type = FaultStateType;
  msg.id = 1001;
  msg.oldValue = 0;
  msg.newValue = 1;
  msg.aux = 42;
  
  // Send the message
  int n = sendto(sock_fd, &msg, sizeof(Message), 0,
               (struct sockaddr*)&target_addr, sizeof(target_addr));
               
  if (n != sizeof(Message)) {
    std::cerr << "Failed to send message: " << strerror(errno) << "\n";
    close(sock_fd);
    return 1;
  }
  
  std::cout << "Message sent successfully\n";
  
  close(sock_fd);
  return 0;
}