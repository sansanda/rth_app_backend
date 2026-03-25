from fastapi import FastAPI
from drivers.keithley_2700 import Keithley2700

app = FastAPI()

k2700 = Keithley2700(gpib_card=0, gpib_address=14, timeout=5000);

# init una vez
k2700.reset()
k2700.configure_temperature_rtd(rtd_type="PT100", four_wire=True, nplc=1)


@app.get("/idn")
def get_idn():
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
        data = k2700.read_channels(ch_list)
        return data

    except Exception as e:
        return {"error": str(e)}