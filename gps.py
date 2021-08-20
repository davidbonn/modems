#!/usr/bin/env python3
"""
   this program gets a GPS fix and puts it in Redis, in particular
   in the LATITUDE and LONGITUDE properties
"""

# Copyright (C) 2021 Deepseek Labs, Inc.

# TODO:  have it come up in parallel to shorten bootup time
# TODO:  run continuously as you get more accurate results

import argparse
import time

from common.rediswrapper import RedisWrapper
from telit import Telit, check_for_telit

R = RedisWrapper()


def set_coordinates(pos, verbose):
    global R

    if pos is not None:
        R["LATITUDE"] = pos["latitude"]
        R["LONGITUDE"] = pos["longitude"]

        if verbose:
            print(f"[gps] GPS fix:  {pos['latitude']:.3f}, {pos['longitude']:.3f}")


def get_gps_fix(t, verbose, retries):
    pos = t.get_position(2.0, total=retries)

    if pos is None:
        if verbose:
            print(f"[gps] Unable to get GPS fix")

    set_coordinates(pos, verbose)


def get_continuous_gps_fix(t, verbose, until):
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

            if pos["hdop"] <= until:
                if verbose:
                    print(f"[gps] Got GPS fix ({pos['hdop']:.3f})")

                return


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", default=False, action='store_true')
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
            get_gps_fix(t, args.verbose, args.retries)
        else:
            get_continuous_gps_fix(t, args.verbose, args.until)

        _ = t.send_gpsp_off()

    if args.verbose:
        print("[gps] Completed GPS fix")


if __name__ == "__main__":
    main()
