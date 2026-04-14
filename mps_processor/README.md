## How to Deploy (The mps processor runs on a k8s cluster)
0. At the moment we are running the mps processor in the `accel-webapp-dev` cluster
1. `kubectl -n mps-history apply -k mps_processor/deployment/`
2. (For Dev): `kubectl -n mps-history apply -k mps_processor/deployment_dev/`
3. (You only need to add this secret one time, this is for the image to be pulled to be authorized) 
kubectl -n mps-history create secret docker-registry github-container-registry \
  --docker-server=ghcr.io \
  --docker-username=pnispero \
  --docker-password=<GITHUB_PAT> \
  --docker-email=pnispero@slac.stanford.edu

## Secrets (Vault)
All application secrets are managed through Vault and synced to Kubernetes via the `VaultSecret` resource defined in `deployment/application-secrets.yml` (prod) and `deployment/application-secrets-dev.yml` (dev).

https://vault.slac.stanford.edu/ui/

The following secrets must exist in Vault under:
- **Dev**: `secret/ad/accel-webapp-dev/mps-history/application-secrets`
- **Prod**: `secret/ad/accel-webapp/mps-history/application-secrets`

| Secret | Description |
|---|---|
| `ELOG_USER_PASSWORD` | App token for authenticating with the ELOG API |
| `ELOG_HISTORY_LOGBOOK_ID` | ID of the mps-history logbook in ELOG |
| `ELOG_BYPASS_TAG_ID` | ID of the `bypass` tag in ELOG |
| `ELOG_CHANNEL_TAG_ID` | ID of the `channel` tag in ELOG |
| `ELOG_FAULT_TAG_ID` | ID of the `fault-state` tag in ELOG |
| `KAFKA_BOOTSTRAP_SERVER` | Kafka bootstrap server address (e.g. `172.x.x.x:9094`) |
| `KAFKA_PASSWORD` | SASL password for Kafka authentication |

## Reliability: At-Least-Once Delivery
The processor uses **at-least-once delivery** to ensure no MPS fault, bypass, or channel events are silently lost.

- Kafka auto-commit is **disabled** (`enable.auto.commit: False`)
- The Kafka offset is only committed **after** a successful ELOG write (`consumer.commit(asynchronous=False)`)
- If the ELOG write fails (timeout, HTTP error, etc.), the offset is not committed — on pod restart the message will be redelivered and retried
- Tradeoff: if the pod crashes after a successful ELOG write but before the commit, the event may be written to ELOG twice (duplicate entry). But no missed events.

## Liveness Probe
The deployment includes a Kubernetes `livenessProbe` that detects if the poll loop hangs:

- Every poll iteration, `Path("/tmp/healthy").touch()` updates the mtime of `/tmp/healthy` (tmpfs, no disk I/O)
- The probe checks that the file was modified within the last 30 seconds
- If the loop hangs (e.g. blocked network call), the file goes stale and Kubernetes restarts the pod
- All external HTTP calls have a 15s timeout to keep worst-case processing time well under the 30s threshold

## Mps History Tags
There are 3 tags which I created manually through a regular curl request (its simple).
1. fault-state
2. channel
3. bypass

You could also make the tags on the elog website if you are an admin

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