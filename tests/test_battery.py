"""Unit tests for battery.py (FRE-114)

Tests cover PiSugarMonitor initialization and all data-retrieval methods
under three scenarios:
  1. Happy path — server connected and returns expected values
  2. Server is None (failed connection) — methods return None silently
  3. Server raises an exception — methods swallow it and return None
"""

import sys
import pytest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def pisugar_module():
    """Return a fresh pisugar module mock and clean up after each test.

    Saves and restores the original pisugar entry in sys.modules so the
    conftest-installed global mock is left intact for other test modules
    (e.g. test_smoke.py::test_hardware_mocks_loaded).
    """
    original_pisugar = sys.modules.get("pisugar")
    mock_pisugar = MagicMock()
    sys.modules["pisugar"] = mock_pisugar
    sys.modules.pop("battery", None)
    yield mock_pisugar
    sys.modules.pop("battery", None)
    # Restore original rather than deleting, so global conftest mocks survive
    if original_pisugar is not None:
        sys.modules["pisugar"] = original_pisugar
    else:
        sys.modules.pop("pisugar", None)


@pytest.fixture()
def connected_monitor(pisugar_module):
    """PiSugarMonitor with a successfully connected server."""
    mock_conn = MagicMock()
    mock_event_conn = MagicMock()
    pisugar_module.connect_tcp.return_value = (mock_conn, mock_event_conn)

    mock_server = MagicMock()
    pisugar_module.PiSugarServer.return_value = mock_server

    import battery
    monitor = battery.PiSugarMonitor()
    assert monitor.server is not None
    return monitor, mock_server


@pytest.fixture()
def disconnected_monitor(pisugar_module):
    """PiSugarMonitor where the TCP connection fails — server is None."""
    pisugar_module.connect_tcp.side_effect = Exception("Connection refused")

    import battery
    monitor = battery.PiSugarMonitor()
    assert monitor.server is None
    return monitor


# ---------------------------------------------------------------------------
# Initialization tests
# ---------------------------------------------------------------------------

class TestInit:
    def test_successful_connection_sets_server(self, pisugar_module):
        pisugar_module.connect_tcp.return_value = (MagicMock(), MagicMock())
        pisugar_module.PiSugarServer.return_value = MagicMock()

        import battery
        monitor = battery.PiSugarMonitor()

        assert monitor.server is not None
        pisugar_module.connect_tcp.assert_called_once()
        pisugar_module.PiSugarServer.assert_called_once()

    def test_failed_connection_sets_server_to_none(self, pisugar_module):
        pisugar_module.connect_tcp.side_effect = OSError("No route to host")

        import battery
        monitor = battery.PiSugarMonitor()

        assert monitor.server is None

    def test_pisugar_server_constructor_failure_sets_server_to_none(self, pisugar_module):
        pisugar_module.connect_tcp.return_value = (MagicMock(), MagicMock())
        pisugar_module.PiSugarServer.side_effect = RuntimeError("Bad handshake")

        import battery
        monitor = battery.PiSugarMonitor()

        assert monitor.server is None

    def test_successful_connection_passes_conn_args_to_pisugar_server(self, pisugar_module):
        mock_conn = MagicMock(name="conn")
        mock_event_conn = MagicMock(name="event_conn")
        pisugar_module.connect_tcp.return_value = (mock_conn, mock_event_conn)
        pisugar_module.PiSugarServer.return_value = MagicMock()

        import battery
        battery.PiSugarMonitor()

        pisugar_module.PiSugarServer.assert_called_once_with(mock_conn, mock_event_conn)


# ---------------------------------------------------------------------------
# get_battery_level
# ---------------------------------------------------------------------------

class TestGetBatteryLevel:
    def test_returns_level_when_connected(self, connected_monitor):
        monitor, mock_server = connected_monitor
        mock_server.get_battery_level.return_value = 85.0

        assert monitor.get_battery_level() == 85.0
        mock_server.get_battery_level.assert_called_once()

    def test_returns_none_when_server_is_none(self, disconnected_monitor):
        assert disconnected_monitor.get_battery_level() is None

    def test_returns_none_on_server_exception(self, connected_monitor):
        monitor, mock_server = connected_monitor
        mock_server.get_battery_level.side_effect = Exception("Read error")

        assert monitor.get_battery_level() is None

    def test_returns_zero_level(self, connected_monitor):
        monitor, mock_server = connected_monitor
        mock_server.get_battery_level.return_value = 0.0

        assert monitor.get_battery_level() == 0.0

    def test_returns_full_level(self, connected_monitor):
        monitor, mock_server = connected_monitor
        mock_server.get_battery_level.return_value = 100.0

        assert monitor.get_battery_level() == 100.0


# ---------------------------------------------------------------------------
# get_current
# ---------------------------------------------------------------------------

class TestGetCurrent:
    def test_returns_current_when_connected(self, connected_monitor):
        monitor, mock_server = connected_monitor
        mock_server.get_battery_current.return_value = 0.45

        assert monitor.get_current() == 0.45
        mock_server.get_battery_current.assert_called_once()

    def test_returns_none_when_server_is_none(self, disconnected_monitor):
        assert disconnected_monitor.get_current() is None

    def test_returns_none_on_server_exception(self, connected_monitor):
        monitor, mock_server = connected_monitor
        mock_server.get_battery_current.side_effect = IOError("Comm error")

        assert monitor.get_current() is None

    def test_returns_negative_current_during_discharge(self, connected_monitor):
        monitor, mock_server = connected_monitor
        mock_server.get_battery_current.return_value = -0.3

        assert monitor.get_current() == -0.3

    def test_returns_zero_current(self, connected_monitor):
        monitor, mock_server = connected_monitor
        mock_server.get_battery_current.return_value = 0.0

        assert monitor.get_current() == 0.0


# ---------------------------------------------------------------------------
# get_voltage
# ---------------------------------------------------------------------------

class TestGetVoltage:
    def test_returns_voltage_when_connected(self, connected_monitor):
        monitor, mock_server = connected_monitor
        mock_server.get_battery_voltage.return_value = 4.1

        assert monitor.get_voltage() == 4.1
        mock_server.get_battery_voltage.assert_called_once()

    def test_returns_none_when_server_is_none(self, disconnected_monitor):
        assert disconnected_monitor.get_voltage() is None

    def test_returns_none_on_server_exception(self, connected_monitor):
        monitor, mock_server = connected_monitor
        mock_server.get_battery_voltage.side_effect = ValueError("Bad data")

        assert monitor.get_voltage() is None

    def test_returns_low_voltage(self, connected_monitor):
        monitor, mock_server = connected_monitor
        mock_server.get_battery_voltage.return_value = 3.0

        assert monitor.get_voltage() == 3.0

    def test_returns_high_voltage(self, connected_monitor):
        monitor, mock_server = connected_monitor
        mock_server.get_battery_voltage.return_value = 4.2

        assert monitor.get_voltage() == 4.2


# ---------------------------------------------------------------------------
# is_charging
# ---------------------------------------------------------------------------

class TestIsCharging:
    def test_returns_true_when_charging(self, connected_monitor):
        monitor, mock_server = connected_monitor
        mock_server.get_battery_charging.return_value = True

        assert monitor.is_charging() is True
        mock_server.get_battery_charging.assert_called_once()

    def test_returns_false_when_not_charging(self, connected_monitor):
        monitor, mock_server = connected_monitor
        mock_server.get_battery_charging.return_value = False

        assert monitor.is_charging() is False

    def test_returns_none_when_server_is_none(self, disconnected_monitor):
        assert disconnected_monitor.is_charging() is None

    def test_returns_none_on_server_exception(self, connected_monitor):
        monitor, mock_server = connected_monitor
        mock_server.get_battery_charging.side_effect = RuntimeError("Timeout")

        assert monitor.is_charging() is None


# ---------------------------------------------------------------------------
# is_power_plugged
# ---------------------------------------------------------------------------

class TestIsPowerPlugged:
    def test_returns_true_when_plugged_in(self, connected_monitor):
        monitor, mock_server = connected_monitor
        mock_server.get_battery_power_plugged.return_value = True

        assert monitor.is_power_plugged() is True
        mock_server.get_battery_power_plugged.assert_called_once()

    def test_returns_false_when_unplugged(self, connected_monitor):
        monitor, mock_server = connected_monitor
        mock_server.get_battery_power_plugged.return_value = False

        assert monitor.is_power_plugged() is False

    def test_returns_none_when_server_is_none(self, disconnected_monitor):
        assert disconnected_monitor.is_power_plugged() is None

    def test_returns_none_on_server_exception(self, connected_monitor):
        monitor, mock_server = connected_monitor
        mock_server.get_battery_power_plugged.side_effect = Exception("Socket closed")

        assert monitor.is_power_plugged() is None


# ---------------------------------------------------------------------------
# is_charging_allowed
# ---------------------------------------------------------------------------

class TestIsChargingAllowed:
    def test_returns_true_when_charging_allowed(self, connected_monitor):
        monitor, mock_server = connected_monitor
        mock_server.get_battery_allow_charging.return_value = True

        assert monitor.is_charging_allowed() is True
        mock_server.get_battery_allow_charging.assert_called_once()

    def test_returns_false_when_charging_not_allowed(self, connected_monitor):
        monitor, mock_server = connected_monitor
        mock_server.get_battery_allow_charging.return_value = False

        assert monitor.is_charging_allowed() is False

    def test_returns_none_when_server_is_none(self, disconnected_monitor):
        assert disconnected_monitor.is_charging_allowed() is None

    def test_returns_none_on_server_exception(self, connected_monitor):
        monitor, mock_server = connected_monitor
        mock_server.get_battery_allow_charging.side_effect = ConnectionError("Lost connection")

        assert monitor.is_charging_allowed() is None


# ---------------------------------------------------------------------------
# Independence / isolation tests
# ---------------------------------------------------------------------------

class TestServerIsolation:
    def test_each_method_call_is_independent(self, connected_monitor):
        """Verify no method has side effects that corrupt subsequent calls."""
        monitor, mock_server = connected_monitor
        mock_server.get_battery_level.return_value = 75.0
        mock_server.get_battery_current.return_value = 0.3
        mock_server.get_battery_voltage.return_value = 4.0
        mock_server.get_battery_charging.return_value = True
        mock_server.get_battery_power_plugged.return_value = True
        mock_server.get_battery_allow_charging.return_value = False

        assert monitor.get_battery_level() == 75.0
        assert monitor.get_current() == 0.3
        assert monitor.get_voltage() == 4.0
        assert monitor.is_charging() is True
        assert monitor.is_power_plugged() is True
        assert monitor.is_charging_allowed() is False

    def test_exception_in_one_method_does_not_affect_others(self, connected_monitor):
        """An exception in get_battery_level should not break subsequent calls."""
        monitor, mock_server = connected_monitor
        mock_server.get_battery_level.side_effect = Exception("Blew up")
        mock_server.get_battery_voltage.return_value = 3.8

        assert monitor.get_battery_level() is None
        assert monitor.get_voltage() == 3.8

    def test_multiple_calls_to_same_method_all_delegate_to_server(self, connected_monitor):
        monitor, mock_server = connected_monitor
        mock_server.get_battery_level.return_value = 50.0

        results = [monitor.get_battery_level() for _ in range(3)]

        assert results == [50.0, 50.0, 50.0]
        assert mock_server.get_battery_level.call_count == 3

    def test_server_none_all_methods_return_none(self, disconnected_monitor):
        """When server is None every public method must return None."""
        monitor = disconnected_monitor

        assert monitor.get_battery_level() is None
        assert monitor.get_current() is None
        assert monitor.get_voltage() is None
        assert monitor.is_charging() is None
        assert monitor.is_power_plugged() is None
        assert monitor.is_charging_allowed() is None
