import json
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from drivers.keithley_2700 import Keithley2700
from pydantic import BaseModel, Field
from typing import Literal, Optional


app = FastAPI()

DEBUG = True

class AveragingConfig(BaseModel):
    enable: bool = Field(default=True)
    type: Literal["REP", "MOV"] = "REP"
    count: int = Field(default=10, gt=0)
    window: float = Field(default=0.1, gt=0, le=100)

class SensorConfig(BaseModel):
    type: str  # "TC", "FRTD", "THER"
    subtype: str  # "K", "PT100", "5000", etc.

class TemperatureConfigRequest(BaseModel):
    nplc: Optional[float] = Field(default=None, gt=0)
    averaging: Optional[AveragingConfig] = None
    sensor: Optional[SensorConfig] = None

# init una vez (solo si no estás en debug)
@app.on_event("startup")
def startup_event():
    # config por defecto (si quieres mantenerla)
    cfg_dict = load_default_config()["multimeter_setup"]["temperature"]
    cfg = TemperatureConfigRequest(**cfg_dict)

    if not DEBUG:
        app.state.k2700 = Keithley2700()
        app.state.k2700.reset()
        print("Applying temperature config:", cfg.model_dump())
        apply_temperature_config(app.state.k2700, cfg)
    else:
        print("In DEBUG Mode:\n")
        print("Readed temperature config:", cfg.model_dump())


@app.get("/", response_class=HTMLResponse)
def root():
    return f"""
    <html>
        <head>
            <title>Keithley 2700 API</title>
            <style>
                body {{ font-family: Arial; padding: 20px; }}
                h1 {{ color: #2c3e50; }}
                a {{ display: block; margin: 10px 0; }}
                .desc {{ margin: 15px 0; line-height: 1.5; }}
            </style>
        </head>
        <body>
            <h1>Keithley 2700 API</h1>

            <p><strong>Servidor en ejecución</strong></p>
            <p>Modo: {"DEBUG" if DEBUG else "REAL"}</p>

            <div class="desc">
                <h2>Descripción</h2>
                <p>
                    Esta API está diseñada para la automatización del proceso de medidas de 
                    resistencia y conductividad térmica utilizando instrumentación de laboratorio.
                </p>
                <p>
                    Permite configurar los parámetros de medida, ejecutar adquisiciones de datos 
                    y realizar la extracción automática de resultados al finalizar el proceso, 
                    facilitando la integración en sistemas de ensayo y caracterización.
                </p>
            </div>

            <h2>Endpoints:</h2>
            <a href="/docs">Swagger UI</a>
            <a href="/temperature">Leer temperatura</a>

            <h2>Estado:</h2>
            <p id="status">OK</p>
        </body>
    </html>
    """

@app.get("/idn")
async def get_idn():
    if DEBUG:
        return {"idn": "In DEBUG Mode --> FAKE,KEITHLEY,2700,0.0"}

    return {"idn": app.state.k2700.idn()}


# @app.get("/temperature")
# async def get_temperature(channels: str = "104,105"):
#     """
#     Retrieve temperature readings from the specified channels of the Keithley 2700.
#
#     The `channels` parameter is a comma-separated string of channel numbers
#     corresponding to the 7700 multiplexer card (e.g., "101,102").
#
#     Each channel is measured sequentially using the internal scanner, and the
#     result is returned as a dictionary mapping channel numbers to temperature values.
#
#     example of usage: http://127.0.0.1:8000/temperature?channels=104,105
#
#     Parameters:
#         channels (str): Comma-separated list of channel numbers.
#                         Default is "104,105".
#
#     Returns:
#         dict:
#             On success:
#                 {channel_number (str): temperature (float), ...}
#                 Example:
#                     {"104":{"value":34.734993,"time":9414.656,"reading_number":39519},"105":{"value":34.5339088,"time":9414.778,"reading_number":39520}}
#
#             On error:
#                 {"error": "<error message>"}
#
#     Notes:
#         - Channels must correspond to valid scanner inputs (e.g., 101–120 for slot 1).
#         - Measurements are performed sequentially (not simultaneous).
#         - Response time depends on configuration (NPLC, averaging, etc.).
#     """
#     try:
#         ch_list = [int(ch) for ch in channels.split(",")]
#
#         if DEBUG:
#             return fake_temperature_read(ch_list)
#
#         return k2700.read_channels(ch_list)
#
#     except Exception as e:
#         return {"error": str(e)}
#
# def fake_temperature_read(channels):
#     result = {}
#     base_temp = 25.0
#
#     for i, ch in enumerate(channels):
#         noise = random.uniform(-0.2, 0.2)
#
#         value = base_temp + (ch % 10) * 0.1 + noise
#
#         result[str(ch)] = {
#             "value": round(value, 6),
#             "time": round(time.time(), 3),
#             "reading_number": i + 1
#         }
#
#         # simular tiempo de medida
#         time.sleep(0.05)
#
#     return result


@app.post("/temperature/config")
def configure_temperature(cfg: TemperatureConfigRequest, request: Request):
    """
    Configure temperature measurement settings on the Keithley 2700.

    This endpoint configures the temperature measurement chain of the instrument,
    including sensor type, integration rate (NPLC), and digital filtering (averaging).

    All settings are applied globally to the active TEMP function.

    Parameters (JSON body):
        nplc (float, optional):
            Number of Power Line Cycles used for integration.
            Higher values increase accuracy but reduce measurement speed.
            Typical range: 0.01 to 60.

        averaging (object, optional):
            Digital filter configuration:
                - enable (bool): Enable or disable averaging filter.
                - type (str): "REP" (repeating) or "MOV" (moving average).
                - count (int): Number of samples (1–100).
                - window (float): Percentage window (0–100), used for MOV filter.

            If not provided, averaging configuration remains unchanged.

        sensor (object, optional):
            Temperature sensor configuration:
                - type (str): "TC" (thermocouple), "FRTD" (RTD), "THER" (thermistor).
                - subtype (str):
                    * TC: "J","K","T","E","R","S","B","N"
                    * FRTD: "PT100","D100","F100","PT3916","PT385","USER"
                    * THER: Resistance value (e.g., "5000")

            If not provided, the current sensor configuration is preserved.

    Returns:
        dict:
            On success:
                {
                    "status": "ok",
                    "config": {...}
                }

            On debug mode:
                {
                    "status": "fake",
                    "config": {...}
                }

            On error:
                {
                    "detail": "<error message>"
                }

    Examples:

        Configure RTD PT100 with moving average:
        ----------------------------------------
        POST /temperature/config

        {
          "nplc": 1,
          "sensor": {
            "type": "FRTD",
            "subtype": "PT100"
          },
          "averaging": {
            "enable": true,
            "type": "MOV",
            "count": 10,
            "window": 5
          }
        }

        Disable averaging:
        ------------------
        POST /temperature/config

        {
          "averaging": {
            "enable": false
          }
        }

        Configure thermocouple type K (fast measurement):
        ------------------------------------------------
        POST /temperature/config

        {
          "nplc": 0.1,
          "sensor": {
            "type": "TC",
            "subtype": "K"
          }
        }

    Notes:
        - Configuration is applied globally per function (TEMP).
        - The Keithley 2700 measures sequentially when multiple channels are used.
        - NPLC and averaging directly affect measurement speed and noise.
        - MOV filter requires a window parameter to be meaningful.
    """
    if DEBUG:
        return {"In DEBUG Mode --> status": "fake", "config": cfg.model_dump()}

    k2700 = request.app.state.k2700
    apply_temperature_config(k2700, cfg)

    return {"status": "ok", "config": cfg.model_dump()}

def load_default_config():
    config_path = Path("config/default_config.json")

    if not config_path.exists():
        raise FileNotFoundError(f"No se encontró el fichero: {config_path}")

    with config_path.open() as f:
        return json.load(f)

def apply_temperature_config(k2700, cfg: TemperatureConfigRequest):
    """
    Apply temperature configuration to Keithley 2700.

    Parameters:
        k2700: Keithley2700 instance
        cfg (TemperatureConfigRequest): validated config
    """

    function = "TEMP"
    # 1. Seleccionar función
    k2700.set_function(function)

    # 2. Configurar sensor
    if cfg.sensor:
        k2700.configure_temperature_transducer(
            sensor_type=cfg.sensor.type,
            sensor_subtype=cfg.sensor.subtype
        )

    # 3. Configurar NPLC
    if cfg.nplc is not None:
        k2700.set_nplc(function=function, nplc=cfg.nplc)

    # 4. Configurar averaging
    if cfg.averaging:
        avg = cfg.averaging

        if avg.enable:
            k2700.enable_averaging(
                function="TEMP",
                count=avg.count,
                tcontrol=avg.type,
                window=avg.window
            )
        else:
            k2700.disable_averaging("TEMP")