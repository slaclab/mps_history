from enum import Enum

class HistoryMessageType(Enum):
  FaultStateType=1         # Fault change state (Faulted/Not Faulted)
  BypassDigitalType=2      # Bypass digital fault
  BypassAnalogType=3       # Bypass analog fault
  BypassApplicationType=4  # Bypass applicaion card
  DigitalChannelType=5     # Change in digital channel
  AnalogChannelType=6      # Change in analog device threshold status
  BypassExpiredFaultType=7    # Bypass expired fault
  BypassExpiredApplicationType=8    # Bypass expired application card
