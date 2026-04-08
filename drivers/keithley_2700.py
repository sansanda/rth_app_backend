import re
import time

from drivers.SCPIInstrument import SCPIInstrument, SUPPORTED_FUNCTIONS, SUPPORTED_TCON, SUPPORTED_AVG, \
    SUPPORTED_TEMPERATURE_TRANSDUCERS, SUPPORTED_TCOUPLES, SUPPORTED_FRTDS
from models.configuration_models import MultimeterConfig, GPIBConfig


# =========================
# CONSTANTS
# =========================

# =========================
# STATIC FUNCTIONS
# =========================

def _parse_reading(raw):
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


class Keithley2700(SCPIInstrument):
    def __init__(self, gpib_card=0, gpib_address=16, timeout=10000):
        resource_name = "GPIB" + str(gpib_card) + "::" + str(gpib_address) + "::INSTR"
        super().__init__(resource_name, timeout)

    # =========================
    # CONFIG
    # =========================
    def read_on_channels(self, channels=None, open_all_channels_after=True):
        channels_to_close = list(channels or [])
        channels_to_close += [124, 125]
        self.close_channels(channels_to_close)
        result = self.read()
        self.wait_opc()
        if open_all_channels_after:
            self.open_all_channels()
        return result

    def enable_scan(self, enable=False):
        """
        Habilita o desabilita el scan del instrumento
        """
        self.write_scpi(subsystem="ROUT", function="SCAN:LSEL", value="INT" if enable else "NONE")

    def enable_incognito_mode(self, enable_beeper=False, enable_display=False):
        self.enable_beeper(enable=enable_beeper)
        self.enable_display(enable=enable_display)

    # TODO: modificar esto, de momento no trabajaremos en modo scan
    def init_config(self, function="TEMP", frtd_type="PT100", nplc=1):
        self.reset()
        self.wait_opc()
        self.clear()
        self.wait_opc()
        self.enable_incognito_mode(enable_beeper=False, enable_display=True)
        self.enable_scan(enable=False)
        self.configure_output_format()
        self.enable_auto_zero()
        self.set_function(function=function)
        self.set_unit(unit="C")
        self.write_scpi(subsystem='SENS', function='TEMP:FRTD:TYPE', value=frtd_type)
        self.write_scpi(subsystem='SENS', function='TEMP:NPLC', value=nplc)

    def configure(self, cfg: MultimeterConfig):
        """
        Apply full multimeter configuration.
        """

        # -------------------------
        # 1. GPIB (CRÍTICO)
        # -------------------------
        gpib_cfg = cfg.gpib

        current_resource = self.inst.resource_name
        new_resource = "GPIB" + str(gpib_cfg.gpib_card) + "::" + str(gpib_cfg.address) + "::INSTR"

        # solo reconectar si cambia dirección
        if current_resource != new_resource:
            self.reconnect(
                resource_name=new_resource,
                timeout_ms=gpib_cfg.timeout_ms
            )
        else:
            # solo actualizar timeout
            self.inst.timeout = gpib_cfg.timeout_ms

        # -------------------------
        # 2. TEMPERATURE
        # -------------------------
        temp_cfg = cfg.temperature

        function = "TEMP"
        self.set_function(function)

        if temp_cfg.sensor:
            self.configure_temperature_transducer(
                transducer_type=temp_cfg.sensor.type,
                transducer_subtype=temp_cfg.sensor.subtype
            )

        if temp_cfg.measure.nplc:
            self.set_nplc(function=function, nplc=temp_cfg.measure.nplc)

        if temp_cfg.measure.measurement_resolution:
            self.set_measurement_resolution(function=function, n_digits=temp_cfg.measure.measurement_resolution)

        if temp_cfg.averaging:
            avg = temp_cfg.averaging

            if avg.enabled:
                self.enable_averaging(
                    function=function,
                    count=avg.count,
                    tcontrol=avg.type,
                    window=avg.window
                )
            else:
                self.disable_averaging(function)

        # -------------------------
        # 3. CHANNELS
        # -------------------------
        #TODO: scan por implmentar
        enabled_channels = [
            ch.channel for ch in temp_cfg.channels.values() if ch.enabled
        ]

        if enabled_channels:
            # self.set_scan_channels(enabled_channels)
            pass

    # ========================= =========================
    # CALCulate commands
    # ========================= =========================

    # ========================= =========================
    # DISPlay commands
    # ========================= =========================

    def enable_display(self, enable=True):
        return self.write_scpi(subsystem="DISP", function="ENAB", value=enable)

    # ========================= =========================
    # FORMat commands
    # ========================= =========================

    def configure_output_format(
            self,
            read=True,
            time=False,
            unit=False,
            status=False,
            channel=False,
            reading_number=False
    ):
        """
        Configura el formato de salida de las lecturas del instrumento mediante
        el comando SCPI `FORM:ELEM`.

        Permite seleccionar qué elementos se incluirán en cada lectura devuelta
        por el equipo (por ejemplo, valor medido, tiempo, unidad, etc.).

        Parámetros
        ----------
        read : bool, opcional
            Incluye el valor de la medida (READ). Por defecto True.
        time : bool, opcional
            Incluye la marca de tiempo de la lectura (TIME). Por defecto False.
        unit : bool, opcional
            Incluye la unidad de la medida (UNIT). Por defecto False.
        status : bool, opcional
            Incluye el estado de la medida (STAT). Por defecto False.
        channel : bool, opcional
            Incluye el canal de adquisición (CHAN). Por defecto False.
        reading_number : bool, opcional
            Incluye el número de lectura (NUM). Por defecto False.

        Excepciones
        -----------
        ValueError
            Se lanza si no se selecciona ningún elemento de salida.

        Notas
        -----
        - El comando generado sigue el formato: `FORM:ELEM <element1>,<element2>,...`
        - El orden de los elementos es el mismo en que se añaden internamente.
        - Esta configuración afecta a cómo se devuelven los datos en lecturas
          posteriores del instrumento.

        Ejemplo
        -------
        configure_output_format(read=True, time=True, unit=True)
        # Envía: FORM:ELEM READ,TIME,UNIT
        """

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

        value = ",".join(elements)
        return self.write_scpi(subsystem="FORM", function="ELEM", value=value)

    # ========================= =========================
    # ROUTe commands
    # ========================= =========================
    def close_channels(self, channels=None, delay=0.1):
        """
        Close (connect) one or more channels on the Keithley 2700 expasion slot determined by the channel number itself.

        This command closes the specified channel(s), allowing the signal
        to pass through the internal multiplexer.

        Parameters:
            channel (int | list[int]):
                Channel number or list of channel numbers to close.
                Example: 101 or [101, 102]

        Notes:
            - SCPI command used: "ROUT:CLOS (@<channel_list>)"
            - Closing a channel connects it to the measurement path.
            - Multiple channels can be closed simultaneously.
            - Ensure channels belong to a valid installed multiplexer card (e.g., 7700).
            :param delay: Wait after close channels
            :param channels: Channel or Channels to close
        """

        if isinstance(channels, list):
            cmd = self.write_scpi(subsystem="ROUT", function="MULT:CLOS", channels=channels)
        else:
            cmd = self.write_scpi(subsystem="ROUT", function="CLOS", channels=channels)
        # wait for relay/s setting
        if delay:
            time.sleep(delay)
        return cmd

    def open_all_channels(self):
        """
        Open (disconnect) all channels on the Keithley 2700 scanner.

        This command opens every channel in the internal multiplexer,
        ensuring no connections remain active.

        Notes:
            - SCPI command used: "ROUT:OPEN:ALL"
            - Typically used to reset the switching state before a new measurement.
            - Recommended before configuring or starting a scan sequence.
        """
        return self.write_scpi(subsystem="ROUT", function="OPEN:ALL")

    def are_channels_closed(self, channels=None):
        #TODO: No funciona
        return self.query_scpi(subsystem="ROUTE", function="MULT:CLOS:STAT", channels=channels, debug=True)

    def get_closed_channels(self):
        return self.query_scpi(subsystem="ROUTE", function="CLOS", debug=True)

    # ========================= =========================
    # SENSe commands
    # ========================= =========================

    def set_nplc(self, function='TEMP:NPLC', nplc=1.0, channel_list=None):
        return self.write_scpi(subsystem="SENS", function=function, value=nplc, channels=channel_list)

    def get_nplc(self, channel_list=None):
        function = self.get_function()
        return self.query_scpi(subsystem="SENS", function=f"{function}:NPLC", channels=channel_list)

    def set_measurement_resolution(self, function='TEMP:DIG', n_digits=6, channel_list=None):
        return self.write_scpi(subsystem="SENS", function=function, value=n_digits, channels=channel_list)

    def get_measurement_resolution(self, channel_list=None):
        function = self.get_function()
        return self.query_scpi(subsystem="SENS", function=f"{function}:DIG", channels=channel_list)

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

        if function not in SUPPORTED_FUNCTIONS:
            raise ValueError(f"Función no válida: {function}")

        return self.write_scpi(subsystem="SENS", function="FUNC", value=function, quoted=True)

    def get_function(self, clear_buffer=True, channel_list=None):
        """
        Retrieve the currently selected measurement function from the Keithley 2700.

        Optionally clears the instrument status and error queue before querying,
        ensuring a clean state.

        Parameters:
            clear_buffer (bool, optional):
                If True, execute clear_status_and_errors() before querying the function.
                This clears the status registers and error queue.
                Default is True.

        Returns:
            str:
                Active measurement function (e.g., "TEMP", "VOLT:DC", "RES", etc.).

        Notes:
            - The function is returned without quotes.
            - The query used is ":SENS:FUNC?".
            - Clearing the buffer is recommended when you want to avoid
              residual errors affecting subsequent operations.
        """
        if clear_buffer: self.clear_status_and_errors()
        response = self.query_scpi(subsystem="SENS", function="FUNC", channels=channel_list)
        function = response.strip().replace('"', '')
        return function

    def configure_temperature_transducer(self, transducer_type='FRTD', transducer_subtype='PT100', channels=None):
        if transducer_subtype is None or transducer_subtype is None:
            raise ValueError(f"Transducer type y transducer subtype deben ser valores str")
        transducer_type = transducer_type.upper()
        transducer_subtype = transducer_subtype.upper()
        if transducer_type not in SUPPORTED_TEMPERATURE_TRANSDUCERS:
            raise ValueError(f"Transducer no válido: {transducer_type}")
        if transducer_type == "TC" and transducer_subtype not in SUPPORTED_TCOUPLES:
            raise ValueError(f"Thermocouple no válida: {transducer_subtype}")
        if transducer_type == "FRTD" and transducer_subtype not in SUPPORTED_FRTDS:
            raise ValueError(f"FRTD no válida: {transducer_subtype}")
        self.write_scpi(subsystem="SENS", function="TEMP:TRAN", value=transducer_type, channels=channels)
        if transducer_type == "TC":
            self.write_scpi(subsystem="SENS", function="TEMP:TC:TYPE", value=transducer_subtype, channels=channels)
        if transducer_type == "FRTD":
            self.write_scpi(subsystem="SENS", function="TEMP:FRTD:TYPE", value=transducer_subtype, channels=channels)

    # ========================= =========================
    # STATus commands
    # ========================= =========================

    # ========================= =========================
    # SYSTem commads
    # ========================= =========================
    def enable_beeper(self, enable=True):
        return self.write_scpi(subsystem="SYST", function="BEEP:STAT", value=enable)

    def enable_auto_zero(self, enable=True):
        return self.write_scpi(subsystem="SYST", function="AZER:STAT", value=enable)

    # ========================= =========================
    # TRACe commads
    # ========================= =========================

    # ========================= =========================
    # Trigger commads
    # ========================= =========================

    # ========================= =========================
    # UNIT commads
    # ========================= =========================
    def set_unit(self, unit=None):
        return self.write_scpi(subsystem="UNIT", function=self.get_function(), value=unit)

    # =========================
    # MEASURE
    # =========================
    def read(self):
        reading = _parse_reading(self.query("READ?"))
        self.wait_opc()
        return reading

    # =========================
    # FILTER (simple)
    # =========================
    def enable_averaging(self, count=5, tcontrol='REP', window=None):
        """
        Enable and configure measurement averaging for the active function.

        This method activates the averaging feature of the current measurement
        function and configures its parameters, including the number of samples,
        averaging control type, and optional window size.

        The averaging is applied using the SCPI commands corresponding to the
        currently active function (e.g., VOLT, CURR, RES, TEMP, etc.).

        Args:
            count (int):
                Number of readings to average. Must be a positive integer.
                Higher values improve noise reduction but increase measurement time.

            tcontrol (str):
                Averaging control type:
                    - 'REP' (Repeat): Averages a fixed number of readings per trigger.
                    - 'MOV' (Moving): Applies a moving average over a sliding window.
                Case-insensitive.

            window (int | None):
                Size of the moving average window. Only valid when `tcontrol='MOV'`.
                If provided with 'REP', a ValueError is raised.

        Raises:
            ValueError:
                - If `tcontrol` is not one of the supported values ('REP', 'MOV').
                - If `window` is provided while `tcontrol` is not 'MOV'.

        Side Effects:
            - Enables averaging for the active measurement function.
            - Configures averaging count (`AVER:COUN`).
            - Sets averaging control mode (`AVER:TCON`).
            - Optionally configures averaging window (`AVER:WIND`).

        Notes:
            - The active measurement function is obtained via `get_function()`.
            - This configuration persists until changed or disabled explicitly.
            - Moving averaging ('MOV') is typically used for smoothing continuous
              measurements, while repeat averaging ('REP') is more deterministic
              for discrete measurements.

        Example:
            >>> inst.enable_averaging(count=10, tcontrol='MOV', window=5)
        """
        actual_function = self.get_function()

        self.write_scpi(subsystem="SENS", function=f"{actual_function}:AVER:STAT", value="ON")
        self.write_scpi(subsystem="SENS", function=f"{actual_function}:AVER:COUN", value=count)

        # Tipo de control (REP o MOV)
        if tcontrol is not None:
            tcontrol = tcontrol.upper()
            if tcontrol not in SUPPORTED_TCON:
                raise ValueError(f"TCON inválido: {tcontrol} (usa REP o MOV)")
            self.write_scpi(subsystem="SENS", function=f"{actual_function}:AVER:TCON", value=tcontrol)

        # Window solo tiene sentido con MOV
        if window is not None:
            if tcontrol != "MOV":
                raise ValueError("WINDOW solo es válido cuando TCON = MOV")
            self.write_scpi(subsystem="SENS", function=f"{actual_function}:AVER:WIND", value=window)

    def disable_averaging(self):
        """
        Disable measurement averaging for the active function.

        This method turns off the averaging feature for the currently active
        measurement function using the corresponding SCPI command.

        Returns:
            Any:
                Result returned by `write_scpi`, depending on its implementation.

        Side Effects:
            - Disables averaging (`AVER:STAT OFF`) for the active measurement function.

        Notes:
            - The active function is obtained via `get_function()`.
            - This only disables averaging; previously configured parameters
              (e.g., count, mode, window) remain stored in the instrument.
        """
        return self.write_scpi(subsystem="SENS", function=f"{self.get_function()}:AVER:STAT", value="OFF")


def main():
    k2700 = Keithley2700(gpib_address=14)
    k2700.init_config()
    k2700.enable_averaging(count=10,
                           tcontrol="REP",
                           window=None)
    k2700.enable_scan(enable=False)
    k2700.open_all_channels()
    k2700.close_channels(channels=[104, 114, 124, 125])
    k2700.wait_opc()
    # print(k2700.are_channels_closed(channels=[104, 114, 124, 125]))


    while True:
        result = k2700.read()
        k2700.wait_opc()
        print(result)
        time.sleep(1)


if __name__ == "__main__":
    main()
