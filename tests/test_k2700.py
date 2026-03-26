import pytest
from drivers.keithley_2700 import Keithley2700, get_function_scpi_command


@pytest.fixture(scope="module")
def k2700():
    inst = Keithley2700(gpib_card=0, gpib_address=14, timeout=5000);

    inst.reset()

    yield inst

    inst.close()


def test_command_generation():
    cmd = get_function_scpi_command(subsystem="SENS",
                                    function="FUNC",
                                    value='TEMP',
                                    channels=[104, 105])
    assert cmd == "SENS:FUNC TEMP (@104,105)"


def test_command_generation2():
    cmd = get_function_scpi_command(subsystem="SENS",
                                    function="TEMP:NPLC",
                                    value=1,
                                    channels=[104, 105])
    assert cmd == "SENS:TEMP:NPLC 1 (@104,105)"


def test_command_generation3():
    cmd = get_function_scpi_command(subsystem="SENS",
                                    function="TEMP:AVER:TCON",
                                    value="REP",
                                    channels=[104, 105])
    assert cmd == "SENS:TEMP:AVER:TCON REP (@104,105)"

#
# @pytest.mark.hardware
# def test_idn(k2700):
#     idn = k2700.idn()
#     assert "KEITHLEY" in idn.upper()
#
# @pytest.mark.hardware
# def test_read_single_channels(k2700, channels = [104]):
#     for channel in channels:
#         value = k2700.read_channel(channel)["value"]
#         assert isinstance(value, float)
#         assert -100 < value < 200  # rango razonable PT100
#
#
# @pytest.mark.hardware
# def test_read_channels(k2700):
#     channels = [104, 105]
#
#     data = k2700.read_channels(channels)
#
#     # =========================
#     # 1. estructura
#     # =========================
#     assert isinstance(data, dict)
#     assert set(data.keys()) == set(channels)
#
#     # =========================
#     # 2. tipos
#     # =========================
#     for ch in channels:
#         assert isinstance(data[ch]["value"], float)
#
# @pytest.mark.hardware
# def test_averaging_state(k2700):
#     # k2700.enable_averaging(count=5)
#     #
#     # state = k2700.inst.query("SENS:AVER:STAT?").strip()
#     # assert state in ["1", "ON"]
#
#     k2700.disable_averaging()
#
#     state = k2700.inst.query("SENS:AVER:STAT?").strip()
#     assert state in ["0", "OFF"]
