from abc import ABC, abstractmethod


class Instrument(ABC):
    """Generic instrument lifecycle interface."""

    @abstractmethod
    def connect(self):
        pass

    @abstractmethod
    def disconnect(self):
        pass

    @abstractmethod
    def reset(self):
        pass