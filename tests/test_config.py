"""
Unit tests for config.py

Tests cover:
- Config loads valid JSON file correctly
- Config handles missing file (configuration_exists=False)
- is_configured logic: email+password present, API token present, neither
- clear_nm_connections parses nmcli output and deletes wifi connections (preserves eduroam)
- Mock subprocess calls for nmcli
"""

import pytest
import os
import json
import tempfile
from unittest.mock import patch, MagicMock, call
from pathlib import Path

import config


class TestConfigLoading:
    """Test Config class initialization and file handling."""

    def test_config_loads_valid_json_file(self):
        """Config should load a valid JSON file correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = os.path.join(tmpdir, 'config.json')
            test_data = {
                'email': 'test@example.com',
                'password': 'testpass',
                'device_name': 'Test Device'
            }
            with open(config_file, 'w') as f:
                json.dump(test_data, f)

            # Patch api_token_exists to return False for this test
            with patch('config.api_token_exists', return_value=False):
                cfg = config.Config(config_file)
                assert cfg.configuration_exists is True
                assert cfg.config == test_data
                assert cfg.config['email'] == 'test@example.com'
                assert cfg.config['password'] == 'testpass'

    def test_config_handles_missing_file(self):
        """Config should handle missing file (configuration_exists=False)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = os.path.join(tmpdir, 'nonexistent.json')

            with patch('config.api_token_exists', return_value=False):
                cfg = config.Config(config_file)
                assert cfg.configuration_exists is False
                assert cfg.config == {}
                assert cfg.is_configured is False


class TestIsConfigured:
    """Test is_configured logic."""

    def test_is_configured_with_email_and_password(self):
        """is_configured should be True when email and password are in config."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = os.path.join(tmpdir, 'config.json')
            test_data = {'email': 'test@example.com', 'password': 'testpass'}
            with open(config_file, 'w') as f:
                json.dump(test_data, f)

            with patch('config.api_token_exists', return_value=False):
                cfg = config.Config(config_file)
                assert cfg.is_configured is True

    def test_is_configured_with_api_token(self):
        """is_configured should be True when api_token_exists returns True."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = os.path.join(tmpdir, 'config.json')
            test_data = {'some_other_key': 'value'}
            with open(config_file, 'w') as f:
                json.dump(test_data, f)

            with patch('config.api_token_exists', return_value=True):
                cfg = config.Config(config_file)
                assert cfg.is_configured is True

    def test_is_configured_false_when_neither(self):
        """is_configured should be False when neither email/password nor API token exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = os.path.join(tmpdir, 'config.json')
            test_data = {'device_name': 'Test Device'}
            with open(config_file, 'w') as f:
                json.dump(test_data, f)

            with patch('config.api_token_exists', return_value=False):
                cfg = config.Config(config_file)
                assert cfg.is_configured is False

    def test_is_configured_false_with_empty_config(self):
        """is_configured should be False with empty config."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = os.path.join(tmpdir, 'config.json')
            with open(config_file, 'w') as f:
                json.dump({}, f)

            with patch('config.api_token_exists', return_value=False):
                cfg = config.Config(config_file)
                assert cfg.is_configured is False

    def test_is_configured_false_missing_password(self):
        """is_configured should be False if only email is present (password missing)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = os.path.join(tmpdir, 'config.json')
            test_data = {'email': 'test@example.com'}
            with open(config_file, 'w') as f:
                json.dump(test_data, f)

            with patch('config.api_token_exists', return_value=False):
                cfg = config.Config(config_file)
                assert cfg.is_configured is False


class TestConfigMethods:
    """Test Config instance methods."""

    def test_clear_config_deletes_file(self):
        """clear_config should delete the config file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = os.path.join(tmpdir, 'config.json')
            test_data = {'email': 'test@example.com', 'password': 'testpass'}
            with open(config_file, 'w') as f:
                json.dump(test_data, f)

            with patch('config.api_token_exists', return_value=False):
                cfg = config.Config(config_file)
                assert os.path.exists(config_file)
                cfg.clear_config()
                assert not os.path.exists(config_file)

    def test_save_new_config_writes_json(self):
        """save_new_config should write JSON to file and update self.config."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = os.path.join(tmpdir, 'config.json')
            with open(config_file, 'w') as f:
                json.dump({}, f)

            with patch('config.api_token_exists', return_value=False):
                cfg = config.Config(config_file)
                new_config = {'email': 'new@example.com', 'password': 'newpass', 'device_name': 'NewDevice'}
                cfg.save_new_config(new_config)

                # Verify file was written
                with open(config_file, 'r') as f:
                    saved_data = json.load(f)
                assert saved_data == new_config

                # Verify self.config updated
                assert cfg.config == new_config

    def test_save_device_name_updates_config(self):
        """save_device_name should update device_name in config and save."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = os.path.join(tmpdir, 'config.json')
            test_data = {'email': 'test@example.com', 'password': 'testpass'}
            with open(config_file, 'w') as f:
                json.dump(test_data, f)

            with patch('config.api_token_exists', return_value=False):
                cfg = config.Config(config_file)
                cfg.save_device_name('NewDeviceName')

                # Verify config was updated
                assert cfg.config['device_name'] == 'NewDeviceName'

                # Verify file was written
                with open(config_file, 'r') as f:
                    saved_data = json.load(f)
                assert saved_data['device_name'] == 'NewDeviceName'

    def test_clear_creds_from_config_removes_email_and_password(self):
        """clear_creds_from_config should remove email and password."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = os.path.join(tmpdir, 'config.json')
            test_data = {
                'email': 'test@example.com',
                'password': 'testpass',
                'device_name': 'TestDevice'
            }
            with open(config_file, 'w') as f:
                json.dump(test_data, f)

            with patch('config.api_token_exists', return_value=False):
                cfg = config.Config(config_file)
                cfg.clear_creds_from_config()

                assert 'email' not in cfg.config
                assert 'password' not in cfg.config
                assert cfg.config['device_name'] == 'TestDevice'

                # Verify file was written
                with open(config_file, 'r') as f:
                    saved_data = json.load(f)
                assert 'email' not in saved_data
                assert 'password' not in saved_data

    def test_add_config_error_updates_config(self):
        """add_config_error should add error to config and save."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = os.path.join(tmpdir, 'config.json')
            test_data = {'email': 'test@example.com', 'password': 'testpass'}
            with open(config_file, 'w') as f:
                json.dump(test_data, f)

            with patch('config.api_token_exists', return_value=False):
                cfg = config.Config(config_file)
                error_msg = 'Connection failed'
                cfg.add_config_error(error_msg)

                assert cfg.config['error'] == error_msg

                # Verify file was written
                with open(config_file, 'r') as f:
                    saved_data = json.load(f)
                assert saved_data['error'] == error_msg


class TestClearNmConnections:
    """Test clear_nm_connections function."""

    def test_clear_nm_connections_deletes_wifi_except_eduroam(self):
        """clear_nm_connections should delete wifi connections except eduroam."""
        nmcli_output = "eth0:ethernet\nwifi-home:wifi\neduroam:wifi\nwifi-guest:wifi\n"

        mock_run_show = MagicMock()
        mock_run_show.stdout = nmcli_output
        mock_run_show.stderr = ""

        with patch('config.subprocess.run') as mock_run:
            # First call is the 'show' command
            mock_run.side_effect = [
                mock_run_show,
                MagicMock(),  # wifi-home delete
                MagicMock(),  # wifi-guest delete
            ]

            config.clear_nm_connections()

            # Verify show was called
            assert mock_run.call_count == 3
            show_call = mock_run.call_args_list[0]
            assert show_call[0][0] == ["/usr/bin/nmcli", "-t", "-f", "NAME,TYPE", "connection", "show"]

            # Verify delete was called for wifi-home
            delete_call_1 = mock_run.call_args_list[1]
            assert delete_call_1[0][0] == ["/usr/bin/nmcli", "connection", "delete", "wifi-home"]

            # Verify delete was called for wifi-guest
            delete_call_2 = mock_run.call_args_list[2]
            assert delete_call_2[0][0] == ["/usr/bin/nmcli", "connection", "delete", "wifi-guest"]

    def test_clear_nm_connections_preserves_eduroam(self):
        """clear_nm_connections should preserve eduroam connection."""
        nmcli_output = """eth0:ethernet
        eduroam:wifi
        """

        mock_run_show = MagicMock()
        mock_run_show.stdout = nmcli_output

        with patch('config.subprocess.run') as mock_run:
            mock_run.return_value = mock_run_show

            config.clear_nm_connections()

            # Only the show command should be called (no deletes)
            assert mock_run.call_count == 1

    def test_clear_nm_connections_no_wifi_connections(self):
        """clear_nm_connections should handle no wifi connections."""
        nmcli_output = """eth0:ethernet
        """

        mock_run_show = MagicMock()
        mock_run_show.stdout = nmcli_output

        with patch('config.subprocess.run') as mock_run:
            mock_run.return_value = mock_run_show

            config.clear_nm_connections()

            # Only the show command should be called
            assert mock_run.call_count == 1

    def test_clear_nm_connections_empty_output(self):
        """clear_nm_connections should handle empty nmcli output."""
        nmcli_output = ""

        mock_run_show = MagicMock()
        mock_run_show.stdout = nmcli_output

        with patch('config.subprocess.run') as mock_run:
            mock_run.return_value = mock_run_show

            config.clear_nm_connections()

            # Only the show command should be called
            assert mock_run.call_count == 1
