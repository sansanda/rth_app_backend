import re

import pyvisa
import time

KEITHLEY_2700_FUNCTIONS = [
    "VOLT:DC",
    "VOLT:AC",
    "CURR:DC",
    "CURR:AC",
    "RES",
    "FRES",
    "TEMP",
    "FREQ",
    "PER",
    "CONT"
]

SUPPORTED_AVG = [
    "VOLT:DC",
    "VOLT:AC",
    "CURR:DC",
    "CURR:AC",
    "RES",
    "FRES",
    "TEMP"
]

SUPPORTED_TCON = ["REP", "MOV"]  # Repeating / Moving

PARAM_MAP = {
    "nplc": "NPLC",
    "range": "RANG",
    "autorange": "RANG:AUTO",
    "digits": "DIG",
    "offset_comp": "OCOM",
    "tran": "TRAN",
    "frtd_type": "FRTD:TYPE"
}

class Keithley2700:
    def __init__(self, gpib_card=0, gpib_address=14, timeout=10000):
        resource_name = "GPIB" + str(gpib_card) + "::" + str(gpib_address) + "::INSTR"
        self.rm = pyvisa.ResourceManager()
        self.inst = self.rm.open_resource(resource_name)
        self.inst.timeout = timeout
        self.configure_output_format()
        self.enable_auto_zero()
        self.init_config()

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
    def init_config(self, function="TEMP", frtd_type="PT100", nplc=1):
        self.enable_auto_zero()
        self.set_function(function=function, nplc=nplc, frtd_type=frtd_type)

    # =========================
    # SYSTEMS
    # =========================
    def enable_auto_zero(self):
        self.inst.write("SYST:AZER ON")

    # =========================
    # FUNCTION CONFIGURATION
    # =========================

    def set_function(self, function, **kwargs):
        """
        Configura la función de medida y aplica parámetros adicionales.

        :param function: Ej: "VOLT:DC", "TEMP"
        :param kwargs: Parámetros adicionales (nplc=1, range=10, autorange=True, etc.)
        """

        function = function.upper()

        if function not in KEITHLEY_2700_FUNCTIONS:
            raise ValueError(f"Función no válida: {function}")

        # Selección de función
        self.inst.write(f"SENS:FUNC '{function}'")

        # Aplicar parámetros adicionales
        if kwargs:
            self._apply_function_settings(function, **kwargs)

    def _apply_function_settings(self, function, **kwargs):
        """
        Aplica parámetros SCPI a una función concreta
        """

        for key, value in kwargs.items():
            key_lower = key.lower()

            if key_lower not in PARAM_MAP:
                raise ValueError(f"Parámetro no soportado: {key}")

            scpi_cmd = PARAM_MAP[key_lower]

            # Booleanos → ON/OFF
            if isinstance(value, bool):
                value = "ON" if value else "OFF"

            self.inst.write(f"SENS:{function}:{scpi_cmd} {value}")

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

    def get_measure_function(self, clear_buffer=True):
        if clear_buffer: self.inst.write("*CLS")
        response = self.inst.query(":SENS:FUNC?")
        function = response.strip().replace('"', '')
        return function

    # =========================
    # FILTER (simple)
    # =========================
    def enable_averaging(self, function='TEMP', count=5, tcontrol='REP', window=None):
        if function not in KEITHLEY_2700_FUNCTIONS:
            raise ValueError(f"Función no válida: {function}")

        if function not in SUPPORTED_AVG:
            raise ValueError(f"Averaging no soportado para: {function}")

        self.inst.write(f"SENS:{function}:AVER:STAT ON")
        self.inst.write(f"SENS:{function}:AVER:COUN {count}")

        # Tipo de control (REP o MOV)
        if tcontrol is not None:
            tcontrol = tcontrol.upper()
            if tcontrol not in SUPPORTED_TCON:
                raise ValueError(f"TCON inválido: {tcontrol} (usa REP o MOV)")

            self.inst.write(f"SENS:{function}:AVER:TCON {tcontrol}")

        # Window solo tiene sentido con MOV
        if window is not None:
            if tcontrol != "MOV":
                raise ValueError("WINDOW solo es válido cuando TCON = MOV")

            self.inst.write(f"SENS:{function}:AVER:WIND {window}")

    def disable_averaging(self, function):
        if function not in KEITHLEY_2700_FUNCTIONS:
            raise ValueError(f"Función no válida: {function}")

        if function not in SUPPORTED_AVG:
            raise ValueError(f"Averaging no soportado para: {function}")

        self.inst.write(f"SENS:{function}:AVER:STAT OFF")


    # =========================
    # CLOSE
    # =========================
    def close(self):
        self.inst.close()