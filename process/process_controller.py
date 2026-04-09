import time
import threading
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
)

logger = logging.getLogger("ProcessController")


class ProcessController:
    def __init__(self):
        logger.info("ProcessController initiated")
        self.state = "idle"
        self.progress = 0
        self.step = 0
        self.state = "idle"
        self.progress = 0
        self.step = 0
        self.stepDescription = ""
        self.logs = []
        self._lock = threading.Lock()
        self._thread = None

    # -------------------------
    # Control
    # -------------------------

    def play(self):
        logger.info("Play executed")
        with self._lock:
            if self.state == "running":
                return False

            self.state = "running"

            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._run)
                self._thread.start()

        return True

    def pause(self):
        logger.info("Pause executed")
        with self._lock:
            if self.state == "running":
                self.state = "paused"

    def stop(self):
        logger.info("Stop executed")
        with self._lock:
            self.state = "stopped"

    # -------------------------
    # Estado
    # -------------------------

    def get_status(self):
        with self._lock:
            return {
                "state": self.state,
                "progress": self.progress,
                "step": self.step,
                "stepDescription": self.stepDescription
            }

    # -------------------------
    # Motor interno
    # -------------------------

    def _run(self):
        logger.info("_run executed")
        steps = [
            "Inicializando",
            "Calentando",
            "Estabilizando",
            "Midiendo",
            "Finalizando"
        ]

        for i, step in enumerate(steps):

            logger.info(f"In step {step}")

            if self.state == "stopped":
                break

            self.step = i
            self.stepDescription = step

            for p in range(20):

                if self.state == "stopped":
                    return

                while self.state == "paused":
                    time.sleep(0.2)

                self.progress = int((i * 20) + p)
                time.sleep(0.2)

        self.state = "idle"

    # -------------------------
    # Logging
    # -------------------------

    def add_log(self, msg, level="info"):
        self.logs.append({
            "time": time.time(),
            "message": msg,
            "level": level
        })
