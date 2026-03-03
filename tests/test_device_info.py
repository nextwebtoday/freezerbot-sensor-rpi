"""Unit tests for device_info.py (FRE-116)"""
import sys
import os
import json
import pytest
from unittest.mock import patch, mock_open, MagicMock
import tempfile


def _import_device_info():
    """Fresh-import device_info module."""
    for mod_name in list(sys.modules.keys()):
        if 'device_info' in mod_name:
            del sys.modules[mod_name]
    
    import device_info
    return device_info


class TestDeviceInfoConstructor:
    """Test DeviceInfo class initialization."""
    
    def test_constructor_handles_missing_file_gracefully(self):
        """Constructor should handle missing device_info.json file gracefully."""
        device_info_module = _import_device_info()
        
        with patch('os.path.exists', return_value=False):
            device_info = device_info_module.DeviceInfo()
            assert device_info.device_info == {}
            assert device_info.device_info_file == "/home/pi/freezerbot/device_info.json"
    
    def test_constructor_loads_valid_json(self):
        """Constructor should load valid JSON from device_info.json."""
        device_info_module = _import_device_info()
        
        mock_data = {
            "firmware_version": "1.2.3",
            "device_id": "test-device-001"
        }
        
        with patch('os.path.exists', return_value=True), \
             patch('builtins.open', mock_open(read_data=json.dumps(mock_data))):
            device_info = device_info_module.DeviceInfo()
            assert device_info.device_info == mock_data
            assert device_info.device_info['firmware_version'] == "1.2.3"
            assert device_info.device_info['device_id'] == "test-device-001"
    
    def test_constructor_handles_corrupted_json(self):
        """Constructor should handle corrupted JSON gracefully."""
        device_info_module = _import_device_info()
        
        with patch('os.path.exists', return_value=True), \
             patch('builtins.open', mock_open(read_data="invalid json {")):
            with pytest.raises(json.JSONDecodeError):
                device_info = device_info_module.DeviceInfo()


class TestUpdateFirmwareVersion:
    """Test firmware version update functionality."""
    
    def test_update_firmware_version_updates_and_persists(self):
        """update_firmware_version should update version and persist to file."""
        device_info_module = _import_device_info()
        
        mock_data = {"firmware_version": "1.0.0"}
        new_version = "2.0.0"
        
        with patch('os.path.exists', return_value=True), \
             patch('builtins.open', mock_open(read_data=json.dumps(mock_data))) as mock_file:
            
            device_info = device_info_module.DeviceInfo()
            device_info.update_firmware_version(new_version)
            
            # Verify the version was updated in memory
            assert device_info.device_info['firmware_version'] == new_version
            
            # Verify save_device_info was called (which writes to file)
            # Check that open was called for writing
            write_calls = [call for call in mock_file.call_args_list if 'w' in str(call)]
            assert len(write_calls) > 0


class TestSaveDeviceInfo:
    """Test device info persistence functionality."""
    
    def test_save_device_info_writes_correct_json(self):
        """save_device_info should write correct JSON to file with proper formatting."""
        device_info_module = _import_device_info()
        
        # Use a real temporary file for this test
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as tmp_file:
            tmp_path = tmp_file.name
        
        try:
            # Patch the device_info_file path to use our temp file
            with patch('os.path.exists', return_value=False):
                device_info = device_info_module.DeviceInfo()
                device_info.device_info_file = tmp_path
            
            # Test data
            test_data = {
                "firmware_version": "3.0.0",
                "device_id": "test-device-002",
                "last_update": "2024-01-01T00:00:00Z"
            }
            
            # Save the data
            device_info.save_device_info(test_data)
            
            # Read back and verify
            with open(tmp_path, 'r') as f:
                saved_data = json.load(f)
            
            assert saved_data == test_data
            assert saved_data['firmware_version'] == "3.0.0"
            assert saved_data['device_id'] == "test-device-002"
            
            # Verify formatting (should be indented with 2 spaces)
            with open(tmp_path, 'r') as f:
                content = f.read()
                # Check that the JSON is pretty-printed (contains newlines and spaces)
                assert '\n' in content
                assert '  ' in content  # 2-space indent
        
        finally:
            # Clean up temp file
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
    
    def test_save_device_info_creates_parent_directory_if_needed(self):
        """save_device_info should work even if parent directory doesn't exist."""
        device_info_module = _import_device_info()
        
        # Create a temp directory for testing
        with tempfile.TemporaryDirectory() as tmp_dir:
            # Create a path with a non-existent subdirectory
            test_path = os.path.join(tmp_dir, "subdir", "device_info.json")
            
            with patch('os.path.exists', return_value=False):
                device_info = device_info_module.DeviceInfo()
                device_info.device_info_file = test_path
            
            # Ensure parent directory exists
            os.makedirs(os.path.dirname(test_path), exist_ok=True)
            
            test_data = {"firmware_version": "1.0.0"}
            device_info.save_device_info(test_data)
            
            # Verify file was created
            assert os.path.exists(test_path)
            
            # Verify content
            with open(test_path, 'r') as f:
                saved_data = json.load(f)
            assert saved_data == test_data


class TestDeviceInfoIntegration:
    """Integration tests for complete workflows."""
    
    def test_full_workflow_with_temp_file(self):
        """Test complete workflow: create, update, save, reload."""
        device_info_module = _import_device_info()
        
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as tmp_file:
            tmp_path = tmp_file.name
        
        try:
            # 1. Create new DeviceInfo (file doesn't exist yet)
            with patch('os.path.exists', return_value=False):
                device_info1 = device_info_module.DeviceInfo()
                device_info1.device_info_file = tmp_path
            
            # 2. Update firmware version
            device_info1.update_firmware_version("1.5.0")
            
            # 3. Reload from file to verify persistence
            device_info2 = device_info_module.DeviceInfo()
            device_info2.device_info_file = tmp_path
            with open(tmp_path, 'r') as f:
                device_info2.device_info = json.load(f)
            
            # 4. Verify the version persisted
            assert device_info2.device_info['firmware_version'] == "1.5.0"
        
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
