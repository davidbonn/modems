#!/usr/bin/env python3

"""exerciser for gps functions of telit/sixfab wireless card

    Usage:

    python3 gpstest.py [--verbose] [--count n] [--hdop v] --device /dev/ttyUSB2

    --device sets the device to send AT commands to and is passed to cu, assuming 8-bit and 115200 bps
    --hdop v max horizontal dilution of precision acceptable (default 99, 1.5 or so is good)
    --verbose enables lots of debugging output
    --count n performs n GPS fixes (default 1)

    this program needs both cu (apt-get install cu) and pexpect (pip install pexpect)
"""

import argparse
import time
import os

from telit import Telit, ModemError

verbose = False

# TODO:  command line argument to set how many times you try to get a decent fix (now hardcoded to 30)
# TODO:  check_device() needs to do a better job


def check_device(d):
    return os.path.exists(d)


def main():
    global verbose

    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action='store_true', default=False)
    ap.add_argument("--device", required=True, type=str)
    ap.add_argument("--hdop", required=False, type=float, default=99.0)
    ap.add_argument("--count", required=False, type=int, default=1)

    args = ap.parse_args()
    verbose = args.verbose

    if not check_device(args.device):
        print(f"[telit.error]  {args.device} does not exist")
        exit(1)

    with Telit(args.device, verbose=args.verbose) as t:
        time.sleep(0.5)

        try:
            t.send_at_ok()

            print(f"[telit] ***ICCID***: {t.iccid}")
            print(f"[telit] ***Signal Strength***: {round(t.signal_strength*100)}%")

            if t.get_gpsp_status() == 0:
                _ = t.send_gpsp_on()

            for k in range(args.count):
                if k > 0:
                    time.sleep(15)

                x = t.get_position(args.hdop)
                if x is not None:
                    if verbose:
                        print(f"[telit] ***RESULTS***: {x['latitude']:.3f},{x['longitude']:.3f}")
                    else:
                        print(f"{x['latitude']:.3f},{x['longitude']:.3f}")
                else:
                    print(f"[telit] nowhere")

            time.sleep(0.1)

            _ = t.send_gpsp_off()

        except ModemError as e:
            print(f"[telit] ***ERROR***: {e}:")
            print(t.child)


if __name__ == "__main__":
    main()
