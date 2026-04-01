import logging
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from config.configuration_controller import ConfigurationController
from models.configuration_models import MultimeterConfig
from drivers.keithley_2700 import Keithley2700
from process.process_controller import ProcessController

app = FastAPI()
process_controller = ProcessController()
configuration_controller = ConfigurationController()
DEBUG = True


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(filename)s] [%(levelname)s] [%(name)s] %(message)s",
)

logger = logging.getLogger("app")

# init una vez (solo si no estás en debug)
@app.on_event("startup")
def startup_event():
    # config por defecto (si quieres mantenerla)
    multimeter_config = configuration_controller.get_multimeter_config()

    if not DEBUG:
        app.state.k2700 = Keithley2700(
            gpib_card=multimeter_config.gpib.gpib_card,
            gpib_address=multimeter_config.gpib.address,
            timeout=multimeter_config.gpib.timeout_ms
        )
        app.state.k2700.reset()
        print("Applying temperature config:", multimeter_config.model_dump())
        app.state.k2700.configure(multimeter_config)
    else:
        logger.info(startup_event.__name__ + " In DEBUG Mode")
        logger.info("Readed temperature config --> " + str(multimeter_config.model_dump()))


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


# **************************************************
# CONTROL DEL PROCESO DE MEDIDA
# **************************************************

@app.post("/process/play")
def play():
    ok = process_controller.play()
    return {"status": "ok" if ok else "ignored"}


@app.post("/process/pause")
def pause():
    process_controller.pause()
    return {"status": "ok"}


@app.post("/process/stop")
def stop():
    process_controller.stop()
    return {"status": "ok"}


@app.get("/process/status")
def status():
    return process_controller.get_status()


# **************************************************
# Configuracion previa del proceso de medida
# **************************************************
@app.post("/multimeter/config")
def configure_multimeter(cfg: MultimeterConfig):
    """
    Configure the multimeter settings and persist them to config file.
    """

    data = cfg.model_dump()

    # guardar config
    configuration_controller.update_config_section("multimeter_setup", data)
    multimeter_config = configuration_controller.get_multimeter_config()

    if not DEBUG:
        try:
            app.state.k2700.configure(multimeter_config)
        except Exception as e:
            logger.exception("Error configuring multimeter")

            return {
                "status": "error",
                "message": str(e)
            }
    else:
        logger.info(f"{configure_multimeter.__name__} received configuration data --> {data} ")
        logger.info(
            f"{configure_multimeter.__name__} - DEBUG MODE → config updated (no instrument comms)"
        )

    return {"status": "ok", "config": data}