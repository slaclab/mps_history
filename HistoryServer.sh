#!/bin/bash
#This file has been copied & edited from the depreciated EicHistoryServer.
echo 'Starting History Server...'

#Check for dev, assume dev if nothing set
if [ -n "$1" ]
  then echo "mode is $1"
  mode=$1
else 
  echo "mode is unset, default dev"
  mode='dev'
fi

# Set the conda environment
# Eval lets us avoid running conda init each time
if [ `hostname` == 'lcls-dev3' ] || [ `hostname` == 'lcls-dev1' ] || [ `hostname` == 'dev-rhel7' ]; then
  source $TOOLS/script/ENVS64.bash
  #eval "$(conda shell.bash hook)"
  source $PACKAGE_TOP/anaconda/2020.11/etc/profile.d/conda.sh  
  conda activate mps-environment
  echo "Conda environment activated: $CONDA_PREFIX"
fi
#if [`hostname` == 'lcls-dev1' ]; then
#  source $TOOLS/script/ENVS64.bash
#  source $PACKAGE_TOP/anaconda/2020.11/etc/profile.d/conda.sh
#fi
if [ `hostname` == 'PC94483' ]; then
  mode='local'
  eval "$(conda shell.bash hook)"
  conda activate mps-environment
  echo "Conda environment activated: $CONDA_PREFIX"
fi

#TODO: send in db as parameter?
#current_db=$PHYSICS_TOP/mps_configuration/current
#files=`ls $current_db/mps_config*.db | grep -v runtime |  wc -l`

#TODO: Add one in for prod
if [ $mode  == 'dev' ]; then
  #$PHYSICS_TOP/mps_history/start_history.py --port 3356 --dev
  #export PYTHONPATH=$PYTHON_PATH:"/afs/slac/g/lcls/package/anaconda/2020.11/envs/mps-environment/bin/python":"/afs/slac.stanford.edu/u/cd/lking/mps/mps_database"
  python /u/cd/pnispero/mps/mps_history/start_history.py --port 3356 --host dev-rhel7 --dev
  #python /u/cd/lking/mps/mps_history/start_history.py --port 3356 --host lcls-dev3 --dev
fi
if [ $mode == 'local' ]; then
  echo "test local"
  python start_history.py --port 3356  
fi

