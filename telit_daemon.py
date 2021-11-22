#!/usr/bin/env python3
# Copyright (C) 2021 Deepseek Labs, Inc.

"""
    telit_daemon:  continuously update gps and periodically check ecm connection

    options:
        --verbose
        --check seconds      ~~ how often to check ecm connection and gps
        --host host          ~~ hostname for ecm check ping
"""

# TODO:  grab /boot/deepseek/location.json from cloud
# TODO:  use generation number rather than set HDOP to 9999
# TODO:  sometimes we need to grab a second GPS fix to get an up-to-date value
# TODO:  hook to external force a check of connection status

import argparse
import os
import time
import json
import pexpect

import ecm
from common.rediswrapper import RedisWrapper
from telit import Telit, ModemError, check_for_telit

R = RedisWrapper()
Device = "/dev/ttyUSB2"
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
        print(f"[telit_daemon:info] new location: {loc} {extra}")


def gps_init(verbose):
    """get initial gps fix"""
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
    with Telit(Device, verbose) as t:
        t.send_at_ok()
        t.send_gpsp_on()

        pos = None

        while pos is None:
            pos = t.get_position(2.0)

        note_location(pos, verbose)
        t.send_gpsp_off()


def gps_check(verbose):
    """periodically check for better gps fix"""
    global Location

    # periodically check for a better gps fix
    with Telit(Device, verbose) as t:
        t.send_at_ok()
        t.send_gpsp_on()

        pos = t.get_position(2.0, total=2)
        note_location(pos, verbose)

        t.send_gpsp_off()


def ecm_check(host, verbose):
    """checks if ECM is up and restore if it isn't"""

    if ecm.check_connection(host):
        return

    if verbose:
        print(f"[telit_daemon:info] ECM connection down, restarting connection")

    with Telit(Device, verbose) as t:
        t.send_at_ok()
        t.ecm_start()


def main():
    global Device

    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true", default=False)
    ap.add_argument("--device", type=str, default=Device)
    ap.add_argument("--check", type=int, default=900)
    ap.add_argument("--host", type=str, default="sixfab.com")

    args = ap.parse_args()
    Device = args.device

    if not check_for_telit():
        if args.verbose:
            print(f"[telit_daemon:info] no telit card, exiting")

        exit(0)

    if not os.path.exists(Device):
        print(f"[telit_daemon:error] no device {Device}")
        exit(0)

    gps_init(args.verbose)
    ecm.verbose = args.verbose

    while True:
        if args.verbose:
            print(f"[telit_daemon:info] Time check: {time.asctime()}")

        try:
            ecm_check(args.host, args.verbose)
            gps_check(args.verbose)
        except ModemError as e:
            print(f"[telit_daemon:error] Error:  {e}")
        except pexpect.exceptions.EOF as e:
            print(f"[telit_daemon:error] pexpect EOF error: {e}")

        time.sleep(args.check)


if __name__ == "__main__":
    main()
