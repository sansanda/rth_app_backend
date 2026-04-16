import re
import time
from typing import Any

from drivers.SCPIInstrument import SCPIInstrument, SUPPORTED_FUNCTIONS, SUPPORTED_TCON, \
    SUPPORTED_TEMPERATURE_TRANSDUCERS, SUPPORTED_TCOUPLES, SUPPORTED_FRTDS
from interfaces.temperature_reader import TemperatureReader
from models.configuration_models import MultimeterConfig


# =========================
# CONSTANTS
# =========================

# =========================
# STATIC FUNCTIONS
# =========================

def parse_reading(raw):
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


def parse_channel_list(value):
    """
    Parse a SCPI-style channel list string into a list of integers.

    This function converts strings such as:
        "1,2,3"
        "1, 2, 3"
        "(@101,102,103)"
        "@101,102"
    into a Python list of integers:
        [1, 2, 3]
        [101, 102, 103]

    Args:
        value (str | list[int] | None):
            Input value to parse. Can be:
                - A SCPI string with channels
                - A list of integers (returned as-is)
                - None (returns empty list)

    Returns:
        list[int]:
            List of parsed channel numbers.

    Raises:
        ValueError:
            If the string contains non-numeric values that cannot be converted.

    Notes:
        - Removes SCPI decorations like '@', '(', ')'.
        - Ignores extra spaces and empty elements.
        - Safe to use with instrument responses like "(@101,102,103)".
    """
    if value is None:
        return []

    if isinstance(value, list):
        return value

    if not isinstance(value, str):
        raise ValueError(f"Unsupported type for channel parsing: {type(value)}")

    # Clean SCPI formatting
    cleaned = value.strip().replace("@", "").replace("(", "").replace(")", "")

    # Split and convert
    result = []
    for item in cleaned.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            result.append(int(item))
        except ValueError:
            raise ValueError(f"Invalid channel value: '{item}'")

    return result


class Keithley2700(SCPIInstrument, TemperatureReader):
    """
    Keithley 2700 instrument driver (version 1.0).

    This class provides a high-level interface to control and interact with
    a Keithley 2700 multimeter/switch system using SCPI commands.

    It extends the `SCPIInstrument` base class, inheriting generic SCPI
    communication capabilities and adding instrument-specific functionality
    such as channel routing, temperature measurements, averaging, and
    configuration of measurement parameters.

    Features:
        - Channel control (open/close, monitor, scan)
        - Temperature measurements (FRTD, thermocouples)
        - Measurement configuration (NPLC, resolution, units)
        - Averaging configuration
        - SCPI command abstraction

    Notes:
        - Designed for use with switching modules (e.g., 7700 series).
        - Some SCPI queries (e.g., backplane relays x24/x25) may not behave
          reliably and should be handled with care.
        - Relies on the underlying communication implementation provided by
          `SCPIInstrument` (e.g., GPIB, RS232, USB).

    Version:
        1.0
    """

    def read_temperature(self, channels: Any) -> float:

        self.open_all_channels()
        self.close_channels(channels=chanels + [104, 114, 124, 125])

        k2700.wait_opc()

        self.conn.write(f":ROUT:CLOS (@{channel})")
        self.conn.write(":SENS:FUNC 'TEMP'")
        value = float(self.conn.query(":READ?"))
        return self.read()

    def __init__(self, gpib_card=0, gpib_address=16, timeout=10000):
        resource_name = "GPIB" + str(gpib_card) + "::" + str(gpib_address) + "::INSTR"
        super().__init__(resource_name, timeout)

    # =========================
    # CONFIG
    # =========================

    def enable_scan(self, enable=False):
        """
        Habilita o desabilita el scan del instrumento
        """
        self.write_scpi(subsystem="ROUT", function="SCAN:LSEL", value="INT" if enable else "NONE")

    def enable_incognito_mode(self, enable_beeper=False, enable_display=False):
        self.enable_beeper(enable=enable_beeper)
        self.enable_display(enable=enable_display)

    # TODO: modificar esto, de momento no trabajaremos en modo scan
    def init_config(self):
        self.reset()
        self.wait_opc()
        self.clear()
        self.wait_opc()
        self.enable_incognito_mode(enable_beeper=False, enable_display=True)
        self.enable_scan(enable=False)
        self.configure_output_format()
        self.enable_auto_zero()

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

        self.set_function("TEMP")

        if temp_cfg.sensor:
            self.configure_temperature_transducer(
                transducer=temp_cfg.sensor.type,
                transducer_type=temp_cfg.sensor.subtype
            )

        if temp_cfg.measure.nplc:
            self.set_nplc(nplc=temp_cfg.measure.nplc)

        if temp_cfg.measure.measurement_resolution:
            self.set_measurement_resolution(n_digits=temp_cfg.measure.measurement_resolution)

        if temp_cfg.averaging:
            avg = temp_cfg.averaging

            if avg.enabled:
                self.enable_averaging(
                    count=avg.count,
                    tcontrol=avg.type,
                    window=avg.window
                )
            else:
                self.disable_averaging()

        # -------------------------
        # 3. CHANNELS
        # -------------------------
        # TODO: scan por implmentar
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
        """
        Query the closed/open status of the specified channels.

        This method sends a SCPI query to retrieve the state of the given channels
        using `ROUTE:CLOS:STAT?`. It returns whether each channel is currently
        closed (connected) or open.

        Args:
            channels (list[int] | None):
                List of channel numbers to query. If None, the instrument behavior
                depends on its default configuration.

        Returns:
            Any:
                Response returned by the instrument. Typically indicates the open/closed
                state of the queried channels, but the exact format depends on the
                instrument configuration and SCPI response parsing.

        Limitations:
            - This query does NOT work reliably for backplane relays (channels x24 and x25).
            - When querying channels such as 124, 125, 224, 225, etc., the instrument
              may return incorrect values or not reflect the real relay state.

        Side Effects:
            - Executes a SCPI query with debug enabled.

        Notes:
            - Uses `query_scpi` with subsystem "ROUTE" and function "CLOS:STAT".
            - Be cautious when relying on this method for validation of relay states
              involving backplane connections.

        Example:
            inst.are_channels_closed([101, 102])
        """
        response = self.query_scpi(subsystem="ROUTE", function="CLOS:STAT", channels=channels, debug=True)
        return [int(x.strip()) for x in response.split(",") if x.strip()]

    def get_closed_channels(self):
        """
        Retrieve the list of currently closed channels.

        This method sends a SCPI query (`ROUTE:CLOS?`) to obtain the channels
        that are currently closed (i.e., relays in the connected state).

        Returns:
            Any:
                Response returned by the instrument, typically a list or string
                representing the closed channels (e.g., "(@101,102)"), depending
                on the instrument configuration and parsing logic.

        Limitations:
            - Backplane relays (channels x24 and x25) may not be correctly reported.
            - Channels such as 124, 125, 224, 225, etc., might be missing or
              inaccurately reflected in the response.

        Side Effects:
            - Executes a SCPI query with debug enabled.

        Notes:
            - Uses `query_scpi` with subsystem "ROUTE" and function "CLOS".
            - This method is useful for general relay state inspection, but should
              not be fully trusted when backplane relays are involved.

        Example:
            inst.get_closed_channels()
        """
        return self.query_scpi(subsystem="ROUTE", function="CLOS", debug=True)

    # ========================= =========================
    # SENSe commands
    # ========================= =========================

    def set_nplc(self, nplc=1.0, channel_list=None):
        """
        Set the integration time in Number of Power Line Cycles (NPLC).

        This method configures the measurement integration time for the active
        function. NPLC controls the trade-off between measurement speed and noise
        rejection: higher values improve accuracy but increase measurement time.

        Args:
            nplc (float):
                Integration time expressed in power line cycles (e.g., 0.1, 1, 10).
                Typical values depend on the instrument and measurement function.

            channel_list (list[int] | None):
                Optional list of channels to apply the setting to. If None, applies
                to the active channel or global configuration depending on the instrument.

        Returns:
            Any:
                Result returned by `write_scpi`.

        Side Effects:
            - Updates the NPLC setting for the active measurement function.

        Notes:
            - The active function is obtained via `get_function()`.
            - Higher NPLC values improve noise rejection (especially 50/60 Hz),
              but slow down measurements.
        """
        return self.write_scpi(subsystem="SENS",
                               function=f"{self.get_function()}:NPLC",
                               value=nplc,
                               channels=channel_list)

    def get_nplc(self, channel_list=None):
        """
        Get the integration time (NPLC) for the active measurement function.

        This method queries the instrument for the current NPLC setting, which
        defines the measurement integration time in power line cycles.

        Args:
            channel_list (list[int] | None):
                Optional list of channels to query. If None, queries the active
                channel or global configuration.

        Returns:
            Any:
                Current NPLC value as returned by the instrument.

        Notes:
            - Uses the active function from `get_function()`.
            - Useful for verifying measurement speed vs. accuracy configuration.
        """
        return self.query_scpi(subsystem="SENS",
                               function=f"{self.get_function()}:NPLC",
                               channels=channel_list)

    def set_measurement_resolution(self, n_digits=6, channel_list=None):
        """
        Set the measurement resolution (number of digits) for the active function.

        This method configures the number of digits used by the instrument for
        measurements, affecting resolution and indirectly measurement speed.

        Args:
            n_digits (int):
                Number of digits for measurement resolution (e.g., typically 4–7
                depending on instrument capabilities). Higher values increase
                resolution but may slow down measurements.

            channel_list (list[int] | None):
                Optional list of channels to apply the setting to. If None, applies
                to the active channel or global configuration depending on the instrument.

        Returns:
            Any:
                Result returned by `write_scpi`.

        Side Effects:
            - Updates the resolution setting (`DIG`) for the active measurement function.

        Notes:
            - The active function is obtained via `get_function()`.
            - The valid range of `n_digits` depends on the instrument model.
            - Increasing resolution does not necessarily improve accuracy if NPLC
              is low; integration time typically has a greater impact on noise reduction.
        """
        return self.write_scpi(subsystem="SENS",
                               function=f"{self.get_function()}:DIG",
                               value=n_digits,
                               channels=channel_list)

    def get_measurement_resolution(self, channel_list=None):
        """
        Get the measurement resolution (number of digits) for the active function.

        This method queries the instrument for the current resolution setting,
        expressed as the number of digits used in the measurement.

        Args:
            channel_list (list[int] | None):
                Optional list of channels to query. If None, queries the active
                channel or global configuration.

        Returns:
            Any:
                Current resolution (number of digits) as returned by the instrument.

        Notes:
            - Uses the active function from `get_function()`.
            - Useful for verifying precision and speed trade-offs in measurements.
        """
        return self.query_scpi(subsystem="SENS",
                               function=f"{self.get_function()}:DIG",
                               channels=channel_list)

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

    def get_function(self, channel_list=None):
        """
        Get the active measurement function.

        This method queries the instrument to retrieve the currently configured
        measurement function (e.g., "VOLT:DC", "CURR:DC", "RES", "TEMP") and
        returns it as a clean string without SCPI formatting.

        Args:
            channel_list (list[int] | None):
                Optional list of channels to query. If None, queries the active
                channel or global configuration depending on the instrument.

        Returns:
            str:
                Active measurement function as a string, without quotes.

        Side Effects:
            - Executes a SCPI query (`SENS:FUNC?`).

        Notes:
            - The raw SCPI response typically includes quotes (e.g., '"VOLT:DC"'),
              which are stripped before returning.
            - This value is widely used internally to build other SCPI commands
              dynamically.
        """
        response = self.query_scpi(subsystem="SENS", function="FUNC", channels=channel_list)
        function = response.strip().replace('"', '')
        return function

    def configure_temperature_transducer(self, transducer='FRTD', transducer_type='PT100', channels=None):
        """
        Configure the temperature transducer type and subtype for measurement.

        This method sets the temperature transducer used by the instrument
        (e.g., thermocouple or RTD) and configures its specific subtype
        (e.g., PT100, type K, etc.) for the selected channels.

        Args:
            transducer (str):
                Type of temperature transducer. Supported values include:
                    - 'TC'   : Thermocouple
                    - 'FRTD' : 4-wire RTD
                Case-insensitive.

            transducer_type (str):
                Specific subtype of the transducer:
                    - For 'TC': thermocouple type (e.g., 'K', 'J', 'T', etc.)
                    - For 'FRTD': RTD type (e.g., 'PT100', 'PT1000', etc.)
                Case-insensitive.

            channels (list[int] | None):
                Optional list of channels to apply the configuration to. If None,
                applies to the active channel or global configuration depending
                on the instrument.

        Raises:
            ValueError:
                - If `transducer_type` or `transducer_subtype` is not a valid string.
                - If `transducer_type` is not supported.
                - If `transducer_subtype` is not valid for the selected type.

        Side Effects:
            - Configures the temperature transducer type (`TEMP:TRAN`).
            - Sets the corresponding subtype:
                - `TEMP:TC:TYPE` for thermocouples
                - `TEMP:FRTD:TYPE` for RTDs

        Notes:
            - Supported values are validated against:
                `SUPPORTED_TEMPERATURE_TRANSDUCERS`,
                `SUPPORTED_TCOUPLES`,
                and `SUPPORTED_FRTDS`.
            - The active measurement function must be set to temperature (`TEMP`)
              for this configuration to be effective.
            - Configuration persists until changed.

        Example:
            inst.configure_temperature_transducer('FRTD', 'PT100', channels=[104,114])
            inst.configure_temperature_transducer('TC', 'K', channels=[101])
        """
        if transducer is None or transducer_type is None:
            raise ValueError(f"Transducer type y transducer subtype deben ser valores str")
        transducer = transducer.upper()
        transducer_type = transducer_type.upper()
        if transducer not in SUPPORTED_TEMPERATURE_TRANSDUCERS:
            raise ValueError(f"Transducer no válido: {transducer}")
        if transducer == "TC" and transducer_type not in SUPPORTED_TCOUPLES:
            raise ValueError(f"Thermocouple no válida: {transducer_type}")
        if transducer == "FRTD" and transducer_type not in SUPPORTED_FRTDS:
            raise ValueError(f"FRTD no válida: {transducer_type}")
        self.write_scpi(subsystem="SENS", function="TEMP:TRAN", value=transducer, channels=channels)
        if transducer == "TC":
            self.write_scpi(subsystem="SENS", function="TEMP:TC:TYPE", value=transducer_type, channels=channels)
        if transducer == "FRTD":
            self.write_scpi(subsystem="SENS", function="TEMP:FRTD:TYPE", value=transducer_type, channels=channels)

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
        """
        Set the measurement unit for the active function.

        This method configures the unit used by the instrument for the current
        measurement function (e.g., Celsius, Fahrenheit, Ohms, Volts, etc.).

        Args:
            unit (str | None):
                Unit to set for the active function. The valid values depend on
                the measurement function (e.g., "C" or "F" for temperature).
                If None, instrument behavior depends on its defaults.

        Returns:
            Any:
                Result returned by `write_scpi`.

        Side Effects:
            - Updates the unit configuration (`UNIT:<function>`) for the active function.

        Notes:
            - The active function is obtained via `get_function()`.
            - Supported units depend on the instrument and selected function.
            - This setting persists until changed.
        """
        return self.write_scpi(subsystem="UNIT", function=self.get_function(), value=unit)

    def get_unit(self, channel_list=None):
        """
        Get the measurement unit for the active function.

        This method queries the instrument for the currently configured unit
        associated with the active measurement function.

        Args:
            channel_list (list[int] | None):
                Optional list of channels to query. If None, queries the active
                channel or global configuration depending on the instrument.

        Returns:
            Any:
                Current unit as returned by the instrument (e.g., "C", "F", "OHM", "V").

        Notes:
            - Uses the active function from `get_function()`.
            - Useful for verifying configuration consistency across channels.
        """
        return self.query_scpi(subsystem="UNIT", function=self.get_function(), channels=channel_list)

    # =========================
    # MEASURE
    # =========================
    def read(self):
        """
        Trigger a measurement on the instrument and return the parsed result.

        This method sends a "READ?" command to the instrument, which initiates
        a measurement and retrieves the result in a single operation. The raw
        response string is then parsed into a structured dictionary using
        `parse_reading`.

        After issuing the query, the method waits for the operation to complete
        by calling `wait_opc()` to ensure synchronization with the instrument.

        Returns:
            dict: Parsed measurement data as returned by `parse_reading`. Possible keys include:
                - "value" (float): Measured value (e.g., temperature, voltage, etc.)
                - "time" (float): Timestamp in seconds (if included in the response)
                - "reading_number" (int): Sequential reading index (if included)

            Example:
                {
                    "value": 29.4759655,
                    "time": 4259.511,
                    "reading_number": 34196
                }

        Raises:
            Exception: Propagates any communication or parsing errors raised by
            `query()` or `parse_reading()`.

        Notes:
            - This method combines triggering and reading in a single command ("READ?").
            - For buffered or previously triggered measurements, consider using "FETCH?"
              instead of "READ?" depending on the measurement strategy.
            - Ensures operation completion using `wait_opc()` before returning.
        """
        reading = parse_reading(self.query("READ?"))
        self.wait_opc()
        return reading

    # =========================
    # FILTER (simple)
    # =========================
    def enable_averaging(self, count=5, tcontrol='REP', window=None | float):
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

            window (float | None):
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
            inst.enable_averaging(count=10, tcontrol='MOV', window=5)
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
    k2700.connect()
    k2700.init_config()

    k2700.set_function(function="TEMP")
    k2700.set_unit(unit="C")
    k2700.set_measurement_resolution(n_digits=5)

    k2700.configure_temperature_transducer(transducer='FRTD', transducer_type='PT100')
    k2700.set_nplc(1)

    k2700.enable_averaging(count=2,
                           tcontrol="REP",
                           window=None)

    k2700.enable_scan(enable=False)
    k2700.open_all_channels()
    k2700.close_channels(channels=[104, 114, 124, 125])

    k2700.wait_opc()
    print(k2700.are_channels_closed(channels=[104, 114, 105, 115]))
    print(k2700.get_closed_channels())

    while True:
        result = k2700.read()
        k2700.wait_opc()
        print(result)
        time.sleep(1)


if __name__ == "__main__":
    main()
