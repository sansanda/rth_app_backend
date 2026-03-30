import re

import pyvisa
import time

from pyvisa import Resource

# =========================
# CONSTANTS
# =========================

# TODO: Continua con la integracion de query, write, scpi
KEITHLEY_2700_FUNCTIONS = {
    "VOLT:DC", "VOLT:AC",
    "CURR:DC", "CURR:AC",
    "RES", "FRES",
    "TEMP",
    "FREQ", "PER",
    "CONT"
}

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


# =========================
# STATIC FUNCTIONS
# =========================

# =========================
# READ AND WRITE SCPI
# =========================

def get_function_scpi_command(
    subsystem: str,
    function: str,
    value=None,
    channels=None,
    quoted: bool = False
):
    """
    Construye comando SCPI genérico.

    Ejemplos:
        SENS:FUNC 'TEMP'
        SENS:TEMP:NPLC 1
        SENS:TEMP:AVER:STAT ON
        SENS:TEMP:NPLC 1, (@101,102)

    :param subsystem: Ej: "SENS"
    :param function: Ej: "FUNC", "TEMP:NPLC", "TEMP:AVER:STAT"
    :param value: Valor opcional (ON/OFF, número, string...)
    :param channels: Lista de canales [101,102]
    :param quoted: Si True, pone comillas en value (ej: 'TEMP')
    """

    if not subsystem:
        raise ValueError("Debes declarar el subsistema")

    if not function:
        raise ValueError("Debes declarar la función")

    subsystem = subsystem.upper()
    function = function.upper()

    command = f"{subsystem}:{function}"

    # ---- VALUE ----
    if value is not None:
        if isinstance(value, bool):
            value = "ON" if value else "OFF"
        else:
            value = str(value)

        if quoted:
            value = f"'{value}'"

        command += f" {value}"

    # ---- CHANNEL LIST ----
    if channels is not None:
        if not isinstance(channels, (list, tuple)):
            raise ValueError("channels debe ser lista o tupla")

        if not channels:
            raise ValueError("channels no puede estar vacío")

        if not all(isinstance(ch, int) for ch in channels):
            raise ValueError("channels debe contener enteros")

        ch_str = ",".join(str(ch) for ch in channels)

        # ⚠️ SCPI correcto → coma antes de clist
        command += f", (@{ch_str})"

    return command

def write_scpi(
    inst: Resource,
    subsystem: str,
    function: str,
    value=None,
    channels=None,
    quoted: bool = False,
    debug: bool = False
):
    cmd = get_function_scpi_command(
        subsystem=subsystem,
        function=function,
        value=value,
        channels=channels,
        quoted=quoted
    )

    if debug:
        print(f"[SCPI WRITE] {cmd}")

    inst.write(cmd)
    return cmd

def query_scpi(
    inst: Resource,
    subsystem: str,
    function: str,
    channels=None,
    debug: bool = False
):
    if not function.endswith("?"):
        function += "?"

    cmd = get_function_scpi_command(
        subsystem=subsystem,
        function=function,
        channels=channels
    )

    if debug:
        print(f"[SCPI QUERY] {cmd}")

    return inst.query(cmd)

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
        """
        Query instrument identification.
        """
        return self.inst.query("*IDN?").strip()

    def reset(self):
        """
        Reset instrument to default state.
        """
        self.inst.write("*RST")

    def clear_status(self):
        """
        Limpia el estado del instrumento.

        - Limpia registros de estado (*CLS)
        - Vacía cola de errores (SYST:ERR?)
        """

        # 1. Clear estándar SCPI
        self.inst.write("*CLS")

        # 2. Vaciar cola de errores completamente
        while True:
            err = query_scpi(self.inst, "SYST", "ERR")
            if err.startswith("0"):
                break

    def get_error(self):
        err = query_scpi(self.inst, "SYST", "ERR")
        code, msg = err.split(",", 1)
        return int(code), msg.strip('"')

    # =========================
    # INIT CONFIG
    # =========================
    #TODO: modificar esto, de momento no trabajaremos en modo scan
    def init_config(self, function="TEMP", frtd_type="PT100", nplc=1):
        self.enable_auto_zero()
        cmd = get_function_scpi_command(subsystem="SENS",
                                        function="FUNC",
                                        value='TEMP')
        self.inst.write(cmd)

    # =========================
    # SYSTEM
    # =========================
    def read_esr(self):
        """
        Lee el Standard Event Status Register (*ESR?).

        Devuelve:
            dict con los bits interpretados
        """

        response = self.inst.query("*ESR?").strip()

        try:
            esr = int(response)
        except ValueError:
            raise RuntimeError(f"Respuesta inválida de ESR: {response}")

        return {
            "raw": esr,
            "operation_complete": bool(esr & 0b00000001),  # OPC
            "request_control": bool(esr & 0b00000010),  # RQC
            "query_error": bool(esr & 0b00000100),  # QYE
            "device_dependent_error": bool(esr & 0b00001000),  # DDE
            "execution_error": bool(esr & 0b00010000),  # EXE
            "command_error": bool(esr & 0b00100000),  # CME
            "user_request": bool(esr & 0b01000000),  # URQ
            "power_on": bool(esr & 0b10000000),  # PON
        }

    def enable_auto_zero(self):
        cmd = get_function_scpi_command(subsystem="SYST",
                                        function="AZER",
                                        value='ON')
        self.inst.write(cmd)


    # =========================
    # SENSE SUBSYSTEM
    # =========================
    # =========================
    # FUNCTION CONFIGURATION
    # =========================

    def set_function(self, function: str):
        """
        Set measurement function on Keithley 2700.

        Parameters:
            function (str): One of:
                "VOLT:DC", "VOLT:AC",
                "CURR:DC", "CURR:AC",
                "RES", "FRES",
                "TEMP",
                "FREQ", "PER",
                "CONT"
        """

        function = function.upper()

        if function not in KEITHLEY_2700_FUNCTIONS:
            raise ValueError(f"Función no válida: {function}")

        self.inst.write(f"SENS:FUNC '{function}'")

    def get_measure_function(self, clear_buffer=True):
        if clear_buffer: self.inst.write("*CLS")
        response = self.inst.query(":SENS:FUNC?")
        function = response.strip().replace('"', '')
        return function

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
        self.open_all_channels()
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
    #TODO: Repasar
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


def main():
    k2700 = Keithley2700()
    k2700.clear_status()
    print(k2700.idn())
    print(k2700.read_esr())
    # cmd = get_function_scpi_command(subsystem="SENS",
    #                                 function="FUNC",
    #                                 value='TEMP',
    #                                 channels=[104, 105])
    # k2700.inst.write(cmd)
    # print(k2700.read_esr())

    # cmd = get_function_scpi_command(subsystem="SENS",
    #                                 function="TEMP:NPLC",
    #                                 value=1,
    #                                 channels=[104, 105])
    #
    # cmd = get_function_scpi_command(subsystem="SENS",
    #                                 function="TEMP:AVER:TCON",
    #                                 value="REP")
    #
    # cmd = get_function_scpi_command(subsystem="SENS",
    #                                 function="TEMP:AVER:COUN",
    #                                 value=2,
    #                                 channels=[104, 105])
    #
    # cmd = get_function_scpi_command(subsystem="SENS",
    #                                 function="TEMP:TRAN",
    #                                 value="FRTD",
    #                                 channels=[104, 105])
    #
    # cmd = get_function_scpi_command(subsystem="SENS",
    #                                 function="TEMP:FRTD:TYPE",
    #                                 value="PT100",
    #                                 channels=[104, 105])

if __name__ == "__main__":
    main()
