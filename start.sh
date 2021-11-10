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

found=0

# this is here because usb comes up in parallel with rc.local and might not be ready yet
# usually ten seconds is more than sufficient for usb to come up properly
while [ $found -le 1 ]
do
  if lsusb | egrep Telit; then
      echo "[start] Found Telit"
      found=99
  else
      echo "[start] Telit not found"
      found=`expr $found + 1`
      sleep 10
  fi
done

if [ $found -eq 99 ]; then
  python3 ./ecm.py --verbose --start --setclock
fi

python3 ./telit_daemon.py --verbose &

