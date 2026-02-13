"""
Test configuration and hardware mock setup.

Hardware-specific modules (RPi.GPIO, gpiozero, w1thermsensor, pisugar) are not
available in CI environments. This conftest mocks them at the sys.modules level
before any application code is imported, allowing unit tests to run without
actual Raspberry Pi hardware.
"""

import sys
from unittest.mock import MagicMock

# Mock hardware-specific modules that aren't available in CI
HARDWARE_MODULES = [
    "RPi",
    "RPi.GPIO",
    "gpiozero",
    "w1thermsensor",
    "pisugar",
]

for mod in HARDWARE_MODULES:
    if mod not in sys.modules:
        sys.modules[mod] = MagicMock()
