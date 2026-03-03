"""Unit tests for start.py (FRE-122)"""
import sys
import pytest
from unittest.mock import patch, MagicMock, call


@pytest.fixture(autouse=True)
def mock_dependencies():
    """Mock all dependencies before importing start."""
    # Mock config module
    mock_config_cls = MagicMock()
    config_mod = MagicMock()
    config_mod.Config = mock_config_cls
    sys.modules['config'] = config_mod

    # Remove cached start module to force reimport with fresh mocks
    sys.modules.pop('start', None)

    yield {'config_cls': mock_config_cls}

    # Cleanup
    for mod_name in ['start', 'config']:
        sys.modules.pop(mod_name, None)


def _import_start():
    sys.modules.pop('start', None)
    import start
    return start


class TestEnsureUpdaterIsActive:
    """Tests for ensure_updater_is_active()"""

    @patch('subprocess.run')
    def test_enables_updater_timer(self, mock_run, mock_dependencies):
        start = _import_start()
        start.ensure_updater_is_active()
        mock_run.assert_any_call(["sudo", "systemctl", "enable", "freezerbot-updater.timer"])

    @patch('subprocess.run')
    def test_restarts_updater_timer(self, mock_run, mock_dependencies):
        start = _import_start()
        start.ensure_updater_is_active()
        mock_run.assert_any_call(["sudo", "systemctl", "restart", "freezerbot-updater.timer"])

    @patch('subprocess.run')
    def test_calls_exactly_two_commands(self, mock_run, mock_dependencies):
        start = _import_start()
        start.ensure_updater_is_active()
        assert mock_run.call_count == 2


class TestDetermineMode:
    """Tests for determine_mode()"""

    @patch('subprocess.run')
    def test_configured_starts_monitor_service(self, mock_run, mock_dependencies):
        mock_dependencies['config_cls'].return_value.is_configured = True
        start = _import_start()
        start.determine_mode()

        mock_run.assert_any_call(["sudo", "systemctl", "enable", "freezerbot-monitor.service"])
        mock_run.assert_any_call(["sudo", "systemctl", "restart", "freezerbot-monitor.service"])

    @patch('subprocess.run')
    def test_configured_stops_setup_service(self, mock_run, mock_dependencies):
        mock_dependencies['config_cls'].return_value.is_configured = True
        start = _import_start()
        start.determine_mode()

        mock_run.assert_any_call(["sudo", "systemctl", "disable", "freezerbot-setup.service"])
        mock_run.assert_any_call(["sudo", "systemctl", "stop", "freezerbot-setup.service"])

    @patch('subprocess.run')
    def test_unconfigured_starts_setup_service(self, mock_run, mock_dependencies):
        mock_dependencies['config_cls'].return_value.is_configured = False
        start = _import_start()
        start.determine_mode()

        mock_run.assert_any_call(["sudo", "systemctl", "enable", "freezerbot-setup.service"])
        mock_run.assert_any_call(["sudo", "systemctl", "restart", "freezerbot-setup.service"])

    @patch('subprocess.run')
    def test_unconfigured_stops_monitor_service(self, mock_run, mock_dependencies):
        mock_dependencies['config_cls'].return_value.is_configured = False
        start = _import_start()
        start.determine_mode()

        mock_run.assert_any_call(["sudo", "systemctl", "disable", "freezerbot-monitor.service"])
        mock_run.assert_any_call(["sudo", "systemctl", "stop", "freezerbot-monitor.service"])

    @patch('subprocess.run')
    def test_always_ensures_updater_active(self, mock_run, mock_dependencies):
        """Updater timer should be enabled regardless of config state."""
        mock_dependencies['config_cls'].return_value.is_configured = True
        start = _import_start()
        start.determine_mode()

        mock_run.assert_any_call(["sudo", "systemctl", "enable", "freezerbot-updater.timer"])
        mock_run.assert_any_call(["sudo", "systemctl", "restart", "freezerbot-updater.timer"])

    @patch('subprocess.run')
    def test_configured_runs_six_commands_total(self, mock_run, mock_dependencies):
        """2 updater + 4 service commands = 6 total."""
        mock_dependencies['config_cls'].return_value.is_configured = True
        start = _import_start()
        start.determine_mode()
        assert mock_run.call_count == 6

    @patch('subprocess.run')
    def test_unconfigured_runs_six_commands_total(self, mock_run, mock_dependencies):
        mock_dependencies['config_cls'].return_value.is_configured = False
        start = _import_start()
        start.determine_mode()
        assert mock_run.call_count == 6

    @patch('subprocess.run')
    def test_configured_prints_monitor_message(self, mock_run, mock_dependencies, capsys):
        mock_dependencies['config_cls'].return_value.is_configured = True
        start = _import_start()
        start.determine_mode()
        captured = capsys.readouterr()
        assert 'starting freezerbot-monitor.service' in captured.out

    @patch('subprocess.run')
    def test_unconfigured_prints_setup_message(self, mock_run, mock_dependencies, capsys):
        mock_dependencies['config_cls'].return_value.is_configured = False
        start = _import_start()
        start.determine_mode()
        captured = capsys.readouterr()
        assert 'starting freezerbot-setup.service' in captured.out

    @patch('subprocess.run')
    def test_updater_called_before_service_commands(self, mock_run, mock_dependencies):
        """ensure_updater_is_active should run before the service enable/disable logic."""
        mock_dependencies['config_cls'].return_value.is_configured = True
        start = _import_start()
        start.determine_mode()

        calls = mock_run.call_args_list
        # First two calls should be the updater timer
        assert calls[0] == call(["sudo", "systemctl", "enable", "freezerbot-updater.timer"])
        assert calls[1] == call(["sudo", "systemctl", "restart", "freezerbot-updater.timer"])

    @patch('subprocess.run')
    def test_configured_does_not_enable_setup_service(self, mock_run, mock_dependencies):
        """When configured, setup service should be disabled, not enabled."""
        mock_dependencies['config_cls'].return_value.is_configured = True
        start = _import_start()
        start.determine_mode()

        enable_calls = [c for c in mock_run.call_args_list
                        if c == call(["sudo", "systemctl", "enable", "freezerbot-setup.service"])]
        assert len(enable_calls) == 0

    @patch('subprocess.run')
    def test_unconfigured_does_not_enable_monitor_service(self, mock_run, mock_dependencies):
        """When unconfigured, monitor service should be disabled, not enabled."""
        mock_dependencies['config_cls'].return_value.is_configured = False
        start = _import_start()
        start.determine_mode()

        enable_calls = [c for c in mock_run.call_args_list
                        if c == call(["sudo", "systemctl", "enable", "freezerbot-monitor.service"])]
        assert len(enable_calls) == 0
