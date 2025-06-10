# Top-level Makefile that delegates to the source directory

# Directories
SRC_DIR = mps_collector/src
BIN_DIR = bin

# Default target
all: $(BIN_DIR)
	$(MAKE) -C $(SRC_DIR)
	cp $(SRC_DIR)/mps_collector $(BIN_DIR)/
	rm $(SRC_DIR)/mps_collector

# Debug build
debug: $(BIN_DIR)
	$(MAKE) -C $(SRC_DIR) debug
	cp $(SRC_DIR)/mps_collector_debug $(BIN_DIR)/
	rm $(SRC_DIR)/mps_collector_debug

# Create bin directory if it doesn't exist
$(BIN_DIR):
	mkdir -p $(BIN_DIR)

# Clean both directories
clean:
	$(MAKE) -C $(SRC_DIR) clean
	rm -rf $(BIN_DIR)/*

.PHONY: all debug clean