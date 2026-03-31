import pyvisa
from pyvisa import Resource

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

class SCPIInstrument:
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
        self.inst: Resource = self.rm.open_resource(resource_name)
        self.inst.timeout = timeout

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
        if debug:
            print(f"[WRITE] {cmd}")
        self.inst.write(cmd)

    def query(self, cmd: str, debug: bool = False) -> str:
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
        if debug:
            print(f"[QUERY] {cmd}")
        return self.inst.query(cmd)

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
            debug: bool = False
    ):
        """
        Construye y envía un comando SCPI.

        Devuelve el comando generado (útil para debug/testing).
        """
        cmd = get_function_scpi_command(
            subsystem=subsystem,
            function=function,
            value=value,
            channels=channels,
            quoted=quoted
        )

        self.write(cmd, debug=debug)
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

        cmd = get_function_scpi_command(
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
        """Cierra la conexión con el instrumento."""
        self.inst.close()

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

        # 👉 permitir entero
        if isinstance(channels, int):
            channels = [channels]

        # 👉 validar tipo
        if not isinstance(channels, (list, tuple)):
            raise ValueError("channels debe ser int, lista o tupla")

        if not channels:
            raise ValueError("channels no puede estar vacío")

        if not all(isinstance(ch, int) for ch in channels):
            raise ValueError("channels debe contener enteros")

        ch_str = ",".join(str(ch) for ch in channels)

        # ⚠️ SCPI correcto → coma antes de clist
        command += f", (@{ch_str})"

    return command