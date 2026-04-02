from pathlib import Path
import json
from typing import Optional

from models.configuration_models import MultimeterConfig, SourceMeterConfig, LimitsConfig, ProcessConfig, MeasureResultsConfig


class ConfigurationController:
    """
    Handles loading, accessing, and managing application configuration.

    Reads configuration from a JSON file and provides typed access
    through Pydantic models.
    """

    def __init__(self, config_path: str = "config/config.json"):
        self.config_path = Path(config_path)
        self._config_data: Optional[dict] = None

        self._load_config()

    # -------------------------
    # Internal
    # -------------------------

    def _load_config(self):
        """
        Load configuration file into memory.
        """
        if not self.config_path.exists():
            raise FileNotFoundError(f"Config file not found: {self.config_path}")

        with self.config_path.open("r") as f:
            self._config_data = json.load(f)

    def update_config_section(self, section: str, data: dict):
        """
        Update a specific section of the configuration file and persist changes safely.

        This method replaces the given section in the in-memory configuration with
        the provided data, then writes the updated configuration to disk using a
        temporary file to avoid corruption.

        Parameters:
            section (str): Name of the configuration section to update
                           (e.g., "multimeter_setup").
            data (dict): New data to assign to the section. Must be JSON-serializable.

        Notes:
            - The update is performed in memory first, then written to disk.
            - A temporary file is used and atomically renamed to ensure safe writes.
            - Existing configuration outside the specified section is preserved.
        """
        # actualizar sección
        self._config_data[section] = data

        # escritura segura
        tmp_path = self.config_path.with_suffix(".tmp")

        # guardar fichero
        with tmp_path.open("w") as f:
            json.dump(self._config_data, f, indent=2)

        tmp_path.replace(self.config_path)

        self.reload()
    # -------------------------
    # Public API
    # -------------------------

    def reload(self):
        """
        Reload configuration from disk.
        """
        self._load_config()

    def get_raw(self) -> dict:
        """
        Return raw configuration dictionary.
        """
        return self._config_data

    # -------------------------
    # Multimeter
    # -------------------------

    def get_multimeter_config(self) -> MultimeterConfig:
        """
        Return full multimeter configuration as a validated model.
        """
        data = self._config_data.get("multimeter_setup")

        if data is None:
            raise ValueError("Missing 'multimeter_setup' in config")

        return MultimeterConfig(**data)

    # -------------------------
    # SourceMeter
    # -------------------------

    def get_sourcemeter_config(self) -> SourceMeterConfig:
        """
        Return full sourcemeter configuration as a validated model.
        """
        data = self._config_data.get("source_meter_setup")

        if data is None:
            raise ValueError("Missing 'sourcemeter_setup' in config")

        return SourceMeterConfig(**data)

    # -------------------------
    # Limits
    # -------------------------

    def get_limits_config(self) -> LimitsConfig:
        """
        Return full limits configuration as a validated model.
        """
        data = self._config_data.get("limits_setup")

        if data is None:
            raise ValueError("Missing 'limits_setup' in config")

        return LimitsConfig(**data)

    # -------------------------
    # Process
    # -------------------------

    def get_process_config(self) -> ProcessConfig:
        """
        Return full process configuration as a validated model.
        """
        data = self._config_data.get("process_setup")

        if data is None:
            raise ValueError("Missing 'process_setup' in config")

        return ProcessConfig(**data)

    # -------------------------
    # Measure Results
    # -------------------------

    def get_measure_results_config(self) -> MeasureResultsConfig:
        """
        Return full measure-results configuration as a validated model.
        """
        data = self._config_data.get("measure_results")

        if data is None:
            raise ValueError("Missing 'measure_results' in config")

        return MeasureResultsConfig(**data)

    # -------------------------
    # Helpers (opcionales pero útiles)
    # -------------------------

    def is_multimeter_enabled(self) -> bool:
        """
        Check if multimeter is enabled.
        """
        return self.get_multimeter_config().enabled

    def get_enabled_channels(self):
        """
        Return enabled temperature channels.
        """
        temp_cfg = self.get_multimeter_config().temperature
        return [
            ch for ch in temp_cfg.channels.values() if ch.enabled
        ]