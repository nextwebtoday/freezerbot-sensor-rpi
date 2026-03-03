"""
Test configuration and hardware mock setup.

Hardware-specific modules (RPi.GPIO, gpiozero, w1thermsensor, pisugar) are not
available in CI environments. This conftest mocks them at the sys.modules level
before any application code is imported, allowing unit tests to run without
actual Raspberry Pi hardware.
"""

import sys
import os
from unittest.mock import MagicMock, patch

# Mock hardware-specific modules that aren't available in CI
HARDWARE_MODULES = [
    "RPi",
    "RPi.GPIO",
    "gpiozero",
    "w1thermsensor",
    "pisugar",
    "smbus",
    "smbus2",
    "spidev",
]

for mod in HARDWARE_MODULES:
    if mod not in sys.modules:
        sys.modules[mod] = MagicMock()

# Make gpiozero.CPUTemperature return a mock with .temperature
cpu_temp_mock = MagicMock()
cpu_temp_mock.return_value.temperature = 45.0
sys.modules['gpiozero'].CPUTemperature = cpu_temp_mock

# Make w1thermsensor.W1ThermSensor a proper mock
w1_mock_class = MagicMock()
w1_mock_class.return_value.get_temperature.return_value = -20.0
sys.modules['w1thermsensor'].W1ThermSensor = w1_mock_class

# Add raspberry_pi directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'raspberry_pi'))

# Mock load_dotenv globally — find_dotenv() can fail in CI when os.path.exists is
# patched or when called without a proper frame stack. Since tests set env vars
# directly via patch.dict, dotenv loading is not needed in tests.
patch('dotenv.load_dotenv', MagicMock()).start()
