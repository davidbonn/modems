#!/usr/bin/env python3
"""
    process to bring up ECM mode
    also stash ICCID in Redis
    also compute unique ID and stash in Redis ID
    also check for the presence of the SixFab telit card

    usage:
        python3 ecm.py --start [--verbose]
        python3 ecm.py --stop [--verbose]

    assumes initial setup (usbcfg and cgdcont) is done elsewhere

"""

import argparse

from common.rediswrapper import RedisWrapper
from telit import Telit, check_for_telit

verbose = False


def find_pi_id():
    """
        find raspberry pi id in /proc/cpuinfo

        returns (str):
            pi:dddddddddddddddddddd (raspberry pi 3 and earlier)
            pi4:dddddddddddddddddddd (raspberry pi 4 &c)
            None (no Serial # found in /proc/cpuinfo

        type determination from
            https://www.raspberrypi.org/documentation/hardware/raspberrypi/revision-codes/README.md
    """

    with open("/proc/cpuinfo", "r") as f:
        lines = f.readlines()

    serial = None
    revision = None

    for w in lines:
        if len(w) > 8 and w[:8] == "Revision":
            words = w.split(':')
            if len(words) == 2:
                revision = int(words[1], base=16)

        if len(w) > 6 and w[:6] == "Serial":
            words = w.split(':')
            if len(words) == 2:
                serial = int(words[1], base=16)

    if serial is None:
        return None

    if revision is None:
        rc = f"pi:{serial}"
    else:
        pi_type = (revision & 0b0111111110000) >> 4

        if pi_type >= 11:
            rc = f"pi4:{serial}"
        else:
            rc = f"pi:{serial}"

    return rc


def main():
    global verbose

    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", required=False, default=False, action='store_true')
    ap.add_argument("--start", required=False, default=False, action='store_true')
    ap.add_argument("--stop", required=False, default=False, action='store_true')

    args = ap.parse_args()

    verbose = args.verbose

    if args.start and args.stop:
        print(f"[ecm] Error:  cannot specify both --start and --stop")
        exit(1)

    R = RedisWrapper()
    pi_id = find_pi_id()
    R["PI_ID"] = pi_id

    if verbose:
        print(f"[ecm] pi_id is {pi_id}")

    if not check_for_telit():
        R["ID"] = pi_id
        if verbose:
            print(f"[ecm] no telit card, exiting")

        exit(1)

    with Telit("/dev/ttyUSB2", verbose=verbose) as t:
        if args.start:
            t.send_at_ok()

            iccid = f"iccid:{t.iccid}"

            if verbose:
                print(f"[ecm] iccid is {iccid}")

            R["ID"] = iccid

            if t.ecm_up():
                if verbose:
                    print(f"[ecm] ECM mode already enabled")

                exit(1)

            t.ecm_start()
        elif args.stop:
            t.send_at_ok()

            if not t.ecm_up():
                if verbose:
                    print(f"[ecm] ECM mode already disabled")

                exit(1)

            t.ecm_stop()


if __name__ == "__main__":
    main()
