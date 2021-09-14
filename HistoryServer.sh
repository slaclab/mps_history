#!/bin/bash
#This file has been copied & edited from the depreciated EicHistoryServer.
echo 'Starting History Server...'

#Set the conda environment
conda activate mps-environment

#TODO: get the right python version/configurations 
#. $TOOLS/script/go_python2.7.13.bash
#export PYTHONPATH=$PHYSICS_TOP/mps_database:$PYTHON_PATH

#TODO: do I need this?
current_db=$PHYSICS_TOP/mps_configuration/current
files=`ls $current_db/mps_config*.db | grep -v runtime |  wc -l`


#TODO: set database location for new history server
#db_file=`ls $current_db/mps_config*.db | grep -v runtime`

#TODO: do we need this file size parameter?   --file-size `echo '1024*1024*10'|bc -l` &
#TODO:this might be the same?
$PHYSICS_TOP/mps_history/start_history.py --port 3356
