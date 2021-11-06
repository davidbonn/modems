#!/usr/bin/env python3
# Copyright (C) 2021 Deepseek Labs, Inc.

"""
    telit_daemon:  continuously update gps and periodically check ecm connection

    options:
        --verbose
        --ecmcheck seconds   ~~ how often to check ecm connection
        --gpscheck seconds   ~~ how often to check gps coordinates
        --host host          ~~ hostname for ecm check ping
"""

# TODO:  testing
# TODO:  sometimes we need to grab a second GPS fix to get an up-to-date value

import argparse
import os
import time
import json
import threading

import ecm
from common.rediswrapper import RedisWrapper
from telit import Telit, check_for_telit

R = RedisWrapper()
Gps_device = "/dev/ttyUSB2"
Ecm_device = "/dev/ttyUSB3"
Location_src = "/boot/deepseek/location.json"
Location_file = "/tmp/deepseek/location.json"
Location = dict(latitude=0.0, longitude=0.0, elevation=0.0, hdop=9999.99)


def note_location(pos, verbose):
    """stash location in Redis and in /tmp/deepseek/location.json"""
    global Location, R

    if pos is None:
        return

    if R["HDOP"] is not None and pos["hdop"] > R["HDOP"]:
        return

    for k in ["latitude", "longitude", "altitude", "hdop"]:
        Location[k] = pos[k]

    Location["latitude"] = round(pos["latitude"], 4)
    Location["longitude"] = round(pos["longitude"], 4)

    R["LATITUDE"] = Location["latitude"]
    R["LONGITUDE"] = Location["longitude"]
    R["ALTITUDE"] = Location["altitude"]
    R["HDOP"] = Location["hdop"]

    with open(Location_file, "w") as f:
        json.dump(Location, f)

    if verbose:
        loc = f"({Location['latitude']},{Location['longitude']})"
        extra = f"+{Location['altitude']} HDOP={Location['hdop']}"
        print(f"[telit_daemon:info] new location: ({loc}) {extra}")


def gps_thread(interval, verbose):
    """thread that continuously requests GPS information"""
    global Location

    # read gps info from /tmp/deepseek/location.json
    if os.path.exists(Location_src):
        with open(Location_src, "r") as f:
            Location = json.load(f)

        Location["hdop"] = 9999.0

        if verbose:
            loc = f"({Location['latitude']},{Location['longitude']})"
            print(f"[telit_daemon:info] original location: {loc}")

        note_location(Location, verbose)

    # get first gps fix
    with Telit(Gps_device, verbose) as t:
        t.send_at_ok()
        t.send_gpsp_on()

        pos = None

        while pos is None:
            pos = t.get_position(2.0)

        note_location(pos, verbose)
        t.send_gpsp_off()

    # periodically check for a better gps fix
    while True:
        time.sleep(interval)
        with Telit(Gps_device, verbose) as t:
            t.send_at_ok()
            t.send_gpsp_on()

            pos = t.get_position(2.0, total=5)
            note_location(pos, verbose)

            t.send_gpsp_off()


def ecm_thread(interval, host, verbose):
    """thread that checks if ECM is up and keeps it up, actually doesn't run as a thread."""
    while True:
        print(f"[telit_daemon:info] Time:  {time.asctime()}")
        time.sleep(interval)

        if ecm.check_connection(host):
            continue

        if verbose:
            print(f"[telit_daemon:info] ECM connection down, restarting connection")

        with Telit(Ecm_device, verbose) as t:
            t.send_at_ok()
            t.ecm_start()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true", default=False)
    ap.add_argument("--ecmcheck", type=int, default=900)
    ap.add_argument("--gpscheck", type=int, default=1800)
    ap.add_argument("--host", type=str, default="sixfab.com")

    args = ap.parse_args()

    if not check_for_telit():
        if args.verbose:
            print(f"[telit_daemon:info] no telit card, exiting")

        exit(0)

    gps = threading.Thread(name="GPS", target=gps_thread, args=(args.gpscheck, args.verbose))

    ecm.verbose = args.verbose

    gps.start()
    ecm_thread(args.ecmcheck, args.host, args.verbose)


if __name__ == "__main__":
    main()
