from pydantic import BaseModel, Field
from typing import Dict, Literal, List


# =========================
# SHARED MODELS
# =========================

class GPIBConfig(BaseModel):
    """
    GPIB communication settings for the instrument.
    """
    gpib_card: int = Field(..., ge=0)
    address: int = Field(..., gt=0)
    timeout_ms: int = Field(..., gt=0)


class AveragingConfig(BaseModel):
    """
    Digital filtering (averaging) configuration.
    """
    enabled: bool = True
    type: Literal["REP", "MOV"] = "MOV"
    window: float = Field(default=0.1, gt=0, le=100)
    count: int = Field(default=10, gt=0)


class NotifyConfig(BaseModel):
    """
    Notification configuration (e.g., SMS alerts).
    """
    enabled: bool = True
    phone_number: str


# =========================
# MULTIMETER MODELS
# =========================
class SensorConfig(BaseModel):
    """
    Temperature sensor configuration (type and subtype).
    """
    type: str
    subtype: str


class ChannelConfig(BaseModel):
    """
    Individual measurement channel configuration.
    """
    id: str
    enabled: bool = True
    channel: int
    description: str


class MultimeterMeasureConfig(BaseModel):
    """
    Measurement configuration for the multimeter.
    """
    nplc: float = Field(..., gt=0)
    measurement_resolution: int = Field(default=6, gt=3, lt=8)


class TemperatureConfig(BaseModel):
    """
    Temperature measurement setup including sensor, channels, and filtering.
    """
    sensor: SensorConfig
    channels: Dict[str, ChannelConfig]
    averaging: AveragingConfig
    measure: MultimeterMeasureConfig


class MultimeterConfig(BaseModel):
    """
    Full multimeter configuration including communication and temperature setup.
    """
    enabled: bool = True
    gpib: GPIBConfig
    temperature: TemperatureConfig


# =========================
# SOURCEMETER MODELS
# =========================

class OutputConfig(BaseModel):
    """
    Output configuration (enable and connection terminal).
    """
    enabled: bool = True
    connection: Literal["FRONT", "REAR"]


class SourceConfig(BaseModel):
    """
    Source configuration (mode and output parameters).
    """
    mode: Literal["CURRENT", "VOLTAGE"] = "CURRENT"
    current: float = 0.0
    voltage_compliance: float = Field(..., gt=0)
    delay_ms: int = Field(default=0, ge=0)


class MeasureConfig(BaseModel):
    """
    Measurement configuration for the source meter.
    """
    mode: Literal["CURRENT", "VOLTAGE"] = "VOLTAGE"
    range_volts: float = Field(..., gt=0)
    nplc: float = Field(..., gt=0)
    timestamps: bool = True


class SourceMeterConfig(BaseModel):
    """
    Full source meter configuration including communication,
    sourcing, measurement, and averaging.
    """
    enabled: bool = True
    gpib: GPIBConfig
    output: OutputConfig
    source: SourceConfig
    measure: MeasureConfig
    averaging: AveragingConfig


# =========================
# LIMITS MODELS
# =========================

class CurrentLimitConfig(BaseModel):
    """
    Current safety limit configuration.
    """
    max: float = Field(..., gt=0)


class TemperatureLimitConfig(BaseModel):
    """
    Temperature safety limit configuration.
    """
    unit: Literal["C", "K", "F"] = "C"
    max: float = Field(...)


class LimitsConfig(BaseModel):
    """
    Safety limits configuration for the process.
    """
    enabled: bool = True
    current: CurrentLimitConfig
    temperature: TemperatureLimitConfig


# =========================
# PROCESS MODELS
# =========================

class InitConfig(BaseModel):
    """
    Initial checks before starting the process.
    """
    test_multimeter: bool = True
    test_source_meter: bool = True
    notify: NotifyConfig


class TemperatureRampUpConfig(BaseModel):
    """
    Temperature ramp-up stage configuration.
    """
    unit: Literal["C", "K", "F"]
    target_temperature: float
    duration_min: float = Field(..., gt=0)


class TemperatureStabilizationConfig(BaseModel):
    """
    Temperature stabilization stage configuration.
    """
    duration_min: float = Field(..., gt=0)


class TemperatureRampDownConfig(BaseModel):
    """
    Temperature ramp-down stage configuration.
    """
    duration_min: float = Field(..., gt=0)


class MeasurementConfig(BaseModel):
    """
    Measurement stage configuration.
    """
    num_measures: int = Field(..., gt=0)
    sample_period_s: float = Field(..., gt=0)
    channel_delay_ms: int = Field(..., ge=0)
    channels: List[str]  # ["top", "bottom"]


class EndConfig(BaseModel):
    """
    End-of-process actions.
    """
    notify: NotifyConfig


class SafetyConfig(BaseModel):
    """
    Safety behavior during the process.
    """
    stop_on_limit: bool = True
    cooldown_on_overtemp: bool = True


class ProcessConfig(BaseModel):
    """
    Full process workflow configuration.
    """
    enabled: bool = True
    init: InitConfig
    temperature_ramp_up: TemperatureRampUpConfig
    temperature_stabilization: TemperatureStabilizationConfig
    measurement: MeasurementConfig
    temperature_ramp_down: TemperatureRampDownConfig
    end: EndConfig
    safety: SafetyConfig


# =========================
# MEASURE RESULTS
# =========================

class FileConfig(BaseModel):
    """
    File output configuration for measurement results.
    """
    name: str
    format: Literal["csv", "json", "dat"] = "csv"
    path: str = "."
    include_timestamp: bool = True


class AutoSaveConfig(BaseModel):
    """
    Autosave configuration for periodic data persistence.
    """
    enabled: bool = True
    period_min: int = Field(..., gt=0)
    mode: Literal["append", "overwrite"] = "append"


class MeasureResultsConfig(BaseModel):
    """
    Configuration for storing measurement results.
    """
    enabled: bool = True
    file: FileConfig
    autosave: AutoSaveConfig


# =========================
# COMPLETE APP CONFIG
# =========================
class AppConfig(BaseModel):
    profile_name: str
    multimeter_setup: MultimeterConfig
    source_meter_setup: SourceMeterConfig
    limits_setup: LimitsConfig
    process_setup: ProcessConfig
    measure_results: MeasureResultsConfig
