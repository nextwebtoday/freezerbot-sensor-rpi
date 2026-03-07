"""
Unit tests for api.py

Tests cover:
- make_api_request builds correct URL, headers, and passes JSON body (mock requests)
- make_api_request_with_creds merges credentials into JSON payload
- set_api_token / clear_api_token write/remove token from .env
- api_token_exists returns correct bool based on env state
- Default host fallback when env var is unset
"""

import pytest
import os
import tempfile
from unittest.mock import patch, MagicMock, call
from pathlib import Path

import api


class TestMakeApiRequest:
    """Test make_api_request function."""

    def test_make_api_request_builds_correct_url(self):
        """make_api_request should build correct URL with default host."""
        with patch('api.requests.request') as mock_request:
            mock_request.return_value = MagicMock(status_code=200)
            
            api.make_api_request('sensors/list', method='GET')
            
            # Verify correct endpoint was called
            call_args = mock_request.call_args
            assert call_args[0][1] == 'https://api.freezerbot.com/api/sensors/list'
            assert call_args[0][0] == 'GET'

    def test_make_api_request_builds_correct_headers(self):
        """make_api_request should set correct headers including auth token."""
        with patch('api.requests.request') as mock_request:
            with patch.dict(os.environ, {api.API_TOKEN: 'test_token_123'}):
                mock_request.return_value = MagicMock(status_code=200)
                
                api.make_api_request('sensors/list')
                
                # Verify headers
                call_args = mock_request.call_args
                headers = call_args[1]['headers']
                assert headers['Authorization'] == 'Bearer test_token_123'
                assert headers['Accept'] == 'application/json'
                assert headers['Content-Type'] == 'application/json'

    def test_make_api_request_passes_json_body(self):
        """make_api_request should pass JSON body to requests."""
        with patch('api.requests.request') as mock_request:
            mock_request.return_value = MagicMock(status_code=200)
            
            test_json = {'sensor_id': 'sensor_1', 'temperature': -70.5}
            api.make_api_request('sensors/update', method='POST', json=test_json)
            
            # Verify JSON was passed
            call_args = mock_request.call_args
            assert call_args[1]['json'] == test_json

    def test_make_api_request_uses_custom_host_from_env(self):
        """make_api_request should use API_HOST from environment if set."""
        with patch('api.requests.request') as mock_request:
            with patch.dict(os.environ, {api.API_HOST: 'https://custom.api.com'}):
                mock_request.return_value = MagicMock(status_code=200)
                
                api.make_api_request('sensors/list', method='GET')
                
                # Verify custom host was used
                call_args = mock_request.call_args
                assert call_args[0][1] == 'https://custom.api.com/api/sensors/list'

    def test_make_api_request_defaults_to_default_host_when_unset(self):
        """make_api_request should use DEFAULT_HOST when API_HOST env var is unset."""
        with patch('api.requests.request') as mock_request:
            with patch.dict(os.environ, {api.API_HOST: ''}, clear=False):
                mock_request.return_value = MagicMock(status_code=200)
                
                # Clear the env var to test fallback
                env_copy = os.environ.copy()
                if api.API_HOST in env_copy:
                    del env_copy[api.API_HOST]
                
                with patch.dict(os.environ, env_copy, clear=True):
                    api.make_api_request('sensors/list')
                    
                    call_args = mock_request.call_args
                    assert 'api.freezerbot.com' in call_args[0][1]

    def test_make_api_request_post_method_default(self):
        """make_api_request should default to POST method."""
        with patch('api.requests.request') as mock_request:
            mock_request.return_value = MagicMock(status_code=200)
            
            api.make_api_request('sensors/create')
            
            # Verify POST was used
            call_args = mock_request.call_args
            assert call_args[0][0] == 'POST'

    def test_make_api_request_empty_json_default(self):
        """make_api_request should default to empty JSON body."""
        with patch('api.requests.request') as mock_request:
            mock_request.return_value = MagicMock(status_code=200)
            
            api.make_api_request('sensors/list', method='GET')
            
            # Verify empty JSON
            call_args = mock_request.call_args
            assert call_args[1]['json'] == {}


class TestMakeApiRequestWithCreds:
    """Test make_api_request_with_creds function."""

    def test_make_api_request_with_creds_merges_credentials(self):
        """make_api_request_with_creds should merge credentials into JSON payload."""
        with patch('api.requests.request') as mock_request:
            mock_request.return_value = MagicMock(status_code=200)
            
            creds = {'email': 'user@example.com', 'password': 'secret123'}
            json_data = {'device_id': 'device_1'}
            
            api.make_api_request_with_creds(creds, 'auth/login', method='POST', json=json_data)
            
            # Verify credentials were merged
            call_args = mock_request.call_args
            sent_json = call_args[1]['json']
            assert sent_json['email'] == 'user@example.com'
            assert sent_json['password'] == 'secret123'
            assert sent_json['device_id'] == 'device_1'

    def test_make_api_request_with_creds_builds_correct_url(self):
        """make_api_request_with_creds should build correct endpoint URL."""
        with patch('api.requests.request') as mock_request:
            mock_request.return_value = MagicMock(status_code=200)
            
            creds = {'email': 'user@example.com', 'password': 'secret123'}
            api.make_api_request_with_creds(creds, 'auth/login')
            
            # Verify endpoint
            call_args = mock_request.call_args
            assert call_args[0][1] == 'https://api.freezerbot.com/api/auth/login'

    def test_make_api_request_with_creds_sets_headers(self):
        """make_api_request_with_creds should set proper headers."""
        with patch('api.requests.request') as mock_request:
            mock_request.return_value = MagicMock(status_code=200)
            
            creds = {'email': 'user@example.com', 'password': 'secret123'}
            api.make_api_request_with_creds(creds, 'auth/login')
            
            # Verify headers
            call_args = mock_request.call_args
            headers = call_args[1]['headers']
            assert headers['Accept'] == 'application/json'
            assert headers['Content-Type'] == 'application/json'

    def test_make_api_request_with_creds_respects_custom_host(self):
        """make_api_request_with_creds should use API_HOST from environment."""
        with patch('api.requests.request') as mock_request:
            with patch.dict(os.environ, {api.API_HOST: 'https://staging.api.com'}):
                mock_request.return_value = MagicMock(status_code=200)
                
                creds = {'email': 'user@example.com', 'password': 'secret123'}
                api.make_api_request_with_creds(creds, 'auth/login')
                
                # Verify custom host was used
                call_args = mock_request.call_args
                assert call_args[0][1] == 'https://staging.api.com/api/auth/login'

    def test_make_api_request_with_creds_credentials_override_json(self):
        """Credentials should be merged last (override any duplicate keys in json)."""
        with patch('api.requests.request') as mock_request:
            mock_request.return_value = MagicMock(status_code=200)
            
            creds = {'password': 'correct_pass'}
            json_data = {'password': 'wrong_pass', 'device': 'device_1'}
            
            api.make_api_request_with_creds(creds, 'auth/login', json=json_data)
            
            # Verify credentials override json
            call_args = mock_request.call_args
            sent_json = call_args[1]['json']
            assert sent_json['password'] == 'correct_pass'


class TestApiToken:
    """Test API token management functions."""

    def test_set_api_token_writes_to_env_file(self):
        """set_api_token should write token to .env file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = os.path.join(tmpdir, '.env')
            
            with patch('api.set_key') as mock_set_key:
                api.set_api_token('token_value_123')
                
                # Verify set_key was called with correct args
                mock_set_key.assert_called_once_with('.env', api.API_TOKEN, 'token_value_123')

    def test_clear_api_token_removes_from_env(self):
        """clear_api_token should remove token from .env file."""
        with patch('api.unset_key') as mock_unset_key:
            api.clear_api_token()
            
            # Verify unset_key was called
            mock_unset_key.assert_called_once_with('.env', api.API_TOKEN)

    def test_api_token_exists_returns_true_when_token_set(self):
        """api_token_exists should return True when API_TOKEN is in environment."""
        with patch.dict(os.environ, {api.API_TOKEN: 'token_123'}):
            assert api.api_token_exists() is True

    def test_api_token_exists_returns_false_when_token_unset(self):
        """api_token_exists should return False when API_TOKEN is not in environment."""
        # Create a clean environment without the token
        env_copy = os.environ.copy()
        if api.API_TOKEN in env_copy:
            del env_copy[api.API_TOKEN]
        
        with patch.dict(os.environ, env_copy, clear=True):
            assert api.api_token_exists() is False

    def test_api_token_exists_loads_dotenv_first(self):
        """api_token_exists should call load_dotenv before checking."""
        with patch('api.load_dotenv') as mock_load:
            with patch.dict(os.environ, {}, clear=True):
                api.api_token_exists()
                
                # Verify load_dotenv was called with override=True
                mock_load.assert_called_once_with(override=True)
