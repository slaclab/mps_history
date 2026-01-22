# MPS History Server


## Description 
MPS History Server is a server that receives event data (New channel changes, bypasses, fault states) from the SCMPS Central Nodes, processes them, then writes to a logbook in the ELOG for operators to view.
The system is comprised of two main parts in this repository, the collector, and the processor.
And there are other infrastructure involved, that is not apart of this repository. See this diagram for more details.
https://confluence.slac.stanford.edu/rest/gliffy/1.0/embeddedDiagrams/0447c68e-afa6-4b3b-af27-fb86e2f8e969.png


## How to run
### Pre-requisites
1. Ensure ELOG and Kafka infrastructure are all setup. Can confirm with Claudio or Yekta about that.
2. Ensure you have access to the kubernetes cluster we deploy the MPS Processor on. Right now for development that is accel-webapp-dev, for production it is accel-webapp.
3. If you want to test on DEV, then have MpsSupport IOC (TODO - figure out which IOC) running for the heartbeat.
4. Get a copy of the mps_database you want to install (as of writing this would be the branch new_mpsdb), and add it here at the top level of the repo. The [Dockerfile](mps_processor/Dockerfile) for mps_processor will install it from there.
5. Anytime the mps_configuration updates, the MPS Processor needs to be rebooted.

### MPS Collector
[Refer to mps collector README](mps_collector/README.md)

### MPS Processor
[Refer to mps processor README](mps_processor/README.md)

## Development
### MPS Collector
[Refer to mps collector README](mps_collector/README.md)

### MPS Processor
[Refer to mps processor README](mps_processor/README.md)

## Resources
More Details:
https://confluence.slac.stanford.edu/spaces/~pnispero/pages/399736973/MPS+History+Server