"""Unit tests for firmware_updater.py (FRE-117)"""
import sys
import os
import json
import pytest
from unittest.mock import patch, MagicMock, mock_open, call
from datetime import datetime


def _import_firmware_updater():
    """Fresh-import firmware_updater module."""
    for mod_name in list(sys.modules.keys()):
        if 'firmware_updater' in mod_name:
            del sys.modules[mod_name]
    
    # Mock dependencies
    sys.modules['api'] = MagicMock()
    sys.modules['config'] = MagicMock()
    sys.modules['device_info'] = MagicMock()
    sys.modules['temperature_monitor'] = MagicMock()
    
    import firmware_updater
    return firmware_updater


@pytest.fixture
def mock_env_enabled():
    """Environment with updater enabled"""
    with patch.dict(os.environ, {'FIRMWARE_UPDATER_ENABLED': 'true'}):
        yield


@pytest.fixture
def mock_env_disabled():
    """Environment with updater disabled"""
    with patch.dict(os.environ, {'FIRMWARE_UPDATER_ENABLED': 'false'}):
        yield


@pytest.fixture
def mock_filesystem():
    """Mock filesystem operations"""
    with patch('os.path.exists') as mock_exists, \
         patch('os.makedirs') as mock_makedirs, \
         patch('builtins.open', mock_open()) as mock_file:
        mock_exists.return_value = True
        yield {
            'exists': mock_exists,
            'makedirs': mock_makedirs,
            'open': mock_file
        }


@pytest.fixture
def mock_subprocess():
    """Mock subprocess operations"""
    with patch('subprocess.run') as mock_run:
        result = MagicMock()
        result.returncode = 0
        result.stdout = ''
        result.stderr = ''
        mock_run.return_value = result
        yield mock_run


class TestEnabledDisabledToggle:
    """Test enabled/disabled state via FIRMWARE_UPDATER_ENABLED env var"""

    def test_enabled_by_default(self, mock_filesystem, mock_subprocess):
        """Updater should be enabled when env var is not set"""
        firmware_updater = _import_firmware_updater()
        
        with patch.dict(os.environ, {}, clear=True), \
             patch('firmware_updater.Config'), \
             patch('firmware_updater.DeviceInfo'), \
             patch('logging.basicConfig'), \
             patch.object(firmware_updater.FirmwareUpdater, 'load_update_history', return_value={"attempts": [], "last_success": 0}):
            updater = firmware_updater.FirmwareUpdater()
            assert updater.enabled is True

    def test_explicitly_enabled(self, mock_env_enabled, mock_filesystem, mock_subprocess):
        """Updater should be enabled when env var is 'true'"""
        firmware_updater = _import_firmware_updater()
        
        with patch('firmware_updater.Config'), \
             patch('firmware_updater.DeviceInfo'), \
             patch('logging.basicConfig'), \
             patch.object(firmware_updater.FirmwareUpdater, 'load_update_history', return_value={"attempts": [], "last_success": 0}):
            updater = firmware_updater.FirmwareUpdater()
            assert updater.enabled is True

    def test_explicitly_disabled(self, mock_env_disabled, mock_filesystem, mock_subprocess):
        """Updater should be disabled when env var is 'false'"""
        firmware_updater = _import_firmware_updater()
        
        with patch('firmware_updater.Config'), \
             patch('firmware_updater.DeviceInfo'), \
             patch('logging.basicConfig'), \
             patch.object(firmware_updater.FirmwareUpdater, 'load_update_history', return_value={"attempts": [], "last_success": 0}):
            updater = firmware_updater.FirmwareUpdater()
            assert updater.enabled is False

    def test_run_exits_when_disabled(self, mock_env_disabled, mock_filesystem, mock_subprocess):
        """run() should exit immediately when disabled"""
        firmware_updater = _import_firmware_updater()
        
        with patch('firmware_updater.Config'), \
             patch('firmware_updater.DeviceInfo'), \
             patch('logging.basicConfig'), \
             patch.object(firmware_updater.FirmwareUpdater, 'load_update_history', return_value={"attempts": [], "last_success": 0}), \
             patch.object(firmware_updater.FirmwareUpdater, 'updates_are_available') as mock_check:
            updater = firmware_updater.FirmwareUpdater()
            updater.run()
            mock_check.assert_not_called()


class TestVersionComparison:
    """Test version comparison logic using git commit hashes"""

    def test_no_updates_when_commits_match(self, mock_env_enabled, mock_filesystem):
        """updates_are_available should return False when commits match"""
        firmware_updater = _import_firmware_updater()
        
        with patch('firmware_updater.Config'), \
             patch('firmware_updater.DeviceInfo'), \
             patch('logging.basicConfig'), \
             patch.object(firmware_updater.FirmwareUpdater, 'load_update_history', return_value={"attempts": [], "last_success": 0}), \
             patch('os.chdir'), \
             patch('subprocess.run') as mock_run:
            
            # Setup mock responses
            fetch_result = MagicMock(returncode=0, stdout='', stderr='')
            current_result = MagicMock(returncode=0, stdout='abc123\n', stderr='')
            remote_result = MagicMock(returncode=0, stdout='abc123\n', stderr='')
            
            mock_run.side_effect = [fetch_result, current_result, remote_result]
            
            updater = firmware_updater.FirmwareUpdater()
            has_updates = updater.updates_are_available()
            
            assert has_updates is False

    def test_updates_when_commits_differ(self, mock_env_enabled, mock_filesystem):
        """updates_are_available should return True when commits differ"""
        firmware_updater = _import_firmware_updater()
        
        with patch('firmware_updater.Config'), \
             patch('firmware_updater.DeviceInfo'), \
             patch('logging.basicConfig'), \
             patch.object(firmware_updater.FirmwareUpdater, 'load_update_history', return_value={"attempts": [], "last_success": 0}), \
             patch('os.chdir'), \
             patch('subprocess.run') as mock_run:
            
            # Setup mock responses
            fetch_result = MagicMock(returncode=0, stdout='', stderr='')
            current_result = MagicMock(returncode=0, stdout='abc123\n', stderr='')
            remote_result = MagicMock(returncode=0, stdout='def456\n', stderr='')
            
            mock_run.side_effect = [fetch_result, current_result, remote_result]
            
            updater = firmware_updater.FirmwareUpdater()
            has_updates = updater.updates_are_available()
            
            assert has_updates is True

    def test_git_fetch_failure(self, mock_env_enabled, mock_filesystem):
        """updates_are_available should return False on git fetch failure"""
        firmware_updater = _import_firmware_updater()
        
        with patch('firmware_updater.Config'), \
             patch('firmware_updater.DeviceInfo'), \
             patch('logging.basicConfig'), \
             patch.object(firmware_updater.FirmwareUpdater, 'load_update_history', return_value={"attempts": [], "last_success": 0}), \
             patch('os.chdir'), \
             patch('subprocess.run') as mock_run:
            
            # git fetch fails
            fetch_result = MagicMock(returncode=1, stdout='', stderr='network error')
            mock_run.side_effect = [fetch_result]
            
            updater = firmware_updater.FirmwareUpdater()
            has_updates = updater.updates_are_available()
            
            assert has_updates is False


class TestGitPullAndInstallScript:
    """Test git pull and install script execution (mocked subprocess)"""

    def test_apply_update_runs_git_reset(self, mock_env_enabled, mock_filesystem):
        """apply_update should run git reset --hard origin/main"""
        firmware_updater = _import_firmware_updater()
        
        with patch('firmware_updater.Config'), \
             patch('firmware_updater.DeviceInfo'), \
             patch('logging.basicConfig'), \
             patch.object(firmware_updater.FirmwareUpdater, 'load_update_history', return_value={"attempts": [], "last_success": 0}), \
             patch.object(firmware_updater.FirmwareUpdater, 'save_update_history'), \
             patch.object(firmware_updater.FirmwareUpdater, 'verify_and_handle_rollback', return_value=True), \
             patch('os.chdir'), \
             patch('subprocess.run') as mock_run:
            
            mock_run.return_value = MagicMock(returncode=0, stdout='', stderr='')
            
            updater = firmware_updater.FirmwareUpdater()
            updater.apply_update('/fake/backup')
            
            # Check that git reset was called
            git_reset_calls = [call for call in mock_run.call_args_list if '/usr/bin/git' in str(call) and 'reset' in str(call)]
            assert len(git_reset_calls) > 0

    def test_apply_update_runs_install_script(self, mock_env_enabled, mock_filesystem):
        """apply_update should run install.sh"""
        firmware_updater = _import_firmware_updater()
        
        with patch('firmware_updater.Config'), \
             patch('firmware_updater.DeviceInfo'), \
             patch('logging.basicConfig'), \
             patch.object(firmware_updater.FirmwareUpdater, 'load_update_history', return_value={"attempts": [], "last_success": 0}), \
             patch.object(firmware_updater.FirmwareUpdater, 'save_update_history'), \
             patch.object(firmware_updater.FirmwareUpdater, 'verify_and_handle_rollback', return_value=True), \
             patch('os.chdir'), \
             patch('subprocess.run') as mock_run:
            
            mock_run.return_value = MagicMock(returncode=0, stdout='', stderr='')
            
            updater = firmware_updater.FirmwareUpdater()
            updater.apply_update('/fake/backup')
            
            # Check that install.sh was called
            install_calls = [call for call in mock_run.call_args_list if 'install.sh' in str(call)]
            assert len(install_calls) > 0

    def test_apply_update_runs_pip_install(self, mock_env_enabled, mock_filesystem):
        """apply_update should run pip install requirements"""
        firmware_updater = _import_firmware_updater()
        
        with patch('firmware_updater.Config'), \
             patch('firmware_updater.DeviceInfo'), \
             patch('logging.basicConfig'), \
             patch.object(firmware_updater.FirmwareUpdater, 'load_update_history', return_value={"attempts": [], "last_success": 0}), \
             patch.object(firmware_updater.FirmwareUpdater, 'save_update_history'), \
             patch.object(firmware_updater.FirmwareUpdater, 'verify_and_handle_rollback', return_value=True), \
             patch('os.chdir'), \
             patch('subprocess.run') as mock_run:
            
            mock_run.return_value = MagicMock(returncode=0, stdout='', stderr='')
            
            updater = firmware_updater.FirmwareUpdater()
            updater.apply_update('/fake/backup')
            
            # Check that pip install was called
            pip_calls = [call for call in mock_run.call_args_list if 'pip' in str(call) and 'install' in str(call)]
            assert len(pip_calls) > 0


class TestRollbackLogic:
    """Test rollback logic on failed update with attempt counting"""

    def test_rollback_on_first_failure(self, mock_env_enabled, mock_filesystem):
        """Should rollback on first update failure"""
        firmware_updater = _import_firmware_updater()
        
        with patch('firmware_updater.Config'), \
             patch('firmware_updater.DeviceInfo'), \
             patch('logging.basicConfig'), \
             patch.object(firmware_updater.FirmwareUpdater, 'load_update_history', return_value={"attempts": [], "last_success": 0}), \
             patch.object(firmware_updater.FirmwareUpdater, 'save_update_history'), \
             patch.object(firmware_updater.FirmwareUpdater, 'rollback_to_backup') as mock_rollback, \
             patch('os.chdir'), \
             patch('subprocess.run') as mock_run:
            
            # Make git reset fail
            mock_run.side_effect = Exception("git reset failed")
            
            updater = firmware_updater.FirmwareUpdater()
            result = updater.apply_update('/fake/backup')
            
            assert result is False
            mock_rollback.assert_called_once_with('/fake/backup')

    def test_rollback_on_second_failure(self, mock_env_enabled, mock_filesystem):
        """Should rollback on second update failure (failure_count = 1)"""
        firmware_updater = _import_firmware_updater()
        
        with patch('firmware_updater.Config'), \
             patch('firmware_updater.DeviceInfo'), \
             patch('logging.basicConfig'), \
             patch.object(firmware_updater.FirmwareUpdater, 'load_update_history', return_value={
                 "attempts": [{"timestamp": 1234567890, "failure_count": 0}], 
                 "last_success": 0
             }), \
             patch.object(firmware_updater.FirmwareUpdater, 'save_update_history'), \
             patch.object(firmware_updater.FirmwareUpdater, 'rollback_to_backup') as mock_rollback, \
             patch('os.chdir'), \
             patch('subprocess.run') as mock_run:
            
            # Make git reset fail
            mock_run.side_effect = Exception("git reset failed")
            
            updater = firmware_updater.FirmwareUpdater()
            result = updater.apply_update('/fake/backup')
            
            assert result is False
            mock_rollback.assert_called_once_with('/fake/backup')

    def test_rollback_restores_backup(self, mock_env_enabled, mock_filesystem):
        """rollback_to_backup should restore from backup path"""
        firmware_updater = _import_firmware_updater()
        
        with patch('firmware_updater.Config'), \
             patch('firmware_updater.DeviceInfo'), \
             patch('logging.basicConfig'), \
             patch.object(firmware_updater.FirmwareUpdater, 'load_update_history', return_value={"attempts": [], "last_success": 0}), \
             patch('os.path.exists', return_value=True), \
             patch('subprocess.run') as mock_run:
            
            mock_run.return_value = MagicMock(returncode=0, stdout='', stderr='')
            
            updater = firmware_updater.FirmwareUpdater()
            result = updater.rollback_to_backup('/fake/backup')
            
            assert result is True
            # Check that mv command was called to restore backup
            mv_calls = [call for call in mock_run.call_args_list if '/usr/bin/mv' in str(call)]
            assert len(mv_calls) > 0

    def test_attempt_count_increments(self, mock_env_enabled, mock_filesystem):
        """Each apply_update should increment attempt count"""
        firmware_updater = _import_firmware_updater()
        
        initial_attempts = []
        
        with patch('firmware_updater.Config'), \
             patch('firmware_updater.DeviceInfo'), \
             patch('logging.basicConfig'), \
             patch.object(firmware_updater.FirmwareUpdater, 'load_update_history', return_value={
                 "attempts": initial_attempts, 
                 "last_success": 0
             }), \
             patch.object(firmware_updater.FirmwareUpdater, 'verify_and_handle_rollback', return_value=True), \
             patch('os.chdir'), \
             patch('subprocess.run') as mock_run:
            
            mock_run.return_value = MagicMock(returncode=0, stdout='', stderr='')
            
            updater = firmware_updater.FirmwareUpdater()
            initial_count = len(updater.update_history["attempts"])
            updater.apply_update('/fake/backup')
            
            assert len(updater.update_history["attempts"]) == initial_count + 1


class TestRecoveryBootstrapEdgeCase:
    """Test Recovery Level 2: 3rd attempt skips backup and verification"""

    def test_third_attempt_skips_backup(self, mock_env_enabled, mock_filesystem):
        """run() should skip backup creation on 3rd attempt (failure_count >= 2)"""
        firmware_updater = _import_firmware_updater()
        
        with patch('firmware_updater.Config'), \
             patch('firmware_updater.DeviceInfo'), \
             patch('logging.basicConfig'), \
             patch.object(firmware_updater.FirmwareUpdater, 'load_update_history', return_value={
                 "attempts": [
                     {"timestamp": 1234567890, "failure_count": 0},
                     {"timestamp": 1234567900, "failure_count": 1}
                 ], 
                 "last_success": 0
             }), \
             patch.object(firmware_updater.FirmwareUpdater, 'updates_are_available', return_value=True), \
             patch.object(firmware_updater.FirmwareUpdater, 'create_timestamped_backup') as mock_backup, \
             patch.object(firmware_updater.FirmwareUpdater, 'apply_update', return_value=True):
            
            updater = firmware_updater.FirmwareUpdater()
            updater.run()
            
            # Backup should not be called when failure_count >= 2
            mock_backup.assert_not_called()

    def test_third_attempt_no_rollback_on_failure(self, mock_env_enabled, mock_filesystem):
        """apply_update should NOT rollback on 3rd attempt even if it fails"""
        firmware_updater = _import_firmware_updater()
        
        with patch('firmware_updater.Config'), \
             patch('firmware_updater.DeviceInfo'), \
             patch('logging.basicConfig'), \
             patch.object(firmware_updater.FirmwareUpdater, 'load_update_history', return_value={
                 "attempts": [
                     {"timestamp": 1234567890, "failure_count": 0},
                     {"timestamp": 1234567900, "failure_count": 1}
                 ], 
                 "last_success": 0
             }), \
             patch.object(firmware_updater.FirmwareUpdater, 'save_update_history'), \
             patch.object(firmware_updater.FirmwareUpdater, 'rollback_to_backup') as mock_rollback, \
             patch.object(firmware_updater.FirmwareUpdater, 'clear_update_history'), \
             patch('os.chdir'), \
             patch('subprocess.run') as mock_run:
            
            # Make git reset fail
            mock_run.side_effect = Exception("git reset failed")
            
            updater = firmware_updater.FirmwareUpdater()
            result = updater.apply_update(None)  # No backup path for level 2
            
            # Should NOT rollback at recovery level 2
            mock_rollback.assert_not_called()

    def test_third_attempt_skips_verification(self, mock_env_enabled, mock_filesystem):
        """apply_update should skip service verification on 3rd attempt"""
        firmware_updater = _import_firmware_updater()
        
        with patch('firmware_updater.Config'), \
             patch('firmware_updater.DeviceInfo'), \
             patch('logging.basicConfig'), \
             patch.object(firmware_updater.FirmwareUpdater, 'load_update_history', return_value={
                 "attempts": [
                     {"timestamp": 1234567890, "failure_count": 0},
                     {"timestamp": 1234567900, "failure_count": 1}
                 ], 
                 "last_success": 0
             }), \
             patch.object(firmware_updater.FirmwareUpdater, 'save_update_history'), \
             patch.object(firmware_updater.FirmwareUpdater, 'verify_and_handle_rollback') as mock_verify, \
             patch.object(firmware_updater.FirmwareUpdater, 'clear_update_history'), \
             patch('os.chdir'), \
             patch('subprocess.run') as mock_run:
            
            mock_run.return_value = MagicMock(returncode=0, stdout='', stderr='')
            
            updater = firmware_updater.FirmwareUpdater()
            result = updater.apply_update(None)
            
            # Should NOT call verify_and_handle_rollback for recovery level 2
            mock_verify.assert_not_called()
            assert result is True  # Should return True even without verification


class TestUpdateHistory:
    """Test update history management"""

    def test_load_nonexistent_history(self, mock_env_enabled):
        """Should return default history when file doesn't exist"""
        firmware_updater = _import_firmware_updater()
        
        with patch('firmware_updater.Config'), \
             patch('firmware_updater.DeviceInfo'), \
             patch('logging.basicConfig'), \
             patch('os.path.exists', return_value=False):
            
            updater = firmware_updater.FirmwareUpdater()
            assert updater.update_history == {"attempts": [], "last_success": 0}

    def test_load_existing_history(self, mock_env_enabled):
        """Should load existing history from file"""
        firmware_updater = _import_firmware_updater()
        
        existing_history = {
            "attempts": [{"timestamp": 1234567890, "failure_count": 0}],
            "last_success": 1234567800
        }
        
        with patch('firmware_updater.Config'), \
             patch('firmware_updater.DeviceInfo'), \
             patch('logging.basicConfig'), \
             patch('os.path.exists', return_value=True), \
             patch('builtins.open', mock_open(read_data=json.dumps(existing_history))):
            
            updater = firmware_updater.FirmwareUpdater()
            assert updater.update_history["attempts"][0]["timestamp"] == 1234567890
            assert updater.update_history["last_success"] == 1234567800

    def test_clear_history_on_success(self, mock_env_enabled, mock_filesystem):
        """Should clear attempt history and set last_success on successful update"""
        firmware_updater = _import_firmware_updater()
        
        with patch('firmware_updater.Config'), \
             patch('firmware_updater.DeviceInfo'), \
             patch('logging.basicConfig'), \
             patch.object(firmware_updater.FirmwareUpdater, 'load_update_history', return_value={
                 "attempts": [{"timestamp": 1234567890, "failure_count": 0}], 
                 "last_success": 0
             }), \
             patch.object(firmware_updater.FirmwareUpdater, 'save_update_history'), \
             patch.object(firmware_updater.FirmwareUpdater, 'update_device_info_json'):
            
            updater = firmware_updater.FirmwareUpdater()
            updater.update_history["attempts"] = [{"timestamp": 1234567890}]
            updater.clear_update_history()
            
            assert updater.update_history["attempts"] == []
            assert updater.update_history["last_success"] > 0
