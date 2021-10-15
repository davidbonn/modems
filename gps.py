#!/usr/bin/env python3
"""
   this program gets a GPS fix and puts it in Redis, in particular
   in the LATITUDE and LONGITUDE properties
"""

# Copyright (C) 2021 Deepseek Labs, Inc.

# TODO:  I'm still not feeling warm-and-fuzzy about convergence of coordinate accuracy over time

import argparse
import time
import os
import math
import json

from common.rediswrapper import RedisWrapper
from telit import Telit, check_for_telit

R = RedisWrapper()
Location_src = "/boot/deepseek/location.json"
Location_tmp = "/tmp/deepseek/location.json"


def coord_within_tolerance(coord1, coord2):
    """see if coord1 and coord2 are equal within tolerances (four decimal places)"""
    r_lat = math.isclose(coord1["latitude"], coord2["latitude"], rel_tol=1e-8)
    r_lon = math.isclose(coord1["longitude"], coord2["longitude"], rel_tol=1e-8)

    return r_lat and r_lon


def set_coordinates(pos, verbose):
    """note coordinates found to REDIS"""
    global R

    if pos is None:
        return

    if R["HDOP"] is not None and pos["hdop"] <= R["HDOP"]:
        return

    R["LATITUDE"] = pos["latitude"]
    R["LONGITUDE"] = pos["longitude"]
    R["ALTITUDE"] = pos["altitude"]
    R["HDOP"] = pos["hdop"]

    if verbose:
        print(f"[gps] GPS fix:  {pos['latitude']:.4f}, {pos['longitude']:.4f}")


def update_coordinates(pos, verbose):
    """
    update /tmp/deepseek/location.json if necessary

    "necessary" is when the HDOP has improved and the coordinates have changed
    """

    if pos is None:
        return

    value = dict()
    for k in ["latitude", "longitude", "altitude", "hdop"]:
        value[k] = pos[k]

    value["latitude"] = round(value["latitude"], 4)
    value["longitude"] = round(value["longitude"], 4)

    if os.path.exists(Location_tmp):
        with open(Location_tmp, "r") as f:
            current = json.load(f)

        if value["hdop"] >= current["hdop"] or coord_within_tolerance(current, value):
            return

    if verbose:
        print(
            f"[gps] updating gps coordinates to {Location_tmp} ({value['latitude']:.4f},{value['longitude']:.4f})")

    with open(Location_tmp, "w") as f:
        json.dump(value, f)


def initialize_coordinates(verbose):
    """read coordinates from /boot/deepseek and note them in REDIS and /tmp/deepseek"""
    if not os.path.exists(Location_src):
        return

    with open(Location_src, "r") as f:
        loc = json.load(f)

    # sleazy hack
    # this lets us update with better coordinates or if we have changed the location of the camera
    loc["hdop"] = 9999.00

    set_coordinates(loc, verbose)
    update_coordinates(loc, verbose)


def get_gps_fix(t, verbose, retries):
    """get one gps fix"""
    pos = t.get_position(2.0, total=retries)

    if pos is None:
        if verbose:
            print(f"[gps] Unable to get GPS fix")

    set_coordinates(pos, verbose)
    update_coordinates(pos, verbose)


def get_continuous_gps_fix(t, verbose, until):
    """get a gps fix until the hdop value is below "until" """
    last_pos = None
    counter = 1

    while True:
        pos = t.get_position(until, total=12)

        if pos is None:
            if verbose:
                print(f"[gps] No GPS fix #{counter}")
                counter += 1

            time.sleep(10)
        elif last_pos is None or pos["hdop"] < last_pos["hdop"]:
            last_pos = pos
            set_coordinates(last_pos, verbose)
            update_coordinates(last_pos, verbose)

            if pos["hdop"] <= until:
                if verbose:
                    print(f"[gps] Got GPS fix ({pos['hdop']:.3f})")

                return


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", default=False, action='store_true')
    ap.add_argument("--toss", default=0, type=int)
    ap.add_argument("--retries", default=40, type=int)
    ap.add_argument("--until", default=None, type=float, required=False)

    args = ap.parse_args()

    if not check_for_telit():
        print(f"[gps] No telit card, exiting")
        exit(1)

    with Telit("/dev/ttyUSB3", args.verbose) as t:
        t.send_at_ok()

        if t.get_gpsp_status() == 0:
            _ = t.send_gpsp_on()

        if args.until is None:
            for i in range(args.toss+1):
                get_gps_fix(t, args.verbose, args.retries)
                time.sleep(5)
        else:
            get_continuous_gps_fix(t, args.verbose, args.until)

        _ = t.send_gpsp_off()

    if args.verbose:
        print("[gps] Completed GPS fix")


if __name__ == "__main__":
    main()
