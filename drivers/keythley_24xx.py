import re

from drivers.SCPIInstrument import SCPIInstrument, SUPPORTED_FUNCTIONS, SUPPORTED_TCON, \
    SUPPORTED_TEMPERATURE_TRANSDUCERS, SUPPORTED_TCOUPLES, SUPPORTED_FRTDS
from models.configuration_models import SourceMeterConfig


# =========================
# CONSTANTS
# =========================

# =========================
# STATIC FUNCTIONS
# =========================

def parse_reading(raw):
    # TODO: Adaptar al 24xx o usar el del 2700 si se puede
    """
    Parse a raw measurement string returned by the Keithley 2400 into a structured dictionary.

    The Keithley 2400 can return measurement data in different formats depending on the
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
            - "value" (float): Measured value (e.g., voltage in Volts)
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


class Keithley24xx(SCPIInstrument):
    """
    Driver for Keithley 24xx SourceMeter instruments (e.g., 2400 series).

    Version
    -------
    1.0

    Overview
    --------
    This class provides a high-level, Pythonic interface for controlling
    Keithley 24xx SourceMeter instruments via SCPI over GPIB.

    It abstracts low-level SCPI commands into a consistent API for configuring
    source and measurement (sense) functions, ranges, levels, compliance limits,
    and acquisition parameters.

    The design follows a clear separation between:
        - Source (SOUR): signal generation (voltage or current)
        - Sense (SENS): measurement configuration (voltage, current, etc.)

    Key Features
    ------------
    - Unified API for source configuration:
        - set_source_mode()
        - set_source_level() / get_source_level()
        - set_source_range() / get_source_range()

    - Unified API for measurement configuration:
        - set_sense_function() / get_sense_function()
        - set_measure_range() / get_measure_range()
        - set_sense_compliance() / get_sense_compliance()
        - set_nplc() / get_nplc()

    - Automatic behavior:
        - Setting source mode automatically configures a typical sense function:
            VOLT → CURR:DC
            CURR → VOLT:DC

    - Output configuration:
        - configure_output_format()
        - parse_reading() helper for structured data extraction

    - Measurement utilities:
        - read() returns parsed measurement data
        - Averaging support (enable_averaging / disable_averaging)

    Design Principles
    -----------------
    - Minimal abstraction over SCPI (transparent mapping)
    - No unnecessary restrictions on valid instrument configurations
    - No caching (v1.0) to ensure state always reflects real instrument
    - Consistent naming and symmetry between source and measure APIs
    - Safe defaults aligned with common lab workflows (I-V measurements)

    Notes
    -----
    - This driver assumes exclusive control of the instrument.
      External changes (front panel or other software) are not tracked.

    - Measurement range and compliance are not artificially restricted.
      The instrument is allowed to handle overloads or compliance conditions.

    - Output parsing is tolerant to multiple formats but may need adaptation
      depending on FORM:ELEM configuration.

    Typical Usage
    -------------
    # >>> inst = Keithley24xx(gpib_address=22)
    # >>> inst.init_config()
    # >>> inst.set_source_mode("VOLT")
    # >>> inst.set_source_range(10)
    # >>> inst.set_source_level(5)
    # >>> inst.set_sense_compliance(0.01)
    # >>> inst.set_output(True)
    # >>> reading = inst.read()

    Example (I-V measurement)
    ------------------------
    # >>> inst.set_source_mode("VOLT")      # Source voltage
    # >>> inst.set_sense_function("CURR:DC") # Measure current
    # >>> inst.set_measure_range("AUTO")
    # >>> inst.set_source_level(1.0)
    # >>> inst.set_output(True)
    # >>> print(inst.read())

    Limitations (v1.0)
    -----------------
    - No caching of instrument state (performance not optimized)
    - Limited validation of cross-parameter consistency
    - Partial support for advanced features (trigger model, trace buffer, etc.)
    - parse_reading() may require adaptation for specific configurations

    Future Improvements
    -------------------
    - Optional caching layer for performance optimization
    - High-level measurement workflows (e.g., IV sweeps)
    - Enhanced error handling and status monitoring
    - Full support for trigger and buffer subsystems

    Dependencies
    ------------
    - SCPIInstrument base class
    - PyVISA-compatible backend (via SCPIInstrument)
    """

    def __init__(self, gpib_card=0, gpib_address=16, timeout=10000):
        resource_name = "GPIB" + str(gpib_card) + "::" + str(gpib_address) + "::INSTR"
        super().__init__(resource_name, timeout)
        self._source_mode = None  # cache interna

    # =========================
    # CONFIG
    # =========================

    def enable_incognito_mode(self, enable_beeper=False, enable_display=False):
        self.enable_beeper(enable=enable_beeper)
        self.enable_display(enable=enable_display)

    def init_config(self):
        self.reset()
        self.wait_opc()
        self.clear()
        self.wait_opc()
        self.enable_incognito_mode(enable_beeper=False, enable_display=True)
        self.configure_output_format()
        self.enable_auto_zero()

    def configure(self, cfg: SourceMeterConfig):
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

    # ========================= =========================
    # CALCulate commands
    # ========================= =========================

    # ========================= =========================
    # DISPlay commands
    # ========================= =========================

    def enable_display(self, enable=True):
        return self.write_scpi(subsystem="DISP", function="ENAB", value=enable)

    def set_display_resolution(self, n_digits=6):
        """
        Set the measurement resolution (number of digits) for the active function.

        This method configures the number of digits used by the instrument for
        measurements, affecting resolution and indirectly measurement speed.

        Args:
            n_digits (int):
                Number of digits for measurement resolution (e.g., typically 4–7
                depending on instrument capabilities). Higher values increase
                resolution but may slow down measurements.

        Returns:
            Any:
                Result returned by `write_scpi`.

        Side Effects:
            - Updates the resolution setting (`DIG`) for the active measurement function.

        Notes:
            - The valid range of `n_digits` depends on the instrument model.
            - Increasing resolution does not necessarily improve accuracy if NPLC
              is low; integration time typically has a greater impact on noise reduction.
        """
        return self.write_scpi(subsystem="DISP",
                               function="DIG",
                               value=n_digits)

    def get_display_resolution(self):
        """
        Get the measurement resolution (number of digits) for the active function.

        This method queries the instrument for the current resolution setting,
        expressed as the number of digits used in the measurement.

        Returns:
            Any:
                Current resolution (number of digits) as returned by the instrument.

        Notes:
            - Useful for verifying precision and speed trade-offs in measurements.
        """
        return self.query_scpi(subsystem="SENS",
                               function="DIG")

    # ========================= =========================
    # FORMat commands
    # ========================= =========================

    def configure_output_format(
            self,
            voltage=True,
            current=False,
            resistance=False,
            time=False,
            status=False
    ):
        """
        Configure the output data format of the instrument.

        This method defines which measurement elements are included in the data
        returned by the instrument using the SCPI `FORM:ELEM` command.

        Parameters
        ----------
        voltage : bool, optional
            Include measured voltage ("VOLT") in the output data. Default is True.
        current : bool, optional
            Include measured current ("CURR") in the output data. Default is False.
        resistance : bool, optional
            Include calculated resistance ("RES") in the output data. Default is False.
        time : bool, optional
            Include timestamp ("TIME") in the output data. Default is False.
        status : bool, optional
            Include measurement status ("STAT") in the output data. Default is False.

        Returns
        -------
        Any
            The response returned by the underlying SCPI write operation.

        Raises
        ------
        ValueError
            If no output elements are selected.

        Notes
        -----
        The selected elements determine the structure and order of the data returned
        by the instrument during measurement queries (e.g., `READ?` or `FETCH?`).
        Ensure that the parsing logic matches the configured output format.

        Examples
        --------
        Configure voltage and current output:

        instrument.configure_output_format(voltage=True, current=True)

        Configure full output including time and status:

        instrument.configure_output_format(
        ...     voltage=True,
        ...     current=True,
        ...     resistance=True,
        ...     time=True,
        ...     status=True
        ... )
        """
        elements = []

        if voltage:
            elements.append("VOLT")
        if current:
            elements.append("CURR")
        if resistance:
            elements.append("RES")
        if time:
            elements.append("TIME")
        if status:
            elements.append("STAT")

        if not elements:
            raise ValueError("At least one output element must be selected")

        value = ",".join(elements)
        return self.write_scpi(subsystem="FORM", function="ELEM", value=value)

    # ========================= =========================
    # OUTPut commands
    # ========================= =========================
    def set_output(self, on=True):
        return self.write_scpi(subsystem="OUTP",
                               function="STAT",
                               value=on)

    def get_output_status(self):
        return self.query_scpi(subsystem="OUTP",
                               function="STAT")

    # ========================= =========================
    # ROUTe commands
    # ========================= =========================
    def set_output_route(self, route="FRONT"):
        """
        Set the output terminal routing of the instrument.

        This method configures which output terminals are used for signal routing
        (e.g., front or rear terminals) by sending the appropriate SCPI command.

        Parameters
        ----------
        route : str, optional
            Output route selection. Common values are:
            - "FRONT": Use the front panel terminals
            - "REAR": Use the rear panel terminals
            Default is "FRONT".

        Returns
        -------
        Any
            The response returned by the underlying SCPI write operation.

        Notes
        -----
        Ensure that the selected route matches the physical connections on the instrument
        to avoid measurement errors or incorrect signal routing.
        """
        return self.write_scpi(subsystem="ROUT",
                               function="TERM",
                               value=route)

    # ========================= =========================
    # SENSe commands
    # ========================= =========================

    def set_nplc(self, nplc=1.0):
        # TODO: Testear
        """
        Set the integration time in Number of Power Line Cycles (NPLC).

        This method configures the measurement integration time for the active
        function. NPLC controls the trade-off between measurement speed and noise
        rejection: higher values improve accuracy but increase measurement time.

        Args:
            nplc (float):
                Integration time expressed in power line cycles (e.g., 0.1, 1, 10).
                Typical values depend on the instrument and measurement function.

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
                               function=f"{self.get_sense_function()}:NPLC",
                               value=nplc)

    def get_nplc(self):
        # TODO: Testear
        """
        Get the integration time (NPLC) for the active measurement function.

        This method queries the instrument for the current NPLC setting, which
        defines the measurement integration time in power line cycles.

        Returns:
            Any:
                Current NPLC value as returned by the instrument.

        Notes:
            - Uses the active function from `get_function()`.
            - Useful for verifying measurement speed vs. accuracy configuration.
        """
        return self.query_scpi(subsystem="SENS",
                               function=f"{self.get_sense_function()}:NPLC")

    def set_sense_function(self, function: str):
        """
        Set measurement (sense) function on the instrument.

        Parameters
        ----------
        function : str
            One of:
                "VOLT:DC", "VOLT:AC",
                "CURR:DC", "CURR:AC",
                "RES", "FRES",
                "TEMP",
                "FREQ", "PER",
                "CONT"

        Returns
        -------
        Any
            The response returned by the underlying SCPI write operation.

        Raises
        ------
        ValueError
            If the provided function is not supported.
        """

        function = function.upper()

        if function not in SUPPORTED_FUNCTIONS:
            raise ValueError(f"Función no válida: {function}")

        return self.write_scpi(
            subsystem="SENS",
            function="FUNC",
            value=function,
            quoted=True
        )

    def get_sense_function(self):
        """
        Get the active sense function.

        This method queries the instrument to retrieve the currently configured
        measurement function (e.g., "VOLT:DC", "CURR:DC", "RES", "TEMP") and
        returns it as a clean string without SCPI formatting.

        Args:

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
        response = self.query_scpi(subsystem="SENS", function="FUNC")
        function = response.strip().replace('"', '')
        return function

    def get_sense_compliance(self):
        """
        Get the compliance (protection limit) based on the active source mode.

        Returns
        -------
        float
            Compliance value (in amperes if sourcing voltage, or volts if sourcing current).

        Raises
        ------
        ValueError
            If the source mode is not supported.
        """

        source_mode = self.get_source_mode()

        if source_mode == "VOLT":
            # Compliance es corriente
            return float(
                self.query_scpi(
                    subsystem="SENS",
                    function="CURR:PROT"
                )
            )

        elif source_mode == "CURR":
            # Compliance es tensión
            return float(
                self.query_scpi(
                    subsystem="SENS",
                    function="VOLT:PROT"
                )
            )

        else:
            raise ValueError(
                f"Invalid source mode '{source_mode}', expected 'VOLT' or 'CURR'."
            )

    def set_sense_compliance(self, value: float):
        """
        Set the compliance (protection limit) based on the active source mode.

        This method sets:
        - Current compliance when sourcing voltage
        - Voltage compliance when sourcing current

        Parameters
        ----------
        value : float
            Compliance limit (A or V depending on mode).

        Returns
        -------
        Any
            The response returned by the underlying SCPI write operation.

        Raises
        ------
        TypeError
            If the provided value is not numeric.
        ValueError
            If the source mode is not supported.
        """

        if not isinstance(value, (float, int)):
            raise TypeError(f"Compliance must be a float, got {type(value)}")

        source_mode = self.get_source_mode()

        if source_mode == "VOLT":
            return self.write_scpi(
                subsystem="SENS",
                function="CURR:PROT",
                value=float(value)
            )

        elif source_mode == "CURR":
            return self.write_scpi(
                subsystem="SENS",
                function="VOLT:PROT",
                value=float(value)
            )

        else:
            raise ValueError(
                f"Invalid source mode '{source_mode}', expected 'VOLT' or 'CURR'."
            )

    def set_sense_range(self, value):
        """
        Set the measurement range based on the active sense function.

        This method configures the measurement range using the SCPI
        `SENS:<FUNC>:RANG` command or enables auto-ranging.

        Parameters
        ----------
        value : float or str
            Range value (in appropriate units), or "AUTO" to enable auto-ranging.

        Returns
        -------
        Any
            The response returned by the underlying SCPI write operation.

        Raises
        ------
        TypeError
            If the provided value is neither numeric nor "AUTO".
        ValueError
            If the measurement function is unsupported.
        """

        quantity = self.get_sense_function().split(":")[0].upper()

        if quantity not in ("CURR", "VOLT"):
            raise ValueError(
                f"Range setting not supported for measurement function '{quantity}'"
            )

        # --- AUTO ---
        if isinstance(value, str):
            if value.strip().upper() == "AUTO":
                return self.write_scpi(
                    subsystem="SENS",
                    function=f"{quantity}:RANG:AUTO",
                    value="ON"
                )
            else:
                raise TypeError(f"Invalid string value for range: {value}")

        # --- NUMÉRICO ---
        if isinstance(value, (float, int)):
            return self.write_scpi(
                subsystem="SENS",
                function=f"{quantity}:RANG",
                value=float(value)
            )

        raise TypeError(f"Range must be float or 'AUTO', got {type(value)}")

    def get_sense_range(self):
        """
        Get the measurement range based on the active sense function.

        Returns
        -------
        float or str
            The current measurement range value, or "AUTO" if auto-ranging is enabled.

        Raises
        ------
        ValueError
            If the measurement function is unsupported.
        """

        # Obtener función activa (ej: "VOLT:DC" → "VOLT")
        quantity = self.get_sense_function().split(":")[0].upper()

        if quantity not in ("CURR", "VOLT"):
            raise ValueError(
                f"Range not supported for measurement function '{quantity}'"
            )

        # Comprobar si está en AUTO
        auto = self.query_scpi(
            subsystem="SENS",
            function=f"{quantity}:RANG:AUTO"
        ).strip().upper()

        if auto == "ON":
            return "AUTO"

        # Si no está en AUTO, devolver valor numérico
        return float(
            self.query_scpi(
                subsystem="SENS",
                function=f"{quantity}:RANG"
            )
        )

    # ========================= =========================
    # SOURce commands
    # ========================= =========================
    def set_source_mode(self, mode="VOLT"):
        """
        Set the source function mode of the instrument.

        Additionally, configures a default sense function:
        - VOLT → CURR:DC
        - CURR → VOLT:DC

        Parameters
        ----------
        mode : str
            "VOLT" or "CURR"

        Returns
        -------
        Any
            The response returned by the underlying SCPI write operation.

        Raises
        ------
        ValueError
            If the mode is invalid.
        """

        mode = mode.strip().upper()

        if mode not in ("VOLT", "CURR"):
            raise ValueError(f"Invalid source mode: {mode}. Expected 'VOLT' or 'CURR'.")

        # 🔹 Configurar source
        result = self.write_scpi(
            subsystem="SOUR",
            function="FUNC:MODE",
            value=mode
        )

        # 🔥 actualizar cache
        self._source_mode = mode

        # 🔹 Configurar sense por defecto (comportamiento típico)
        if mode == "VOLT":
            self.set_sense_function("CURR:DC")
        elif mode == "CURR":
            self.set_sense_function("VOLT:DC")

        return result

    def get_source_mode(self, refresh=False):
        """
        Get the current source mode, using cache when possible.

        Parameters
        ----------
        refresh : bool, optional
            If True, force a query to the instrument. Default is False.

        Returns
        -------
        str
            Source mode ("VOLT" or "CURR").
        """
        if self._source_mode is None or refresh:
            response = self.query_scpi(subsystem="SOUR", function="FUNC:MODE")
            self._source_mode = response.strip().upper()

        return self._source_mode

    def set_source_level(self, value: float):
        """
        Set the source level (voltage or current) based on the active source mode.
        """

        if not isinstance(value, (float, int)):
            raise TypeError(f"Source level must be a float, got {type(value)}")

        source_mode = self.get_source_mode()

        if source_mode not in ("VOLT", "CURR"):
            raise ValueError(
                f"Invalid source mode '{source_mode}', expected 'VOLT' or 'CURR'."
            )

        level = float(value)

        # 🔎 Validación contra rango usando función reutilizable
        range_value = self.get_source_range()

        if range_value != "AUTO":
            if abs(level) > range_value:
                raise ValueError(
                    f"{source_mode} level ({level}) exceeds configured range ({range_value})"
                )

        return self.write_scpi(
            subsystem="SOUR",
            function=f"{source_mode}",
            value=level
        )

    def get_source_level(self):
        """
        Get the source level (voltage or current) based on the active source mode.

        Returns
        -------
        float
            Source level (in volts if sourcing voltage, or amperes if sourcing current).

        Raises
        ------
        ValueError
            If the source mode is not supported.
        """

        source_mode = self.get_source_mode()

        if source_mode not in ("VOLT", "CURR"):
            raise ValueError(
                f"Invalid source mode '{source_mode}', expected 'VOLT' or 'CURR'."
            )

        return float(
            self.query_scpi(
                subsystem="SOUR",
                function=f"{source_mode}"
            )
        )

    def set_source_range(self, value):
        """
        Set the source range (voltage or current) based on the active source mode.

        This method configures the source range using the SCPI
        `SOUR:<MODE>:RANG` command or enables auto-ranging with
        `SOUR:<MODE>:RANG:AUTO ON`, where <MODE> is "VOLT" or "CURR".

        Parameters
        ----------
        value : float or str
            Range to be set (in volts or amperes depending on mode),
            or "AUTO" to enable auto-ranging.

        Returns
        -------
        Any
            The response returned by the underlying SCPI write operation.

        Raises
        ------
        TypeError
            If the provided value is neither numeric nor "AUTO".
        ValueError
            If the current source mode is not supported.
        """

        source_mode = self.get_source_mode()

        # 🔒 Solo soportamos VOLT y CURR
        if source_mode not in ("VOLT", "CURR"):
            raise ValueError(
                f"Invalid source mode '{source_mode}', expected 'VOLT' or 'CURR'."
            )

        if isinstance(value, str):
            if value.strip().upper() == "AUTO":
                return self.write_scpi(
                    subsystem="SOUR",
                    function=f"{source_mode}:RANG:AUTO",
                    value="ON"
                )
            else:
                raise TypeError(f"Invalid string value for range: {value}")

        if isinstance(value, (float, int)):
            return self.write_scpi(
                subsystem="SOUR",
                function=f"{source_mode}:RANG",
                value=float(value)
            )

        raise TypeError(f"Range must be float or 'AUTO', got {type(value)}")

    def get_source_range(self):
        """
        Get the configured source range.

        Returns
        -------
        float or str
            The current source range value, or "AUTO" if auto-ranging is enabled.

        Raises
        ------
        ValueError
            If the source mode is not supported.
        """

        source_mode = self.get_source_mode()

        if source_mode not in ("VOLT", "CURR"):
            raise ValueError(
                f"Invalid source mode '{source_mode}', expected 'VOLT' or 'CURR'."
            )

        auto = self.query_scpi(
            subsystem="SOUR",
            function=f"{source_mode}:RANG:AUTO"
        ).strip().upper()

        if auto == "ON":
            return "AUTO"

        range_value = float(
            self.query_scpi(
                subsystem="SOUR",
                function=f"{source_mode}:RANG"
            )
        )

        return range_value

    def _require_source_mode(self, expected: str):
        """
        Ensure the instrument is in the expected source mode.

        Parameters
        ----------
        expected : str
            Expected source mode ("VOLT" or "CURR").

        Raises
        ------
        ValueError
            If the current source mode does not match the expected one.
        """
        mode = self.get_source_mode()
        if mode != expected:
            raise ValueError(
                f"Invalid source mode '{mode}', expected '{expected}'."
            )

    # ========================= =========================
    # STATus commands
    # ========================= =========================

    # ========================= =========================
    # SYSTem commands
    # ========================= =========================
    def enable_beeper(self, enable=True):
        return self.write_scpi(subsystem="SYST", function="BEEP:STAT", value=enable)

    def enable_auto_zero(self, enable=True):
        return self.write_scpi(subsystem="SYST", function="AZER:STAT", value=enable)

    # ========================= =========================
    # TRACe commands
    # ========================= =========================

    # ========================= =========================
    # Trigger commands
    # ========================= =========================

    # =========================
    # MEASURE
    # =========================
    def read(self):
        reading = parse_reading(self.query("READ?"))
        self.wait_opc()
        return reading

    # =========================
    # FILTER (simple)
    # =========================
    def enable_averaging(self, count=5, tcontrol='REP'):
        """
        Enable and configure measurement averaging for the active function.

        This method activates the averaging feature of the current measurement
        function and configures its parameters, including the number of samples,
        averaging control type, and optional window size.

        The averaging is applied using the SCPI commands corresponding to the
        currently active function (e.g., VOLT, CURR).

        Args:
            count (int):
                Number of readings to average. Must be a positive integer.
                Higher values improve noise reduction but increase measurement time.

            tcontrol (str):
                Averaging control type:
                    - 'REP' (Repeat): Averages a fixed number of readings per trigger.
                    - 'MOV' (Moving): Applies a moving average over a sliding window.
                Case-insensitive.

        Raises:
            ValueError:
                - If `tcontrol` is not one of the supported values ('REP', 'MOV').

        Side Effects:
            - Enables averaging for the active measurement function.
            - Configures averaging count (`AVER:COUN`).
            - Sets averaging control mode (`AVER:TCON`).

        Notes:
            - The active measurement function is obtained via `get_function()`.
            - This configuration persists until changed or disabled explicitly.
            - Moving averaging ('MOV') is typically used for smoothing continuous
              measurements, while repeat averaging ('REP') is more deterministic
              for discrete measurements.

        Example:
            inst.enable_averaging(count=10, tcontrol='MOV')
        """
        actual_function = self.get_sense_function()

        self.write_scpi(subsystem="SENS", function=f"{actual_function}:AVER:STAT", value="ON")
        self.write_scpi(subsystem="SENS", function=f"{actual_function}:AVER:COUN", value=count)

        # Tipo de control (REP o MOV)
        if tcontrol is not None:
            tcontrol = tcontrol.upper()
            if tcontrol not in SUPPORTED_TCON:
                raise ValueError(f"TCON inválido: {tcontrol} (usa REP o MOV)")
            self.write_scpi(subsystem="SENS", function=f"{actual_function}:AVER:TCON", value=tcontrol)

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
        return self.write_scpi(subsystem="SENS", function=f"{self.get_sense_function()}:AVER:STAT", value="OFF")


def main():
    k24xx = Keithley24xx(gpib_address=22)
    k24xx.wait_opc()
    k24xx.enable_incognito_mode()
    print(k24xx.idn())
    k24xx.set_nplc(1)
    print(k24xx.get_nplc())
    k24xx.set_output_route("FRONT")
    print(k24xx.get_sense_function())
    k24xx.configure_output_format(voltage=True, current=True)
    k24xx.set_source_mode(mode="VOLT")
    k24xx.set_source_range(10)
    k24xx.set_source_level(5)
    k24xx.get_source_level()
    k24xx.set_sense_compliance(1)


    k24xx.set_output(on=True)
    print(k24xx.read())
    print(k24xx.read())


if __name__ == "__main__":
    main()
