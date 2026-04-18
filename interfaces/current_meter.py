from abc import ABC, abstractmethod


class CurrentMeter(ABC):
    """Interface for current measurement devices."""

    @abstractmethod
    def measure_current(self) -> dict:
        """
        Measure current.

        Returns:
            Current in amperes.
        """
        pass
