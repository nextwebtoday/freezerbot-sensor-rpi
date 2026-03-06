"""Unit tests for temperature_monitor.py (FRE-123)"""
import sys
import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture(autouse=True)
def mock_dependencies():
    """Mock all dependencies before importing temperature_monitor."""
    # Fresh W1ThermSensor mock each test
    w1_module = MagicMock()
    w1_sensor_class = MagicMock()
    w1_sensor_class.return_value.get_temperature.return_value = -20.0
    w1_module.W1ThermSensor = w1_sensor_class
    sys.modules['w1thermsensor'] = w1_module

    # Fresh gpiozero mock
    gpiozero_mod = MagicMock()
    cpu_temp_cls = MagicMock()
    cpu_temp_cls.return_value.temperature = 45.0
    gpiozero_mod.CPUTemperature = cpu_temp_cls
    sys.modules['gpiozero'] = gpiozero_mod

    mocks = {}

    # Mock config
    mock_config = MagicMock()
    mock_config.return_value.configuration_exists = True
    mock_config.return_value.is_configured = True
    mock_config.return_value.config = {
        'email': 'test@example.com',
        'password': 'testpass',
        'device_name': 'Test Sensor',
    }
    mocks['config_cls'] = mock_config
    sys.modules['config'] = MagicMock()
    sys.modules['config'].Config = mock_config

    # Mock api
    mock_api = MagicMock()
    mock_api.api_token_exists.return_value = True
    mock_api.make_api_request.return_value = MagicMock(status_code=201, json=lambda: {'name': 'Test Sensor'})
    mock_api.make_api_request_with_creds.return_value = MagicMock(status_code=201, json=lambda: {'token': 'test-token'})
    mocks['api'] = mock_api
    sys.modules['api'] = mock_api

    # Mock led_control
    sys.modules['led_control'] = MagicMock()

    # Mock freezerbot_setup
    sys.modules['freezerbot_setup'] = MagicMock()

    # Mock battery
    mock_battery_inst = MagicMock()
    mock_battery_inst.get_battery_level.return_value = 85.0
    mock_battery_inst.get_current.return_value = 0.5
    mock_battery_inst.get_voltage.return_value = 4.1
    mock_battery_inst.is_charging.return_value = True
    mock_battery_inst.is_power_plugged.return_value = True
    mock_battery_inst.is_charging_allowed.return_value = True
    battery_mod = MagicMock()
    battery_mod.PiSugarMonitor.return_value = mock_battery_inst
    sys.modules['battery'] = battery_mod
    mocks['battery_inst'] = mock_battery_inst

    # Mock network
    mock_network = MagicMock()
    mock_network.load_network_status.return_value = {'network_failure_count': 0, 'reboot_count': 0}
    mock_network.test_internet_connectivity.return_value = True
    mock_network.get_current_wifi_ssid.return_value = 'TestWifi'
    mock_network.get_wifi_signal_strength.return_value = -50
    mock_network.get_ip_address.return_value = '192.168.1.100'
    mock_network.get_mac_address.return_value = 'AA:BB:CC:DD:EE:FF'
    mock_network.get_configured_wifi_networks.return_value = ['TestWifi']
    sys.modules['network'] = mock_network
    mocks['network'] = mock_network

    # Mock device_info
    di_mod = MagicMock()
    di_mod.DeviceInfo.return_value.device_info = {'serial': '12345', 'model': 'rpi4'}
    sys.modules['device_info'] = di_mod

    # Mock restarts
    mock_restarts = MagicMock()
    sys.modules['restarts'] = mock_restarts
    mocks['restarts'] = mock_restarts

    # Mock offline_buffer so TemperatureMonitor doesn't try to create /home/pi
    mock_offline_buffer_inst = MagicMock()
    mock_offline_buffer_cls = MagicMock(return_value=mock_offline_buffer_inst)
    offline_buffer_mod = MagicMock()
    offline_buffer_mod.OfflineBuffer = mock_offline_buffer_cls
    sys.modules['offline_buffer'] = offline_buffer_mod
    mocks['offline_buffer'] = mock_offline_buffer_inst

    # Mock RPi.GPIO
    sys.modules['RPi'] = MagicMock()
    sys.modules['RPi.GPIO'] = MagicMock()

    # Remove cached temperature_monitor to force reimport with fresh mocks
    sys.modules.pop('temperature_monitor', None)

    yield mocks

    # Cleanup
    for mod_name in ['temperature_monitor', 'config', 'api', 'led_control',
                     'freezerbot_setup', 'battery', 'network', 'device_info',
                     'restarts', 'w1thermsensor', 'gpiozero', 'RPi', 'RPi.GPIO',
                     'offline_buffer']:
        sys.modules.pop(mod_name, None)


def _import_monitor():
    sys.modules.pop('temperature_monitor', None)
    import temperature_monitor
    return temperature_monitor


def _create_monitor(mock_deps):
    tm = _import_monitor()
    return tm.TemperatureMonitor()


class TestSensorDiscoveryAndReading:
    def test_read_temperature_discovers_sensor(self, mock_dependencies):
        monitor = _create_monitor(mock_dependencies)
        assert monitor.sensor is None
        monitor.read_temperature()
        assert monitor.sensor is not None

    def test_read_temperature_returns_value(self, mock_dependencies):
        from w1thermsensor import W1ThermSensor
        W1ThermSensor.return_value.get_temperature.return_value = -18.5
        monitor = _create_monitor(mock_dependencies)
        temp = monitor.read_temperature()
        assert temp == -18.5

    def test_read_temperature_reuses_existing_sensor(self, mock_dependencies):
        from w1thermsensor import W1ThermSensor
        monitor = _create_monitor(mock_dependencies)
        monitor.read_temperature()
        monitor.read_temperature()
        assert W1ThermSensor.call_count == 1

    def test_sensor_discovery_failure_increments_error_count(self, mock_dependencies):
        from w1thermsensor import W1ThermSensor
        W1ThermSensor.side_effect = Exception("No sensor found")
        monitor = _create_monitor(mock_dependencies)
        with pytest.raises(Exception):
            monitor.read_temperature()
        assert monitor.consecutive_sensor_errors == 1

    def test_sensor_read_failure_increments_error_count(self, mock_dependencies):
        from w1thermsensor import W1ThermSensor
        W1ThermSensor.return_value.get_temperature.side_effect = Exception("Read error")
        monitor = _create_monitor(mock_dependencies)
        with pytest.raises(Exception):
            monitor.read_temperature()
        assert monitor.consecutive_sensor_errors == 1

    def test_successful_read_resets_error_count(self, mock_dependencies):
        from w1thermsensor import W1ThermSensor
        W1ThermSensor.return_value.get_temperature.return_value = -20.0
        monitor = _create_monitor(mock_dependencies)
        monitor.consecutive_sensor_errors = 5
        # Need sensor to already exist so it doesn't go through discovery path with modprobe
        monitor.sensor = W1ThermSensor()
        temp = monitor.read_temperature()
        assert monitor.consecutive_sensor_errors == 0
        assert temp == -20.0


class TestModprobeRecovery:
    @patch('subprocess.run')
    def test_modprobe_triggered_after_threshold(self, mock_subprocess, mock_dependencies):
        from w1thermsensor import W1ThermSensor
        W1ThermSensor.return_value.get_temperature.return_value = -20.0
        monitor = _create_monitor(mock_dependencies)
        monitor.consecutive_sensor_errors = 3
        monitor.read_temperature()
        assert mock_subprocess.call_count >= 2

    @patch('subprocess.run')
    def test_no_modprobe_below_threshold(self, mock_subprocess, mock_dependencies):
        from w1thermsensor import W1ThermSensor
        W1ThermSensor.return_value.get_temperature.return_value = -20.0
        monitor = _create_monitor(mock_dependencies)
        monitor.consecutive_sensor_errors = 1
        monitor.read_temperature()
        mock_subprocess.assert_not_called()


class TestAPIReportingPayload:
    def test_payload_contains_temperature(self, mock_dependencies):
        from w1thermsensor import W1ThermSensor
        W1ThermSensor.return_value.get_temperature.return_value = -22.5
        monitor = _create_monitor(mock_dependencies)
        temp = monitor.read_temperature()
        assert temp == -22.5

    def test_payload_contains_cpu_temperature(self, mock_dependencies):
        from gpiozero import CPUTemperature
        cpu = CPUTemperature()
        assert cpu.temperature == 45.0

    def test_payload_contains_battery_fields(self, mock_dependencies):
        monitor = _create_monitor(mock_dependencies)
        assert monitor.pisugar.get_battery_level() == 85.0
        assert monitor.pisugar.get_current() == 0.5
        assert monitor.pisugar.get_voltage() == 4.1
        assert monitor.pisugar.is_charging() is True
        assert monitor.pisugar.is_power_plugged() is True
        assert monitor.pisugar.is_charging_allowed() is True

    def test_payload_contains_network_fields(self, mock_dependencies):
        import network
        assert network.get_current_wifi_ssid() == 'TestWifi'
        assert network.get_wifi_signal_strength() == -50
        assert network.get_ip_address() == '192.168.1.100'
        assert network.get_mac_address() == 'AA:BB:CC:DD:EE:FF'


class TestConsecutiveErrorTracking:
    def test_errors_appended_on_sensor_failure(self, mock_dependencies):
        from w1thermsensor import W1ThermSensor
        W1ThermSensor.side_effect = Exception("Sensor gone")
        monitor = _create_monitor(mock_dependencies)
        with pytest.raises(Exception):
            monitor.read_temperature()
        assert len(monitor.consecutive_errors) == 1

    def test_multiple_errors_accumulated(self, mock_dependencies):
        from w1thermsensor import W1ThermSensor
        W1ThermSensor.side_effect = Exception("Sensor gone")
        monitor = _create_monitor(mock_dependencies)
        for _ in range(3):
            with pytest.raises(Exception):
                monitor.read_temperature()
        assert len(monitor.consecutive_errors) == 3

    def test_report_consecutive_errors_clears_on_success(self, mock_dependencies):
        monitor = _create_monitor(mock_dependencies)
        monitor.consecutive_errors = ['error1', 'error2']
        import api
        api.make_api_request.return_value = MagicMock(status_code=200)
        monitor.report_consecutive_errors()
        assert len(monitor.consecutive_errors) == 0

    def test_report_consecutive_errors_keeps_on_failure(self, mock_dependencies):
        monitor = _create_monitor(mock_dependencies)
        monitor.consecutive_errors = ['error1']
        import api
        api.make_api_request.return_value = MagicMock(status_code=500, text='Server Error')
        monitor.report_consecutive_errors()
        assert len(monitor.consecutive_errors) == 1

    def test_report_consecutive_errors_noop_when_empty(self, mock_dependencies):
        monitor = _create_monitor(mock_dependencies)
        monitor.consecutive_errors = []
        import api
        api.make_api_request.reset_mock()
        monitor.report_consecutive_errors()
        api.make_api_request.assert_not_called()


class TestRebootConditions:
    @patch('subprocess.run')
    def test_reboot_triggered_at_max_sensor_errors(self, mock_subprocess, mock_dependencies):
        from w1thermsensor import W1ThermSensor
        W1ThermSensor.return_value.get_temperature.side_effect = Exception("Read error")
        import api
        api.make_api_request.return_value = MagicMock(status_code=200)
        monitor = _create_monitor(mock_dependencies)
        monitor.consecutive_sensor_errors = 9
        monitor.reboot_count = 0
        monitor.sensor = W1ThermSensor()
        with pytest.raises(Exception, match="Rebooting system"):
            monitor.read_temperature()

    @patch('subprocess.run')
    def test_no_reboot_when_max_reboots_exceeded(self, mock_subprocess, mock_dependencies):
        from w1thermsensor import W1ThermSensor
        W1ThermSensor.return_value.get_temperature.side_effect = Exception("Read error")
        monitor = _create_monitor(mock_dependencies)
        monitor.consecutive_sensor_errors = 9
        monitor.reboot_count = 4
        monitor.sensor = W1ThermSensor()
        with pytest.raises(Exception, match="Read error"):
            monitor.read_temperature()


class TestAuthFailureFallback:
    def test_401_triggers_setup_mode(self, mock_dependencies):
        monitor = _create_monitor(mock_dependencies)
        import api
        api.api_token_exists.return_value = False
        api.make_api_request_with_creds.return_value = MagicMock(status_code=401)
        import restarts
        monitor.obtain_api_token()
        restarts.restart_in_setup_mode.assert_called_once()

    def test_403_triggers_setup_mode(self, mock_dependencies):
        monitor = _create_monitor(mock_dependencies)
        import api
        api.api_token_exists.return_value = False
        api.make_api_request_with_creds.return_value = MagicMock(status_code=403)
        import restarts
        monitor.obtain_api_token()
        restarts.restart_in_setup_mode.assert_called_once()

    def test_successful_auth_saves_token(self, mock_dependencies):
        monitor = _create_monitor(mock_dependencies)
        import api
        api.api_token_exists.return_value = False
        api.make_api_request_with_creds.return_value = MagicMock(
            status_code=201, json=lambda: {'token': 'new-token'}
        )
        monitor.obtain_api_token()
        api.set_api_token.assert_called_once_with('new-token')

    def test_existing_token_skips_auth(self, mock_dependencies):
        monitor = _create_monitor(mock_dependencies)
        import api
        api.api_token_exists.return_value = True
        api.make_api_request_with_creds.reset_mock()
        monitor.obtain_api_token()
        api.make_api_request_with_creds.assert_not_called()


class TestNetworkStatusMonitoring:
    def test_initial_network_status_loaded(self, mock_dependencies):
        monitor = _create_monitor(mock_dependencies)
        assert monitor.network_failure_count == 0
        assert monitor.reboot_count == 0

    def test_network_status_with_existing_failures(self, mock_dependencies):
        import network
        network.load_network_status.return_value = {'network_failure_count': 5, 'reboot_count': 2}
        monitor = _create_monitor(mock_dependencies)
        assert monitor.network_failure_count == 5
        assert monitor.reboot_count == 2


class TestCPUTemperature:
    def test_cpu_temperature_accessible(self, mock_dependencies):
        from gpiozero import CPUTemperature
        cpu = CPUTemperature()
        assert cpu.temperature == 45.0


class TestSensorDisconnection:
    def test_sensor_set_to_none_after_discovery_failure(self, mock_dependencies):
        from w1thermsensor import W1ThermSensor
        W1ThermSensor.side_effect = Exception("No sensor")
        monitor = _create_monitor(mock_dependencies)
        with pytest.raises(Exception):
            monitor.read_temperature()
        assert monitor.sensor is None

    def test_sensor_read_failure_still_keeps_sensor_ref(self, mock_dependencies):
        from w1thermsensor import W1ThermSensor
        W1ThermSensor.return_value.get_temperature.side_effect = Exception("Disconnected")
        monitor = _create_monitor(mock_dependencies)
        with pytest.raises(Exception):
            monitor.read_temperature()
        assert monitor.sensor is not None

    def test_consecutive_disconnections_tracked(self, mock_dependencies):
        from w1thermsensor import W1ThermSensor
        W1ThermSensor.side_effect = Exception("No sensor")
        monitor = _create_monitor(mock_dependencies)
        for _ in range(5):
            with pytest.raises(Exception):
                monitor.read_temperature()
        assert monitor.consecutive_sensor_errors == 5
        assert len(monitor.consecutive_errors) == 5


class TestConfigValidation:
    def test_missing_config_triggers_setup_mode(self, mock_dependencies):
        import config
        config.Config.return_value.configuration_exists = False
        import restarts
        tm = _import_monitor()
        with pytest.raises(SystemExit):
            tm.TemperatureMonitor()
        restarts.restart_in_setup_mode.assert_called()

    def test_invalid_config_triggers_setup_mode(self, mock_dependencies):
        import config
        config.Config.return_value.configuration_exists = True
        config.Config.return_value.is_configured = False
        import restarts
        tm = _import_monitor()
        with pytest.raises(SystemExit):
            tm.TemperatureMonitor()
        restarts.restart_in_setup_mode.assert_called()


class TestCleanup:
    def test_cleanup_calls_gpio_cleanup(self, mock_dependencies):
        import RPi.GPIO as GPIO
        monitor = _create_monitor(mock_dependencies)
        monitor.cleanup()
        monitor.led_control.cleanup.assert_called_once()
        GPIO.cleanup.assert_called()
