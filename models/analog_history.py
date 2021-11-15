import datetime

from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.orm import relationship, backref
from mps_database.models import Base

class AnalogHistory(Base):
  """
  AnalogHistory class (analog_history table)

  Stores the analog inputs sent from the central node.

  All derived data is from the mps_configuration database

  Properties:
   timestamp: the timestamp of the fault event. Format is as follows
     in order to work with sqlite date/time functions: "YYYY-MM-DD HH:MM:SS.SSS"
   channel: The analog channel from the device id
   device: Device name receiving the input
   new_state: Hex value of data sent directly from the central node
   old_state: Hex value of data sent directly from the central node

  """
  __tablename__ = 'analog_history'
  id = Column(Integer, primary_key=True)
  timestamp = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
  channel = Column(Integer, nullable=False) # AnalogChannel from id(AnalogDevice)
  device = Column(String, nullable=False)
  # States are converted to hex?
  new_state = Column(Integer, nullable=False)
  old_state = Column(Integer, nullable=False)
