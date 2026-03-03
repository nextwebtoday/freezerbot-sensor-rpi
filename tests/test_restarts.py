from unittest.mock import patch, call
import restarts


class TestRestartInSetupMode:
    @patch("restarts.subprocess.run")
    @patch("restarts.time.sleep")
    def test_sleeps_2_seconds_at_start(self, mock_sleep, mock_run):
        restarts.restart_in_setup_mode()
        mock_sleep.assert_called_once_with(2)

    @patch("restarts.subprocess.run")
    @patch("restarts.time.sleep")
    def test_enables_setup_disables_monitor(self, mock_sleep, mock_run):
        restarts.restart_in_setup_mode()
        mock_run.assert_any_call(["/usr/bin/systemctl", "enable", "freezerbot-setup.service"])
        mock_run.assert_any_call(["/usr/bin/systemctl", "restart", "freezerbot-setup.service"])
        mock_run.assert_any_call(["/usr/bin/systemctl", "disable", "freezerbot-monitor.service"])
        mock_run.assert_any_call(["/usr/bin/systemctl", "stop", "freezerbot-monitor.service"])

    @patch("restarts.subprocess.run")
    @patch("restarts.time.sleep")
    def test_correct_call_order(self, mock_sleep, mock_run):
        restarts.restart_in_setup_mode()
        assert mock_run.call_args_list == [
            call(["/usr/bin/systemctl", "enable", "freezerbot-setup.service"]),
            call(["/usr/bin/systemctl", "restart", "freezerbot-setup.service"]),
            call(["/usr/bin/systemctl", "disable", "freezerbot-monitor.service"]),
            call(["/usr/bin/systemctl", "stop", "freezerbot-monitor.service"]),
        ]


class TestRestartInSensorMode:
    @patch("restarts.subprocess.run")
    @patch("restarts.time.sleep")
    def test_stops_services_and_enables_monitor(self, mock_sleep, mock_run):
        restarts.restart_in_sensor_mode()
        mock_run.assert_any_call(["/usr/bin/systemctl", "stop", "hostapd.service"])
        mock_run.assert_any_call(["/usr/bin/systemctl", "stop", "dnsmasq.service"])
        mock_run.assert_any_call(["/usr/bin/nmcli", "device", "set", "wlan0", "managed", "yes"])
        mock_run.assert_any_call(["/usr/bin/systemctl", "restart", "NetworkManager.service"])
        mock_run.assert_any_call(["/usr/bin/systemctl", "enable", "freezerbot-monitor.service"])
        mock_run.assert_any_call(["/usr/bin/systemctl", "restart", "freezerbot-monitor.service"])
        mock_run.assert_any_call(["/usr/bin/systemctl", "disable", "freezerbot-setup.service"])
        mock_run.assert_any_call(["/usr/bin/systemctl", "stop", "freezerbot-setup.service"])

    @patch("restarts.subprocess.run")
    @patch("restarts.time.sleep")
    def test_sleeps_5_seconds_after_network_manager_restart(self, mock_sleep, mock_run):
        restarts.restart_in_sensor_mode()
        mock_sleep.assert_called_once_with(5)

    @patch("restarts.subprocess.run")
    @patch("restarts.time.sleep")
    def test_correct_call_order(self, mock_sleep, mock_run):
        restarts.restart_in_sensor_mode()
        assert mock_run.call_args_list == [
            call(["/usr/bin/systemctl", "stop", "hostapd.service"]),
            call(["/usr/bin/systemctl", "stop", "dnsmasq.service"]),
            call(["/usr/bin/nmcli", "device", "set", "wlan0", "managed", "yes"]),
            call(["/usr/bin/systemctl", "restart", "NetworkManager.service"]),
            call(["/usr/bin/systemctl", "enable", "freezerbot-monitor.service"]),
            call(["/usr/bin/systemctl", "restart", "freezerbot-monitor.service"]),
            call(["/usr/bin/systemctl", "disable", "freezerbot-setup.service"]),
            call(["/usr/bin/systemctl", "stop", "freezerbot-setup.service"]),
        ]
