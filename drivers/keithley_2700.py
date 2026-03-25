import re

import pyvisa
import time


class Keithley2700:
    def __init__(self, gpib_card=0, gpib_address=14, timeout=10000):
        resource_name = "GPIB" + str(gpib_card) + "::" + str(gpib_address) + "::INSTR"
        self.rm = pyvisa.ResourceManager()
        self.inst = self.rm.open_resource(resource_name)
        self.inst.timeout = timeout
        self.configure_output_format()

    # =========================
    # BASIC
    # =========================
    def idn(self):
        return self.inst.query("*IDN?").strip()

    def reset(self):
        self.inst.write("*RST")

    # =========================
    # INIT CONFIG
    # =========================
    def configure_temperature_rtd(self, rtd_type="PT100", four_wire=True, nplc=1):
        self.inst.write("SYST:AZER ON")

        self.inst.write("SENS:FUNC 'TEMP'")
        self.inst.write("SENS:TEMP:TRAN RTD")
        self.inst.write(f"SENS:TEMP:RTD:TYPE {rtd_type}")

        if four_wire:
            self.inst.write("SENS:TEMP:RTD:FOUR ON")
        else:
            self.inst.write("SENS:TEMP:RTD:FOUR OFF")

        self.inst.write(f"SENS:TEMP:NPLC {nplc}")

    # =========================
    # CHANNEL CONTROL
    # =========================
    def close_channel(self, channel):
        self.inst.write(f"ROUT:CLOS (@{channel})")

    def open_all_channels(self):
        self.inst.write("ROUT:OPEN:ALL")

    # =========================
    # FORMAT
    # =========================

    def configure_output_format(
            self,
            read=True,
            time=False,
            unit=False,
            status=False,
            channel=False,
            reading_number=False
    ):
        elements = []

        if read:
            elements.append("READ")
        if time:
            elements.append("TIME")
        if unit:
            elements.append("UNIT")
        if status:
            elements.append("STAT")
        if channel:
            elements.append("CHAN")
        if reading_number:
            elements.append("NUM")

        if not elements:
            raise ValueError("At least one output element must be selected")

        cmd = "FORM:ELEM " + ",".join(elements)
        self.inst.write(cmd)

    # =========================
    # MEASURE
    # =========================
    def read(self):
        self.inst.write("*CLS")
        return self._parse_reading(self.inst.query("READ?"))

    def read_channel(self, channel, delay=0.05):
        self.close_channel(channel)
        time.sleep(delay)  # settling relé
        return self.read()

    def read_channels(self, channels, delay=0.05):
        results = {}

        for ch in channels:
            results[ch] = self.read_channel(ch, delay)

        return results

    def _parse_reading(self, raw):
        """
        Parse a raw measurement string returned by the Keithley 2700 into a structured dictionary.

        The Keithley 2700 can return measurement data in different formats depending on the
        configured output elements (FORM:ELEM). The response may include the measured value,
        timestamp, unit, reading number, and other metadata, typically separated by commas.

        Example raw inputs:
            "+2.94759655E+01"
            "+2.94759655E+01C"
            "+2.94759655E+01,+4259.511SECS"
            "+2.94759655E+01C,+4259.511SECS,+34196RDNG#"
            "+3.03752861E+01\\x13C,+4259.511SECS"

        Notes:
            - The instrument may include non-printable ASCII control characters (e.g., '\\x13')
              that must be removed before parsing.
            - Units (e.g., 'C') and suffixes (e.g., 'SECS', 'RDNG#') are stripped during parsing.
            - The function is tolerant to partial or unexpected formats and will extract
              available fields when possible.

        Parameters:
            raw (str): Raw string returned by the instrument (e.g., from READ? or FETCH?).

        Returns:
            dict: Parsed measurement data. Possible keys include:
                - "value" (float): Measured value (e.g., temperature in °C)
                - "time" (float): Timestamp in seconds (if present)
                - "reading_number" (int): Sequential reading index (if present)

            Example:
                {
                    "value": 29.4759655,
                    "time": 4259.511,
                    "reading_number": 34196
                }

        Raises:
            None explicitly. Invalid or unrecognized parts are ignored silently.

        Recommended usage:
            This function should be used together with a cleaning step that removes
            non-printable characters from the raw instrument response.

        """

        # elimina caracteres no imprimibles
        raw = re.sub(r'[^\x20-\x7E]', '', raw)

        parts = raw.strip().split(",")

        parsed = {}

        for part in parts:
            if "SECS" in part:
                parsed["time"] = float(part.replace("SECS", ""))
            elif "RDNG" in part:
                parsed["reading_number"] = int(part.replace("RDNG#", ""))
            elif "C" in part:
                parsed["value"] = float(part.replace("C", ""))
            else:
                try:
                    parsed["value"] = float(part)
                except:
                    pass

        return parsed

    # =========================
    # FILTER (simple)
    # =========================
        def enable_averaging(self, count=10):
            self.inst.write("SENS:AVER:STAT ON")
            self.inst.write(f"SENS:AVER:COUN {count}")

        def disable_averaging(self):
            self.inst.write("SENS:AVER:STAT OFF")

    # =========================
    # CLOSE
    # =========================
    def close(self):
        self.inst.close()