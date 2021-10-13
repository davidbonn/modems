#!/usr/bin/env python3
"""
    process to bring up ECM mode
    also stash ICCID in Redis
    also compute unique ID and stash in Redis ID
    also check for the presence of the SixFab telit card

    usage:
        python3 ecm.py --start [--verbose]
        python3 ecm.py --stop [--verbose]

    When starting you can optionally include --setclock to set the OS clock to the hardware clock of the modem

    assumes initial setup (usbcfg and cgdcont) is done elsewhere
    initial setup is:

        AT#USBCFG=4

        AT+CGDCONT=1,"IP","super"

        AT#REBOOT

    CGDCONT values will be different for non-sixfab SIM cards

"""
# Copyright (C) 2021 Deepseek Labs, Inc.

# TODO:  keep internet connection up if we have to
# TODO:  stash things like signal strength and network name in Redis

import argparse
import os
import subprocess
import re

from common.rediswrapper import RedisWrapper
from telit import Telit, check_for_telit

Clock_flag = "/tmp/telit_clock"
verbose = False


def set_clock(t, check=None):
    """
    sets os clock from HW clock on modem, good for timesync

    t -- is Telit instance
    check -- None or pathname to touch when we set the clock so we set it exactly once

    use date to set the time because chrony is not yet running

    this will give you time sync but not great time sync
    """

    if check is not None and os.path.exists(check):
        return

    utc = t.utc_clock
    utc_str = f"{utc:%m%d%H%M%Y.%S}"

    if verbose:
        print(f"[ecm] Setting time to {utc_str}")

    rc = subprocess.run(["sudo", "date", "--utc", utc_str], capture_output=True, text=True).stdout

    if verbose:
        print(f"[ecm] Output from date:\n{rc}")

    if check is not None:
        with open(check, "w") as f:
            pass


def find_pi_id():
    """
        find raspberry pi id in /proc/cpuinfo

        returns (str):
            pi:dddddddddddddddddddd (raspberry pi 3 and earlier)
            pi4:dddddddddddddddddddd (raspberry pi 4 &c)
            None (no Serial # found in /proc/cpuinfo

        type determination from
            https://www.raspberrypi.org/documentation/hardware/raspberrypi/revision-codes/README.md

        needs to be factored out somewhere else
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


def check_connection(host):
    cmd = ["ping", "-i", "0.4", "-c", "5", host]

    if verbose:
        print(f"[ecm] Checking ECM connection to {host}")

    output = subprocess.run(cmd, capture_output=True, text=True).stdout

    m = re.search(r' ([0-9]+) received, ', output)

    if m is not None:
        if verbose:
            print(f"[ecm] {host} returned {int(m[1])} packets")

        return int(m[1]) != 0

    return False


def main():
    global verbose

    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", required=False, default=False, action='store_true')
    ap.add_argument("--start", required=False, default=False, action='store_true')
    ap.add_argument("--stop", required=False, default=False, action='store_true')
    ap.add_argument("--check", required=False, default=False, action='store_true')
    ap.add_argument("--host", required=False, default="sixfab.com", type=str)
    ap.add_argument("--setclock", required=False, default=False, action='store_true')

    args = ap.parse_args()

    verbose = args.verbose

    if len(list(filter(lambda x: x, [args.start, args.stop, args.check]))) != 1:
        print(f"[ecm] Error:  can specify only one of --start, --stop, --check")
        exit(1)

    if args.setclock and not args.start:
        print(f"[ecm] Error, must specify --setclock only with --start")
        exit(1)

    R = RedisWrapper()

    if args.start:
        pi_id = find_pi_id()
        R["PI_ID"] = pi_id

        if verbose:
            print(f"[ecm] pi_id is {pi_id}")

        if not check_for_telit():
            R["ID"] = pi_id

    if not check_for_telit():
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

            if args.setclock:
                set_clock(t, Clock_flag)

            t.ecm_start()
        elif args.stop:
            t.send_at_ok()

            if not t.ecm_up():
                if verbose:
                    print(f"[ecm] ECM mode already disabled")

                exit(1)

            t.ecm_stop()
        elif args.check:
            if not check_connection(args.host):
                if verbose:
                    print(f"[ecm] Network down, restarting ECM connection")

                t.send_at_ok()
                t.ecm_start()


if __name__ == "__main__":
    main()
