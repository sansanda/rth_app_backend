from abc import ABC, abstractmethod
from typing import Any


class TemperatureReader(ABC):
    """Interface for temperature measurement devices."""

    @abstractmethod
    def read_temperature(self, channel: Any) -> dict:
        """
        Read temperature from a specific channel.

        Args:
            channel: Channel identifier. Format depends on instrument
            (e.g. "101", 1, "A1", etc.)

        Returns:
            Temperature in degrees Celsius.
        """
        pass
