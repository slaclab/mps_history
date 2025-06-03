# Compiler to use
CXX = g++

# Compiler flags
CXXFLAGS = -Wall -Wextra -O2 -std=c++11 -static

# Debug flags
DEBUG_FLAGS = -DDEBUG -g -O0

# Path to librdkafka source
RDKAFKA_PATH = $(HOME)/librdkafka/librdkafka-2.8.0

# Include paths
INCLUDES = -I$(RDKAFKA_PATH)/src -I$(RDKAFKA_PATH)/src-cpp

# Library Requirements per librdkafka:
# The GNU toolchain
# GNU make
# pthreads
# zlib-dev (optional, for gzip compression support)
# libssl-dev (optional, for SSL and SASL SCRAM support)
# libsasl2-dev (optional, for SASL GSSAPI support)
# libzstd-dev (optional, for ZStd compression support)
# libcurl-dev (optional, for SASL OAUTHBEARER OIDC support)

# Libraries to link (static linking)
LIBS = $(RDKAFKA_PATH)/src-cpp/librdkafka++.a \
		$(RDKAFKA_PATH)/src/librdkafka.a \
       -lpthread -lz -lssl -lcrypto -lsasl2 -lzstd -lcurl

# Source files
SRCS = mps_collector.cpp

# Object files (automatically generated from source files)
OBJS = $(SRCS:.cpp=.o)
DEBUG_OBJS = $(SRCS:.cpp=.debug.o)

# Output executable name
TARGET = mps_collector
DEBUG_TARGET = mps_collector_debug

# Default target
all: $(TARGET)

# Debug build target
debug: $(DEBUG_TARGET)

# Link object files to create executable (release version)
$(TARGET): $(OBJS)
	$(CXX) $(CXXFLAGS) -o $@ $^ $(LIBS)

# Link object files to create executable (debug version)
$(DEBUG_TARGET): $(DEBUG_OBJS)
	$(CXX) $(CXXFLAGS) $(DEBUG_FLAGS) -o $@ $^ $(LIBS)

# Compile source files to object files (release version)
%.o: %.cpp
	$(CXX) $(CXXFLAGS) $(INCLUDES) -c $< -o $@

# Compile source files to object files (debug version)
%.debug.o: %.cpp
	$(CXX) $(CXXFLAGS) $(DEBUG_FLAGS) $(INCLUDES) -c $< -o $@

# Clean up generated files
clean:
	rm -f $(OBJS) $(DEBUG_OBJS) $(TARGET) $(DEBUG_TARGET)

# Phony targets (targets that aren't actual files)
.PHONY: all debug clean