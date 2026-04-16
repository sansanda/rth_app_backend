from abc import ABC, abstractmethod


class VoltageSource(ABC):
    """Interface for voltage sourcing devices."""

    @abstractmethod
    def set_voltage(self, voltage: float):
        """
        Set output voltage.

        Args:
            voltage: Voltage in volts.
        """
        pass

    @abstractmethod
    def enable_output(self, enable: bool):
        """
        Enable or disable output.

        Args:
            enable: True to enable output, False to disable.
        """
        pass
