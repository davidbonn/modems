# modems

This directory has functions and code to support cellular modems.
Currently only the Telit LE910* modems are supported.

* ecm.py -- enables/disables ethernet control mode, also sets unique ID in redis
* gps.py -- reads current GPS position and saves in Redis
* gpstest.py -- test script
* start.sh -- script to be run before fire detector and chrony to start up networking
* telit.py -- class interface to Telit LE910* modems.

