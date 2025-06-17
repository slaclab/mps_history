# MPS History Collector
A barebones receiver of data from the mps central nodes through UDP. 
Then sends the raw data directly to the kafka message brokers of the ELOG. 
Where it will later be processed and written to the ELOG database.

## Mps History Tags
There are 3 tags which I created manually through a regular curl request (its simple).
1. fault-state
2. channel
3. bypass

Note - Replace <ELOG_USER_PASSWORD> with the actual password

curl -X 'POST' \
  'https://accel-webapp-dev.slac.stanford.edu/api/elog-apptoken/v1/logbooks/684c71350de278523b9f3daf/tags' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -H 'x-vouch-idp-accesstoken: <ELOG_USER_PASSWORD>' \
  -d '{
  "name": "bypass",
  "description": "Tag for bypasses (Digital, Analog, or Application Card)"
}'

curl -X 'POST' \
  'https://accel-webapp-dev.slac.stanford.edu/api/elog-apptoken/v1/logbooks/684c71350de278523b9f3daf/tags' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -H 'x-vouch-idp-accesstoken: <ELOG_USER_PASSWORD>' \
  -d '{
  "name": "fault-state",
  "description": "Fault state change"
}'

curl -X 'POST' \
  'https://accel-webapp-dev.slac.stanford.edu/api/elog-apptoken/v1/logbooks/684c71350de278523b9f3daf/tags' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -H 'x-vouch-idp-accesstoken: <ELOG_USER_PASSWORD>' \
  -d '{
  "name": "channel",
  "description": "Channel state change"
}'