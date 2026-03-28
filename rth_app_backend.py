import time
import random
from fastapi import FastAPI, HTTPException
from drivers import keithley_2700
from drivers.keithley_2700 import Keithley2700, KEITHLEY_2700_FUNCTIONS
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
if not DEBUG:
    k2700 = Keithley2700()
    k2700.reset()
    k2700.configure_temperature_rtd(rtd_type="PT100", four_wire=True, nplc=1)


@app.get("/")
async def root():
    return {"message": "Welcome to Keithley 2700 api"}

@app.get("/idn")
def get_idn():
    if DEBUG:
        return {"idn": "FAKE,KEITHLEY,2700,0.0"}

    return {"idn": k2700.idn()}


@app.get("/temperature")
def get_temperature(channels: str = "104,105"):
    """
    Retrieve temperature readings from the specified channels of the Keithley 2700.

    The `channels` parameter is a comma-separated string of channel numbers
    corresponding to the 7700 multiplexer card (e.g., "101,102").

    Each channel is measured sequentially using the internal scanner, and the
    result is returned as a dictionary mapping channel numbers to temperature values.

    example of usage: http://127.0.0.1:8000/temperature?channels=104,105

    Parameters:
        channels (str): Comma-separated list of channel numbers.
                        Default is "104,105".

    Returns:
        dict:
            On success:
                {channel_number (str): temperature (float), ...}
                Example:
                    {"104":{"value":34.734993,"time":9414.656,"reading_number":39519},"105":{"value":34.5339088,"time":9414.778,"reading_number":39520}}

            On error:
                {"error": "<error message>"}

    Notes:
        - Channels must correspond to valid scanner inputs (e.g., 101–120 for slot 1).
        - Measurements are performed sequentially (not simultaneous).
        - Response time depends on configuration (NPLC, averaging, etc.).
    """
    try:
        ch_list = [int(ch) for ch in channels.split(",")]

        if DEBUG:
            return fake_temperature_read(ch_list)

        return k2700.read_channels(ch_list)

    except Exception as e:
        return {"error": str(e)}

def fake_temperature_read(channels):
    result = {}
    base_temp = 25.0

    for i, ch in enumerate(channels):
        noise = random.uniform(-0.2, 0.2)

        value = base_temp + (ch % 10) * 0.1 + noise

        result[str(ch)] = {
            "value": round(value, 6),
            "time": round(time.time(), 3),
            "reading_number": i + 1
        }

        # simular tiempo de medida
        time.sleep(0.05)

    return result


@app.post("/temperature/config")
def configure_temperature(cfg: TemperatureConfigRequest):
    """
    Configure temperature measurement settings on the Keithley 2700.

    This endpoint allows configuring the full temperature measurement chain,
    including sensor type, integration rate (NPLC), and digital filtering
    (averaging).

    The configuration is applied globally to the active TEMP function.

    Parameters (JSON body):
        nplc (float, optional):
            Number of Power Line Cycles used for integration.
            Higher values increase accuracy but slow down measurements.
            Typical range: 0.01 to 60.

        averaging (object, optional):
            Digital filter configuration:
                - enable (bool): Enable or Disable
                - type (str): "REP" (repeating) or "MOV" (moving average)
                - count (int): number of samples (1–100)
                - window (float): percentage window (0–100), used for MOV

        sensor (object, optional):
            Temperature sensor configuration:
                - type (str): "TC" (thermocouple), "FRTD" (RTD), "THER" (thermistor)
                - subtype (str):
                    * TC: "J","K","T","E","R","S","B","N"
                    * FRTD: "PT100","D100","F100","PT3916","PT385","USER"
                    * THER: resistance value (e.g., "5000")

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

        Configure RTD PT100 with filtering:
        -----------------------------------
        POST /temperature/config

        {
          "nplc": 1,
          "sensor": {
            "type": "FRTD",
            "subtype": "PT100"
          },
          "averaging": {
            "type": "MOV",
            "count": 10,
            "window": 5
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
        - The Keithley 2700 applies configuration globally per function (TEMP).
        - Averaging and NPLC directly affect measurement speed and noise.
        - Moving average (MOV) requires a window parameter.
    """
    try:
        if DEBUG:
            return {
                "status": "fake",
                "config": cfg.dict()
            }

        # 1. Seleccionar función TEMP
        k2700.set_function("TEMP")

        # 2. Sensor
        if cfg.sensor:
            k2700.configure_temperature_sensor(
                sensor_type=cfg.sensor.type,
                sensor_subtype=cfg.sensor.subtype
            )

        # 3. NPLC
        if cfg.nplc is not None:
            k2700.inst.write(f"SENS:TEMP:NPLC {cfg.nplc}")

        # 4. Averaging
        if cfg.averaging.enable:
            avg = cfg.averaging
            k2700.enable_averaging(
                function="TEMP",
                count=avg.count,
                tcontrol=avg.type,
                window=avg.window
            )

        return {
            "status": "ok",
            "config": cfg.dict()
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))