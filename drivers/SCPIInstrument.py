import pyvisa
from pyvisa import Resource

from drivers.instrument import Instrument

# =========================
# CONSTANTS
# =========================

SUPPORTED_TEMPERATURE_TRANSDUCERS = {
    "TC", "FRTD", "THER"
}

SUPPORTED_TCOUPLES = {
    "J": "Type J (Iron-Constantan)",
    "K": "Type K (Chromel-Alumel)",
    "T": "Type T (Copper-Constantan)",
    "E": "Type E (Chromel-Constantan)",
    "R": "Type R (Platinum-Rhodium)",
    "S": "Type S (Platinum-Rhodium)",
    "B": "Type B (Platinum-Rhodium)",
    "N": "Type N (Nicrosil-Nisil)"
}

SUPPORTED_FRTDS = {
    "PT100": "Platinum RTD 100Ω",
    "D100": "DIN 100Ω RTD",
    "F100": "IEC 100Ω RTD",
    "PT3916": "Platinum RTD (α = 0.003916)",
    "PT385": "Platinum RTD (α = 0.00385)",
    "USER": "User-defined RTD (requires RZERO, ALPHA, BETA, DELTA)"
}

SUPPORTED_FUNCTIONS = {
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


class SCPIInstrument(Instrument):
    """
    Clase base para instrumentos compatibles con SCPI.

    Proporciona:
    - Gestión de conexión VISA
    - Envío y consulta de comandos SCPI
    - Comandos estándar (*IDN?, *RST, *CLS, etc.)
    - Manejo de errores

    Esta clase está pensada para ser extendida por instrumentos concretos
    (por ejemplo, Keithley2700, Keithley2400, etc.).
    """

    def __init__(self, resource_name: str, timeout: int = 10000):
        """
        Inicializa la conexión con el instrumento.

        Parámetros
        ----------
        resource_name : str
            Dirección VISA (ej: "GPIB0::14::INSTR")
        timeout : int, opcional
            Timeout en milisegundos. Por defecto 10000 ms.
        """
        self.rm = pyvisa.ResourceManager()
        self.inst = None
        self._resource_name = resource_name
        self._timeout = timeout
        self._connected = False

    def connect(self):
        """(Re)connect to the instrument."""
        if self._connected:
            return
        self.inst = self.rm.open_resource(self._resource_name)
        self.inst.timeout = self._timeout
        self._connected = True

    def disconnect(self):
        """Disconnect from instrument."""
        if not self._connected:
            return

        try:
            self.inst.close()
        finally:
            self._connected = False

    def _ensure_connected(self):
        if not self._connected:
            raise RuntimeError("Instrument not connected")

    def reconnect(self, resource_name: str = None, timeout_ms: int = None):
        """
        Reconnect to instrument with optional new parameters.
        """
        self.disconnect()

        if resource_name:
            self._resource_name = resource_name
        if timeout_ms:
            self._timeout = timeout_ms

        self.connect()

    # =========================
    # LOW LEVEL
    # =========================

    def write(self, cmd: str, debug: bool = False):
        """
        Envía un comando al instrumento.

        Parámetros
        ----------
        cmd : str
            Comando SCPI completo.
        debug : bool
            Si True, imprime el comando enviado.
        """
        self._ensure_connected()
        if debug:
            print(f"[WRITE] {cmd}")
        self.inst.write(cmd)

    def query(self, cmd: str, debug: bool = True, debug_response=True) -> str:
        """
        Envía una query al instrumento y devuelve la respuesta.

        Parámetros
        ----------
        cmd : str
            Comando SCPI completo terminado en '?'.
        debug : bool
            Si True, imprime el comando.

        Returns
        -------
        str
            Respuesta del instrumento.
        """
        self._ensure_connected()
        response = self.inst.query(cmd)
        if debug:
            print(f"[QUERY] {cmd}")
        if debug_response:
            print(f"[QUERY_RESPONSE] {response}")
        return response

    # =========================
    # SCPI HELPERS
    # =========================

    def write_scpi(
            self,
            subsystem: str,
            function: str,
            value=None,
            channels=None,
            quoted: bool = False,
            debug: bool = True,
            check_esr: bool = True
    ):
        """
        Construye y envía un comando SCPI.

        Devuelve el comando generado (útil para debug/testing).
        """
        cmd = get_scpi_command(
            subsystem=subsystem,
            function=function,
            value=value,
            channels=channels,
            quoted=quoted
        )

        self.write(cmd, debug=debug)

        if check_esr:
            esr = self.read_esr()
            if esr["command_error"] or esr["execution_error"]:
                raise RuntimeError(f"Error SCPI detectado: {esr} en comando {cmd}")

        return cmd

    def query_scpi(
            self,
            subsystem: str,
            function: str,
            channels=None,
            debug: bool = False
    ) -> str:
        """
        Construye y envía una query SCPI.
        """
        if not function.endswith("?"):
            function += "?"

        cmd = get_scpi_command(
            subsystem=subsystem,
            function=function,
            channels=channels
        )

        return self.query(cmd, debug=debug)

    # =========================
    # STANDARD SCPI
    # =========================

    def idn(self) -> str:
        """Devuelve la identificación del instrumento."""
        return self.query("*IDN?").strip()

    def reset(self):
        """Resetea el instrumento (*RST)."""
        self.write("*RST")

    def clear(self):
        """Clear all messages from Error Queue (*CLS)."""
        self.write("*CLS")

    def clear_status_and_errors(self):
        """
        Limpia el estado del instrumento (*CLS) y vacía la cola de errores.
        """
        self.write("*CLS")

        while True:
            err = self.query_scpi("SYST", "ERR")
            if err.startswith("0"):
                break

    def get_error(self):
        """
        Devuelve el siguiente error del instrumento.

        Returns
        -------
        tuple (int, str)
            Código y mensaje de error.
        """
        err = self.query_scpi("SYST", "ERR")
        code, msg = err.split(",", 1)
        return int(code), msg.strip('"')

    def wait_opc(self):
        """
        Espera a que el instrumento complete la operación (*OPC?).
        """
        self.query("*OPC?")

    def read_esr(self) -> dict:
        """
        Lee el Standard Event Status Register (*ESR?).

        Returns
        -------
        dict
            Diccionario con los bits interpretados.
        """
        response = self.query("*ESR?").strip()

        try:
            esr = int(response)
        except ValueError:
            raise RuntimeError(f"Respuesta inválida de ESR: {response}")

        return {
            "raw": esr,
            "operation_complete": bool(esr & 0b00000001),
            "request_control": bool(esr & 0b00000010),
            "query_error": bool(esr & 0b00000100),
            "device_dependent_error": bool(esr & 0b00001000),
            "execution_error": bool(esr & 0b00010000),
            "command_error": bool(esr & 0b00100000),
            "user_request": bool(esr & 0b01000000),
            "power_on": bool(esr & 0b10000000),
        }

    # =========================
    # CLOSE
    # =========================

    def close(self):
        """Alias for disconnect."""
        self.disconnect()


def get_scpi_command(
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

        # 👉 permitir entero
        if isinstance(channels, int):
            channels = [channels]

        # 👉 validar tipo
        if not isinstance(channels, (list, tuple)):
            raise ValueError("channels debe ser int, lista o tupla")

        ch_str = ""
        if not channels:
            # "Case empty list"
            pass
        elif not all(isinstance(ch, int) for ch in channels):
            raise ValueError("channels debe contener enteros")
        else:
            ch_str = ",".join(str(ch) for ch in channels)

        # ⚠️ SCPI correcto → coma antes de clist
        command += f" (@{ch_str})"

    return command
