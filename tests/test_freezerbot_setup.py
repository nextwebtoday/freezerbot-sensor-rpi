"""Unit tests for freezerbot_setup.py (FRE-118)"""
import sys
import pytest
from unittest.mock import patch, MagicMock, mock_open, call


@pytest.fixture(autouse=True)
def mock_dependencies():
    """Mock all dependencies before importing freezerbot_setup."""
    mocks = {}

    # Mock RPi.GPIO
    sys.modules['RPi'] = MagicMock()
    sys.modules['RPi.GPIO'] = MagicMock()

    # Mock config
    mock_config = MagicMock()
    mock_config_inst = MagicMock()
    mock_config_inst.configuration_exists = False
    mock_config_inst.is_configured = False
    mock_config_inst.config = {}
    mock_config_inst.save_new_config = MagicMock()
    mock_config.return_value = mock_config_inst
    mocks['config_cls'] = mock_config
    mocks['config_inst'] = mock_config_inst
    
    # Mock clear_nm_connections
    mocks['clear_nm_connections'] = MagicMock()
    
    config_mod = MagicMock()
    config_mod.Config = mock_config
    config_mod.clear_nm_connections = mocks['clear_nm_connections']
    sys.modules['config'] = config_mod

    # Mock led_control
    mock_led = MagicMock()
    mock_led_inst = MagicMock()
    mock_led.return_value = mock_led_inst
    mocks['led_cls'] = mock_led
    mocks['led_inst'] = mock_led_inst
    
    led_mod = MagicMock()
    led_mod.LedControl = mock_led
    sys.modules['led_control'] = led_mod

    # Mock restarts
    mock_restarts = MagicMock()
    sys.modules['restarts'] = mock_restarts
    mocks['restarts'] = mock_restarts

    # Remove cached module to force reimport with fresh mocks
    sys.modules.pop('freezerbot_setup', None)

    # Save original module state so we can restore hardware mocks after cleanup
    saved_modules = {k: sys.modules.get(k) for k in ['RPi', 'RPi.GPIO']}

    yield mocks

    # Cleanup — only remove app-level modules, not hardware mocks
    for mod_name in ['freezerbot_setup', 'config', 'led_control', 'restarts']:
        sys.modules.pop(mod_name, None)

    # Restore hardware mock modules so other test files (e.g. test_led_control.py)
    # that rely on conftest's hardware mocks still work after this fixture runs
    for mod_name, mod in saved_modules.items():
        if mod is not None:
            sys.modules[mod_name] = mod


def _import_setup():
    sys.modules.pop('freezerbot_setup', None)
    import freezerbot_setup
    return freezerbot_setup


def _create_setup(mock_deps):
    # If the module was already imported (e.g. by @patch decorators), reuse it
    # so that any active patches on the module remain in effect.
    fbs = sys.modules.get('freezerbot_setup') or _import_setup()
    return fbs.FreezerBotSetup()


class TestInitialization:
    def test_creates_config_instance(self, mock_dependencies):
        setup = _create_setup(mock_dependencies)
        assert setup.config is not None
        mock_dependencies['config_cls'].assert_called_once()

    def test_creates_led_control_instance(self, mock_dependencies):
        setup = _create_setup(mock_dependencies)
        assert setup.led_control is not None
        mock_dependencies['led_cls'].assert_called_once()

    def test_creates_flask_app(self, mock_dependencies):
        setup = _create_setup(mock_dependencies)
        assert setup.app is not None
        assert setup.app.name == 'freezerbot_setup'

    def test_sets_up_routes(self, mock_dependencies):
        setup = _create_setup(mock_dependencies)
        # Verify routes are registered
        route_rules = [rule.rule for rule in setup.app.url_map.iter_rules()]
        assert '/' in route_rules
        assert '/api/scan-wifi' in route_rules
        assert '/api/get-config' in route_rules
        assert '/api/setup' in route_rules
        assert '/api/create-account' in route_rules
        assert '/generate_204' in route_rules
        assert '/ncsi.txt' in route_rules
        assert '/hotspot-detect.html' in route_rules
        assert '/success.txt' in route_rules
        assert '/connecttest.txt' in route_rules


class TestFlaskRoutes:
    def test_index_returns_template(self, mock_dependencies):
        setup = _create_setup(mock_dependencies)
        with setup.app.test_client() as client:
            response = client.get('/')
            assert response.status_code == 200

    def test_get_config_returns_json(self, mock_dependencies):
        mock_dependencies['config_inst'].config = {'email': 'test@example.com'}
        setup = _create_setup(mock_dependencies)
        with setup.app.test_client() as client:
            response = client.get('/api/get-config')
            assert response.status_code == 200
            assert response.json == {'email': 'test@example.com'}

    def test_captive_portal_redirect(self, mock_dependencies):
        setup = _create_setup(mock_dependencies)
        with setup.app.test_client() as client:
            for endpoint in ['/generate_204', '/ncsi.txt', '/hotspot-detect.html', '/success.txt', '/connecttest.txt']:
                response = client.get(endpoint)
                assert response.status_code == 302  # Redirect
                assert response.location == '/'


class TestCreateAccount:
    @patch('freezerbot_setup.subprocess.run')
    @patch('freezerbot_setup.sleep')
    def test_stops_and_starts_hostapd(self, mock_sleep, mock_subprocess, mock_dependencies):
        setup = _create_setup(mock_dependencies)
        with setup.app.test_client() as client:
            response = client.post('/api/create-account')
            assert response.status_code == 200
            assert response.json == {'success': True}
            
            # Verify hostapd was stopped then started
            calls = mock_subprocess.call_args_list
            assert call(["/usr/bin/systemctl", "stop", "hostapd.service"]) in calls
            assert call(["/usr/bin/systemctl", "start", "hostapd.service"]) in calls
            mock_sleep.assert_called_once_with(5)


class TestWiFiScanning:
    @patch('freezerbot_setup.subprocess.run')
    def test_scan_wifi_returns_networks(self, mock_subprocess, mock_dependencies):
        mock_result = MagicMock()
        mock_result.stdout = '''
          Cell 01 - Address: AA:BB:CC:DD:EE:FF
                    ESSID:"TestNetwork1"
          Cell 02 - Address: 11:22:33:44:55:66
                    ESSID:"TestNetwork2"
        '''
        mock_subprocess.return_value = mock_result
        
        setup = _create_setup(mock_dependencies)
        with setup.app.test_client() as client:
            response = client.get('/api/scan-wifi')
            assert response.status_code == 200
            assert 'TestNetwork1' in response.json['networks']
            assert 'TestNetwork2' in response.json['networks']
            
        mock_subprocess.assert_called_once_with(
            ["/usr/sbin/iwlist", "wlan0", "scan"],
            capture_output=True,
            text=True
        )

    @patch('freezerbot_setup.subprocess.run')
    def test_scan_wifi_deduplicates_networks(self, mock_subprocess, mock_dependencies):
        mock_result = MagicMock()
        mock_result.stdout = '''
          ESSID:"Network1"
          ESSID:"Network1"
          ESSID:"Network2"
        '''
        mock_subprocess.return_value = mock_result
        
        setup = _create_setup(mock_dependencies)
        with setup.app.test_client() as client:
            response = client.get('/api/scan-wifi')
            assert response.json['networks'] == ['Network1', 'Network2']

    @patch('freezerbot_setup.subprocess.run')
    def test_scan_wifi_handles_error(self, mock_subprocess, mock_dependencies):
        mock_subprocess.side_effect = Exception("Scan failed")
        
        setup = _create_setup(mock_dependencies)
        with setup.app.test_client() as client:
            response = client.get('/api/scan-wifi')
            assert response.status_code == 200
            assert 'error' in response.json
            assert response.json['networks'] == []


class TestSaveConfig:
    @patch('freezerbot_setup.threading.Thread')
    @patch('freezerbot_setup.subprocess.run')
    def test_save_config_success(self, mock_subprocess, mock_thread, mock_dependencies):
        setup = _create_setup(mock_dependencies)
        
        config_data = {
            'networks': [{'ssid': 'TestWiFi', 'password': 'testpass'}],
            'email': 'test@example.com',
            'password': 'password123',
            'device_name': 'Test Sensor'
        }
        
        with setup.app.test_client() as client:
            response = client.post('/api/setup', json=config_data)
            assert response.status_code == 200
            assert response.json == {'success': True}
            
        # Verify config was saved
        mock_dependencies['config_inst'].save_new_config.assert_called_once_with(config_data)
        
        # Verify network setup was called
        mock_dependencies['clear_nm_connections'].assert_called_once()
        
        # Verify restart thread was created and started
        mock_thread.assert_called_once()
        mock_thread.return_value.start.assert_called_once()

    def test_save_config_validates_networks(self, mock_dependencies):
        setup = _create_setup(mock_dependencies)
        
        # Missing networks
        with setup.app.test_client() as client:
            response = client.post('/api/setup', json={
                'email': 'test@example.com',
                'password': 'pass',
                'device_name': 'Sensor'
            })
            assert response.json['success'] is False
            assert 'WiFi network' in response.json['error']

    def test_save_config_validates_email(self, mock_dependencies):
        setup = _create_setup(mock_dependencies)
        
        with setup.app.test_client() as client:
            response = client.post('/api/setup', json={
                'networks': [{'ssid': 'Test', 'password': 'pass'}],
                'password': 'pass',
                'device_name': 'Sensor'
            })
            assert response.json['success'] is False
            assert 'Email' in response.json['error']

    def test_save_config_validates_password(self, mock_dependencies):
        setup = _create_setup(mock_dependencies)
        
        with setup.app.test_client() as client:
            response = client.post('/api/setup', json={
                'networks': [{'ssid': 'Test', 'password': 'pass'}],
                'email': 'test@example.com',
                'device_name': 'Sensor'
            })
            assert response.json['success'] is False
            assert 'Password' in response.json['error']

    def test_save_config_validates_device_name(self, mock_dependencies):
        setup = _create_setup(mock_dependencies)
        
        with setup.app.test_client() as client:
            response = client.post('/api/setup', json={
                'networks': [{'ssid': 'Test', 'password': 'pass'}],
                'email': 'test@example.com',
                'password': 'pass123'
            })
            assert response.json['success'] is False
            assert 'Sensor name' in response.json['error']

    @patch('freezerbot_setup.subprocess.run')
    def test_save_config_handles_error(self, mock_subprocess, mock_dependencies):
        mock_dependencies['config_inst'].save_new_config.side_effect = Exception("Save failed")
        setup = _create_setup(mock_dependencies)
        
        config_data = {
            'networks': [{'ssid': 'Test', 'password': 'pass'}],
            'email': 'test@example.com',
            'password': 'pass123',
            'device_name': 'Sensor'
        }
        
        with setup.app.test_client() as client:
            response = client.post('/api/setup', json=config_data)
            assert response.json['success'] is False
            assert 'error' in response.json
            
        # Verify LED was set to error state
        mock_dependencies['led_inst'].set_state.assert_called_with('error')


class TestNetworkManagerSetup:
    @patch('freezerbot_setup.subprocess.run')
    def test_setup_regular_wifi(self, mock_subprocess, mock_dependencies):
        setup = _create_setup(mock_dependencies)
        networks = [{'ssid': 'TestWiFi', 'password': 'testpass123'}]
        
        setup.setup_network_manager(networks)
        
        # Verify clear was called
        mock_dependencies['clear_nm_connections'].assert_called_once()
        
        # Verify nmcli was called to add connection
        add_call = None
        modify_call = None
        for c in mock_subprocess.call_args_list:
            args = c[0][0]
            if 'add' in args:
                add_call = args
            if 'modify' in args:
                modify_call = args
        
        assert add_call is not None
        assert 'TestWiFi' in add_call
        assert 'testpass123' in add_call
        assert 'wpa-psk' in add_call
        
        assert modify_call is not None
        assert 'TestWiFi' in modify_call

    @patch('freezerbot_setup.subprocess.run')
    def test_setup_enterprise_wifi(self, mock_subprocess, mock_dependencies):
        setup = _create_setup(mock_dependencies)
        networks = [{
            'ssid': 'EnterpriseNet',
            'password': 'pass',
            'enterprise': True,
            'username': 'user@example.com',
            'eap_method': 'peap',
            'phase2_auth': 'mschapv2'
        }]
        
        setup.setup_network_manager(networks)
        
        # Find the add call
        add_call = None
        for c in mock_subprocess.call_args_list:
            args = c[0][0]
            if 'add' in args and 'EnterpriseNet' in args:
                add_call = args
                break
        
        assert add_call is not None
        assert 'wpa-eap' in add_call
        assert 'user@example.com' in add_call
        assert 'peap' in add_call
        assert 'mschapv2' in add_call

    @patch('freezerbot_setup.subprocess.run')
    @patch('builtins.open', new_callable=mock_open)
    def test_setup_enterprise_wifi_with_ca_cert(self, mock_file, mock_subprocess, mock_dependencies):
        setup = _create_setup(mock_dependencies)
        networks = [{
            'ssid': 'SecureNet',
            'password': 'pass',
            'enterprise': True,
            'username': 'user@example.com',
            'ca_cert_content': '-----BEGIN CERTIFICATE-----\ntest\n-----END CERTIFICATE-----'
        }]
        
        setup.setup_network_manager(networks)
        
        # Verify CA cert was written
        mock_file.assert_called()
        write_calls = [c for c in mock_file().write.call_args_list]
        assert len(write_calls) > 0

    @patch('freezerbot_setup.subprocess.run')
    def test_setup_multiple_networks(self, mock_subprocess, mock_dependencies):
        setup = _create_setup(mock_dependencies)
        networks = [
            {'ssid': 'Network1', 'password': 'pass1'},
            {'ssid': 'Network2', 'password': 'pass2'}
        ]
        
        setup.setup_network_manager(networks)
        
        # Verify both networks were added
        call_args_str = ' '.join([str(c[0][0]) for c in mock_subprocess.call_args_list])
        assert 'Network1' in call_args_str
        assert 'Network2' in call_args_str

    @patch('freezerbot_setup.subprocess.run')
    def test_skips_incomplete_networks(self, mock_subprocess, mock_dependencies):
        setup = _create_setup(mock_dependencies)
        networks = [
            {'ssid': 'ValidNetwork', 'password': 'pass'},
            {'ssid': '', 'password': 'pass'},  # Missing SSID
            {'ssid': 'NoPassword', 'password': ''},  # Missing password
        ]
        
        setup.setup_network_manager(networks)
        
        # Only ValidNetwork should be added
        call_args_str = ' '.join([str(c[0][0]) for c in mock_subprocess.call_args_list])
        assert 'ValidNetwork' in call_args_str
        assert 'NoPassword' not in call_args_str


class TestDelayedRestart:
    @patch('freezerbot_setup.time.sleep')
    def test_delayed_restart_waits_then_restarts(self, mock_sleep, mock_dependencies):
        setup = _create_setup(mock_dependencies)
        
        setup.delayed_restart()
        
        mock_sleep.assert_called_once_with(10)
        mock_dependencies['restarts'].restart_in_sensor_mode.assert_called_once()

    @patch('freezerbot_setup.time.sleep')
    def test_delayed_restart_handles_error(self, mock_sleep, mock_dependencies):
        mock_dependencies['restarts'].restart_in_sensor_mode.side_effect = Exception("Restart failed")
        setup = _create_setup(mock_dependencies)
        
        # Should not raise, should set LED to error
        setup.delayed_restart()
        
        mock_dependencies['led_inst'].set_state.assert_called_with('error')


class TestStartHotspot:
    @patch('builtins.open', new_callable=mock_open)
    @patch('freezerbot_setup.subprocess.run')
    def test_start_hotspot_creates_unique_name(self, mock_subprocess, mock_file, mock_dependencies):
        cpuinfo_content = "Serial\t\t: 00000000abcd1234"
        mock_file.return_value.read.return_value = cpuinfo_content
        
        # Mock subprocess to return 'active' for service checks
        def subprocess_side_effect(cmd, **kwargs):
            result = MagicMock()
            if 'is-active' in cmd:
                result.stdout = 'active'
            else:
                result.stdout = ''
            return result
        mock_subprocess.side_effect = subprocess_side_effect
        
        setup = _create_setup(mock_dependencies)
        setup.start_hotspot()
        
        # Verify hostapd config contains unique serial suffix
        write_calls = [str(c) for c in mock_file().write.call_args_list]
        assert any('Freezerbot-Setup-1234' in call for call in write_calls)

    @patch('builtins.open', new_callable=mock_open)
    @patch('freezerbot_setup.subprocess.run')
    def test_start_hotspot_configures_services(self, mock_subprocess, mock_file, mock_dependencies):
        # Mock subprocess to return 'active' for service checks
        def subprocess_side_effect(cmd, **kwargs):
            result = MagicMock()
            if 'is-active' in cmd:
                result.stdout = 'active'
            else:
                result.stdout = ''
            return result
        mock_subprocess.side_effect = subprocess_side_effect
        
        setup = _create_setup(mock_dependencies)
        setup.start_hotspot()
        
        # Verify services were restarted
        call_args_list = [c[0][0] for c in mock_subprocess.call_args_list]
        restart_calls = [c for c in call_args_list if 'restart' in c]
        assert any('dnsmasq' in ' '.join(c) for c in restart_calls)
        assert any('hostapd' in ' '.join(c) for c in restart_calls)

    @patch('builtins.open', new_callable=mock_open)
    @patch('freezerbot_setup.subprocess.run')
    @patch('freezerbot_setup.sleep')
    def test_start_hotspot_retries_on_failure(self, mock_sleep, mock_subprocess, mock_file, mock_dependencies):
        # Mock subprocess to return 'inactive' for first 2 attempts, then 'active'
        call_count = [0]
        def subprocess_side_effect(cmd, **kwargs):
            result = MagicMock()
            if 'is-active' in cmd:
                call_count[0] += 1
                if call_count[0] < 4:  # Fail first 2 attempts (2 checks per attempt)
                    result.stdout = 'inactive'
                else:
                    result.stdout = 'active'
            else:
                result.stdout = ''
            return result
        mock_subprocess.side_effect = subprocess_side_effect
        
        setup = _create_setup(mock_dependencies)
        setup.start_hotspot()
        
        # Verify sleep was called for retries
        assert mock_sleep.call_count >= 1

    @patch('builtins.open', new_callable=mock_open)
    @patch('freezerbot_setup.subprocess.run')
    def test_start_hotspot_raises_after_max_retries(self, mock_subprocess, mock_file, mock_dependencies):
        # Mock subprocess to always return 'inactive'
        def subprocess_side_effect(cmd, **kwargs):
            result = MagicMock()
            result.stdout = 'inactive'
            return result
        mock_subprocess.side_effect = subprocess_side_effect
        
        setup = _create_setup(mock_dependencies)
        
        with pytest.raises(Exception, match="Failed to start services"):
            setup.start_hotspot()
        
        # Verify LED was set to error
        mock_dependencies['led_inst'].set_state.assert_called_with('error')


class TestRunMethod:
    @patch('freezerbot_setup.FreezerBotSetup')
    def test_run_enters_setup_mode_when_not_configured(self, mock_cls, mock_dependencies):
        mock_dependencies['config_inst'].configuration_exists = False
        mock_dependencies['config_inst'].is_configured = False
        
        mock_instance = MagicMock()
        mock_instance.config = mock_dependencies['config_inst']
        mock_instance.led_control = mock_dependencies['led_inst']
        mock_cls.return_value = mock_instance
        
        fbs = _import_setup()
        setup = fbs.FreezerBotSetup()
        
        # Manually set to not configured to test the logic
        setup.config.configuration_exists = False
        setup.config.is_configured = False
        
        # Mock the methods we don't want to actually execute
        setup.start_hotspot = MagicMock()
        setup.app = MagicMock()
        
        setup.run()
        
        setup.start_hotspot.assert_called_once()
        mock_dependencies['led_inst'].set_state.assert_called_with('setup')
        setup.app.run.assert_called_once_with(host="0.0.0.0", port=80)

    def test_run_exits_when_already_configured(self, mock_dependencies):
        mock_dependencies['config_inst'].configuration_exists = True
        mock_dependencies['config_inst'].is_configured = True
        
        setup = _create_setup(mock_dependencies)
        
        setup.run()
        
        # Verify restart was called instead of starting setup
        mock_dependencies['restarts'].restart_in_sensor_mode.assert_called_once()


class TestCleanup:
    def test_cleanup_calls_led_cleanup(self, mock_dependencies):
        setup = _create_setup(mock_dependencies)
        setup.cleanup()
        
        mock_dependencies['led_inst'].cleanup.assert_called_once()

    @patch('freezerbot_setup.GPIO')
    def test_cleanup_calls_gpio_cleanup(self, mock_gpio, mock_dependencies):
        setup = _create_setup(mock_dependencies)
        setup.cleanup()
        
        mock_gpio.cleanup.assert_called_once()
