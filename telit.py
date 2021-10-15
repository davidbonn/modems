"""
Class interface for the Telit LE910C4 cellular module


    this module needs both cu (apt-get install cu) and pexpect (pip install pexpect)
    I broke this into a class heirarchy just to separate the functions a bit and make it
    a bit less overwhelming to piece together what is going on.

    In practice you use these functions by making an instance of the Telit class like so:

    with Telit("/dev/ttyUSB2", verbose=True) as t:
        t.send_at_ok()
        ...

    Recommended to always use send_at_ok() as the first thing you do with it
"""

# Copyright (C) 2021 Deepseek Labs, Inc.


import time
import datetime
import pexpect
import subprocess

# TODO:  consider using an @retry decorator to handle the retries rather than with explicit loops
# TODO:  a lot of duplicated code could be refactored
# TODO:  Get network provider name
# TODO:  more info in __str__()


def check_for_telit():
    """checks for presence of telit module"""
    output = subprocess.run(["lsusb"], capture_output=True, text=True).stdout

    if "Telit Wireless Solutions" in output:
        return True

    return False


class ModemError(Exception):
    pass


class ModemBusted(ModemError):
    pass


class ModemTimeout(ModemError):
    pass


class TelitGPSDataError(ModemError):
    pass


class ECMDataError(ModemError):
    pass


class TelitDataError(ModemError):
    pass


class ModemBase:
    """
    base class to handle opening the communications channel and resource grabbing protocol
    supports context managers and manages pexpect child process and also has helper code to wait for
    modem results and do initial command-finding (by repeated sending 'AT' commands)
    """
    def __init__(self, device, timeout=10, verbose=False, bps=115200):
        self._device = device
        self._timeout = timeout
        self._verbose = verbose
        self._bps = bps
        self._child = None
        self._cmd = f"cu --nostop --parity none --baud {self._bps} --line {self._device} dir"

    def __str__(self):
        return f"{type(self)}({self._device}, verbose is {self._verbose})"

    def _start_cu(self):
        self._child = pexpect.spawn(self._cmd)
        return self

    def __enter__(self):
        return self._start_cu()

    def __exit__(self, exc_type, exc_value, traceback):
        self._child.sendline("")
        time.sleep(0.1)
        self._child.sendline("~.")
        time.sleep(0.5)

    @property
    def child(self):
        return self._child

    def _handle_single_result(self, i):
        """this function handles a single result and returns it as a str"""
        if i == 0:
            if self._verbose:
                print(f"[telit] Timeout, failing!")

            raise ModemTimeout
        elif i == 1:
            rc = self._child.match[1].decode('utf-8')

            if self._verbose:
                print(f"[telit] results:  '{rc}'")

            return rc

        raise ModemBusted

    def _wait_for_result(self):
        """wait for OK, ERROR, or timeout return "OK" or raise an exception"""
        i = self._child.expect([pexpect.TIMEOUT, "OK\r\n", "ERROR\r\n"], timeout=self._timeout)

        if i == 0:
            if self._verbose:
                print(f"[telit] Timed out!")

            raise ModemTimeout
        elif i == 1:
            if self._verbose:
                print(f"[telit] Saw OK")

            return "OK"
        elif i == 2:
            if self._verbose:
                print(f"[telit] Saw ERROR")

            raise ModemError

        raise ModemBusted

    def send_at_ok(self, count=10):
        """repeatedly send 'AT' command until we get OK or give up"""
        self._child.send("\r")
        time.sleep(0.1)

        for k in range(count):
            if self._verbose:
                print(f"[telit] Trying to send 'AT', try #{k + 1}")

            self._child.send("AT\r")

            try:
                _ = self._wait_for_result()

            except ModemTimeout:
                time.sleep(0.5)

            else:
                return

        raise ModemTimeout

    @classmethod
    def _strip_quotes(cls, buf):
        # strip quotes out from buf
        if len(buf) < 2:
            return buf

        if buf[0] == '"' and buf[-1] == '"':
            return buf[1:-1]

        return buf

    def _command_with_result(self, description, command, pattern):
        """send a command and wait for a result pattern and OK"""
        if self._verbose:
            print(f"[telit] {description} {command}")

        self._child.send(f"{command}\r")

        i = self._child.expect([pexpect.TIMEOUT, pattern], timeout=self._timeout)
        rc = self._handle_single_result(i)
        _ = self._wait_for_result()

        return rc


class TelitGPS(ModemBase):
    """
    Telit GPS modem interface.  Right now only GPS functions
    """
    def __init__(self, device, verbose=False, timeout=10):
        super().__init__(device, timeout=timeout, verbose=verbose)

    def get_gpsp_status(self):
        """get the current state of the gps (in case it is on)"""
        rc = self._command_with_result("Getting GPS power state with", "AT$GPSP?", r"[$]GPSP:[ ]+([0-9])\r\n")
        return int(rc)

    def send_gpsp(self, state):
        """turn the gps on or off"""
        self._child.send(f"AT$GPSP={state}\r")

        _ = self._wait_for_result()
        return True

    def send_gpsp_on(self):
        """turn on gps"""
        if self._verbose:
            print(f"[telit] Sending AT$GPSP=1 to power on GPS")

        return self.send_gpsp(1)

    def send_gpsp_off(self):
        """turn off gps"""
        if self._verbose:
            print(f"[telit] Sending AT$GPSP=0 to power off GPS")

        return self.send_gpsp(0)

    def _get_one_position(self):
        """get position, matched string or None"""
        return self._command_with_result(
            "Getting current position with", "AT$GPSACP", r"[$]GPSACP:[ ]+([0-9A-Z,.]+)\r\n")

    @classmethod
    def _parse_latitude(cls, lat):
        """produce normal signed fractional latitude from weird gps value"""
        direction = lat[-1:]
        sign = 0

        if direction == "N":
            sign = 1
        elif direction == "S":
            sign = -1

        return sign * (float(int(lat[:2])) + float(lat[2:-1]) / 60)

    @classmethod
    def _parse_longitude(cls, lon):
        """produce normal signed fractional longitude from weird gps value"""
        direction = lon[-1:]
        sign = 0

        if direction == "E":
            sign = 1
        elif direction == "W":
            sign = -1

        return sign * (float(int(lon[:3])) + float(lon[3:-1]) / 60)

    @classmethod
    def _parse_values(cls, position):
        """break out values from GPS sentence"""
        if len(position) != 12:
            raise TelitGPSDataError

        rc = dict(
            GMTIME=position[0],
            LATITUDE=position[1],
            LONGITUDE=position[2],
            HDOP=position[3],
            ALTITUDE=position[4],
            fix=position[5],
            COG=position[6],
            SPKM=position[7],
            SPKN=position[8],
            DATE=position[9],
            NSAT_GPS=position[10],
            NSAT_GLONASS=position[11],
        )

        rc["latitude"] = Telit._parse_latitude(rc["LATITUDE"])
        rc["longitude"] = Telit._parse_longitude(rc["LONGITUDE"])
        rc["altitude"] = float(rc["ALTITUDE"])
        rc["hdop"] = float(rc["HDOP"])

        return rc

    def get_position(self, hdop, total=30):
        """
            get gps position.
            retry until a valid sentence is returned with an hdop less or equal to than the passed hdop
            returns a dict
        """
        min_results = None

        for k in range(total):
            if k > 0:
                time.sleep(10)

            results = self._get_one_position()

            if results is None:
                time.sleep(0.1)
                continue

            position = results.split(',')

            if len(position) >= 6 and position[5] == '3':
                rc = self._parse_values(position)
                if hdop >= rc["hdop"]:
                    return rc
                else:
                    if min_results is None or min_results["hdop"] >= rc["hdop"]:
                        min_results = rc

            if self._verbose:
                print(f"[telit] get_position(): Try #{k+1}, got {position[5]}, hdop was '{position[3]}'")

        if self._verbose:
            if min_results is None:
                print(f"[telit] Got nothing")
            else:
                print(f"[telit] Best result had hdop {min_results['hdop']}")

        return min_results


class TelitECM(TelitGPS):
    """
    Telit modem interface
    Has functions for ECM Mode and to set up ECM Mode
    """
    def __init__(self, device, verbose=False, timeout=10):
        super().__init__(device, timeout=timeout, verbose=verbose)

    def _wait_for_reboot(self):
        """wait a long time, then do AT resync """
        if self._verbose:
            print(f"[telit] Rebooting... expect a long pause")

        time.sleep(30)

        if self._verbose:
            print(f"[telit] Waiting for cu to terminate")
        i = self._child.expect([pexpect.TIMEOUT, pexpect.EOF], timeout=30)

        if i == 0:
            raise ModemTimeout
        elif i == 1:
            if self._verbose:
                print(f"[telit] Restarting cu")

            self._start_cu()

        time.sleep(0.5)
        self.send_at_ok()

    def reboot(self):
        """send reboot command"""
        if self._verbose:
            print(f"[telit] Sending AT#REBOOT")

        self._child.send("AT#REBOOT\r")
        self._wait_for_reboot()

    def get_usb_config(self):
        """get weird USB config value"""
        return int(self._command_with_result("Sending", "AT#USBCFG?", r"[#]USBCFG:[ ]+([0-9]+)\r\n"))

    def set_usb_config(self, value=4):
        """set USB config.  in practice we always set it to 4"""
        if self._verbose:
            print(f"[telit] Sending AT#USBCFG={value}")

        self._child.send(f"AT#USBCFG={value}\r")
        _ = self._wait_for_result()
        self._wait_for_reboot()

    def get_cgdcont(self):
        """
            return a tuple having the network provider configuration
        """
        if self._verbose:
            print(f"[telit] Sending AT+CGDCONT?")

        self._child.send(f"AT+CGDCONT?\r")

        finished = False
        rc = None

        while not finished:
            i = self._child.expect([pexpect.TIMEOUT, r'[+]CGDCONT:[ ]+([0-9A-Za-z,"]+)\r\n', r"OK\r\n"])

            if i == 2:
                finished = True
            elif i == 0:
                if self._verbose:
                    print(f"[telit] Timeout, failing!")

                raise ModemTimeout
            elif i == 1:
                stuff = self._child.match[1].decode('utf-8')

                if self._verbose:
                    print(f"[telit] results: {stuff}")

                stuff = stuff.split(",")

                if len(stuff) >= 4 and stuff[0] == "1":
                    rc = stuff
                    rc[1] = self._strip_quotes(rc[1])
                    rc[2] = self._strip_quotes(rc[2])

        if rc is None:
            raise ECMDataError

        return rc

    def set_cgdcont(self, ip, sim_id):
        """set network provider configuration, typical values are ip="IP" and sim_id="super" """
        if self._verbose:
            print(f'[telit] Sending AT+CGDCONT=1,"{ip}","{sim_id}"')

        self._child.send(f'AT+CGDCONT=1,"{ip}","{sim_id}"\r')
        _ = self._wait_for_result()

    def ecm_start(self):
        """bring ECM online"""
        if self._verbose:
            print(f"[telit] Sending AT#ECM=1,0")

        self._child.send("AT#ECM=1,0\r")
        _ = self._wait_for_result()

    def ecm_stop(self):
        """take ECM offline"""
        if self._verbose:
            print(f"[telit] Sending AT#ECMD=0")

        self._child.send("AT#ECMD=0\r")
        _ = self._wait_for_result()

    def ecm_up(self):
        """returns truthy if ECM is up and running"""
        v = self.get_ecm_config()

        return v[1] == "1"

    def get_ecm_config(self):
        """
            returns list of str with ECM configuration
        """
        stuff = self._command_with_result("Sending", "AT#ECMC?", r'[#]ECMC:[ ]+([0-9A-Za-z,."]+)\r\n')
        rc = None
        stuff = stuff.split(",")

        if len(stuff) >= 5:
            rc = [self._strip_quotes(v) for v in stuff]

        if rc is None:
            raise ECMDataError

        return rc


class Telit(TelitECM):
    """
        Telit modem interface,
        this layer has special functions
    """
    def __init__(self, device, verbose=False, timeout=10):
        super().__init__(device, timeout=timeout, verbose=verbose)

    @property
    def iccid(self):
        """Returns ICCID found on modem as an int"""
        return int(self._command_with_result("Getting ICCID with", "AT+ICCID", r"[+]ICCID:[ ]+([0-9]+)\r\n"))

    @property
    def imei(self):
        """returns IMEI number found on modem as an int"""
        rc = int(self._command_with_result("Getting IMEI with", "AT+IMEISV", r"[+]IMEISV:[ ]+([0-9]+)\r\n"))
        return rc // 100

    @property
    def signal_strength(self):
        """Returns signal strength as a float between 0 and 1 or None if not computed"""
        rc = int(self._command_with_result(
            "Getting signal strength with", "AT+CSQ", r"[+]CSQ:[ ]+([0-9]+),[0-9]+\r\n"))

        if rc <= 31:
            rc = float(rc / 31)
        elif 100 <= rc <= 191:
            rc = float((rc - 100) / 91)
        else:
            rc = None

        return rc

    @property
    def clock(self):
        """returns current value of RTC as datetime in whatever timezone the rtc uses"""

        rc = self._command_with_result(
            "Getting clock value with", "AT+CCLK?", r'[+]CCLK:[ ]+["]([-0-9,/:+]+)["]\r\n')

        zone_offset = int(rc[17:])

        if zone_offset % 4 != 0:
            raise TelitDataError("FIXME:  handle zone_offsets that aren't a whole hour")

        tz = datetime.timezone(offset=datetime.timedelta(hours=zone_offset // 4))
        return datetime.datetime(
            int(rc[0:2]) + 2000, int(rc[3:5]), int(rc[6:8]), int(rc[9:11]), int(rc[12:14]), int(rc[15:17]),
            tzinfo=tz
        )

    @property
    def utc_clock(self):
        """returns current value of RTC normalized to UTC"""
        return self.clock.astimezone(datetime.timezone(offset=datetime.timedelta(hours=0)))
