#!/usr/bin/env python3
"""
   this program gets a GPS fix and puts it in Redis, in particular
   in the LATITUDE and LONGITUDE properties
"""

import argparse

from common.rediswrapper import RedisWrapper
from telit import Telit, check_for_telit


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", default=False, action='store_true')
    ap.add_argument("--retries", default=40, type=int)

    args = ap.parse_args()
    R = RedisWrapper()

    if not check_for_telit():
        print(f"[gps] No telit card, exiting")
        exit(1)

    with Telit("/dev/ttyUSB3", args.verbose) as t:
        t.send_at_ok()

        if t.get_gpsp_status() == 0:
            _ = t.send_gpsp_on()

        pos = t.get_position(1.5, total=args.retries)

        if pos is not None:
            R["LATITUDE"] = pos["latitude"]
            R["LONGITUDE"] = pos["longitude"]

        _ = t.send_gpsp_off()


if __name__ == "__main__":
    main()
