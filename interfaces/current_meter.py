from abc import ABC, abstractmethod


class CurrentMeter(ABC):
    """Interface for current measurement devices."""

    @abstractmethod
    def measure_current(self) -> float:
        """
        Measure current.

        Returns:
            Current in amperes.
        """
        pass
