#!/bin/bash

#
# startup script for gps position and ecm mode
#
# Copyright (C) 2021 Deepseek Labs, Inc.
#

export TERM=linux
export LOGNAME=pi
export HOME=/home/pi
export WORKON_HOME=$HOME/.virtualenvs
export VIRTUALENVWRAPPER_PYTHON=/usr/bin/python3
export LANGUAGE=en_US.UTF-8
export LANG=en_US.UTF-8
export PATH=/bin:/usr/bin:/usr/local/bin

export PYTHONDONTWRITEBYTECODE=yes
export PYTHONUNBUFFERED=1

cd $HOME

source `which virtualenvwrapper.sh`

workon py3cv4

cd modems

if lsusb | egrep Telit; then
    echo "Found Telit"
else
    echo "Telit not found"
    exit 0
fi

python3 ./gps.py --verbose --init --retries 6
python3 ./ecm.py --verbose --start --setclock

