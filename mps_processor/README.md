# MPS History Collector
A barebones receiver of data from the mps central nodes through UDP. 
Then sends the raw data directly to the kafka message brokers of the ELOG. 
Where it will later be processed and written to the ELOG database.

## How to Deploy (on k8s cluster)
1. kubectl -n mps-history apply -f mps_processor/deployment
2. (You only need to add this secret one time, this is for the image to be pulled to be authorized) 
kubectl -n mps-history create secret docker-registry github-container-registry \
  --docker-server=ghcr.io \
  --docker-username=pnispero \
  --docker-password=<GITHUB_PAT> \
  --docker-email=pnispero@slac.stanford.edu


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

GET request for tags of MPS-HISTORY logbook
NOTE - You have to use the id, not the tag name for making new entries associated with tags.
{"id":"5723c868-0b39-4be9-ae08-9d4e5cd8f86f","name":"bypass","description":"Tag for bypasses (Digital, Analog, or Application Card)","logbook":{"id":"684c71350de278523b9f3daf","name":"mps-history"}},{"id":"803bf78d-a718-419d-bd81-979bee35cf54","name":"fault-state","description":"Fault state change","logbook":{"id":"684c71350de278523b9f3daf","name":"mps-history"}},{"id":"a45b3865-0e31-4083-be08-0b69274096a8","name":"channel","description":"Channel state change","logbook":{"id":"684c71350de278523b9f3daf","name":"mps-history"}},