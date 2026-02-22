import unittest
import tempfile
import os
import time
import threading
import multiprocessing
import json
from unittest.mock import patch, MagicMock, mock_open
import sys

# Mock GPIO before importing LedControl
sys.modules['RPi'] = MagicMock()
sys.modules['RPi.GPIO'] = MagicMock()


class TestLedControlCoordination(unittest.TestCase):

    def setUp(self):
        """Set up test environment with temporary files"""
        self.temp_dir = tempfile.mkdtemp()
        self.led_state_file = os.path.join(self.temp_dir, "led_state.json")

        # Patch the led_state_file path in the module
        self.led_state_patcher = patch('led_control.led_state_file', self.led_state_file)
        self.led_state_patcher.start()

        # Mock GPIO operations
        self.gpio_patcher = patch('led_control.GPIO')
        self.mock_gpio = self.gpio_patcher.start()

        # Create initial state file
        self.initial_state = {"current_state": None}
        self.save_state(self.initial_state)

    def tearDown(self):
        """Clean up test environment"""
        self.led_state_patcher.stop()
        self.gpio_patcher.stop()

        # Clean up temp files
        if os.path.exists(self.led_state_file):
            os.remove(self.led_state_file)
        os.rmdir(self.temp_dir)

    def save_state(self, state):
        """Helper to save state to the test file"""
        with open(self.led_state_file, 'w') as f:
            json.dump(state, f)

    def load_state(self):
        """Helper to load state from the test file"""
        with open(self.led_state_file, 'r') as f:
            return json.load(f)


class TestCoordinationFileOperations(TestLedControlCoordination):
    """Test the file-based coordination logic"""

    @patch('led_control.os.getpid')
    def test_register_pattern_thread_updates_file(self, mock_getpid):
        """Test that registering a pattern thread updates the coordination file"""
        mock_getpid.return_value = 1234

        from led_control import LedControl
        led_control = LedControl()

        led_control.register_pattern_thread()

        state = self.load_state()
        self.assertEqual(state['active_pattern_pid'], 1234)
        self.assertIn('pattern_timestamp', state)

    @patch('led_control.os.getpid')
    def test_signal_stop_to_other_pattern_creates_stop_request(self, mock_getpid):
        """Test that signaling creates proper stop request in file"""
        mock_getpid.return_value = 5678

        from led_control import LedControl
        led_control = LedControl()

        led_control.signal_stop_to_other_pattern(1234)

        state = self.load_state()
        self.assertEqual(state['stop_request_for_pid'], 1234)
        self.assertEqual(state['requesting_pid'], 5678)
        self.assertIn('stop_request_timestamp', state)

    @patch('led_control.os.getpid')
    def test_clear_stop_request_removes_fields(self, mock_getpid):
        """Test that clearing stop request removes coordination fields"""
        mock_getpid.return_value = 5678

        # Set up initial state with stop request
        initial_state = {
            "current_state": "wifi_issue",
            "stop_request_for_pid": 1234,
            "requesting_pid": 5678
        }
        self.save_state(initial_state)

        from led_control import LedControl
        led_control = LedControl()

        led_control.clear_stop_request()

        state = self.load_state()
        self.assertNotIn('stop_request_for_pid', state)
        self.assertNotIn('requesting_pid', state)
        self.assertEqual(state['current_state'], 'wifi_issue')  # Other fields preserved


class TestPatternThreadCoordination(TestLedControlCoordination):
    """Test the actual thread coordination behavior"""

    @patch('led_control.os.getpid')
    @patch('led_control.time.sleep')  # Speed up the test
    def test_monitoring_thread_detects_stop_signal(self, mock_sleep, mock_getpid):
        """Test that the monitoring thread detects and acts on stop signals"""
        mock_getpid.return_value = 1234
        mock_sleep.return_value = None  # Make sleep instant

        from led_control import LedControl
        led_control = LedControl()

        # Start a mock pattern thread
        pattern_stopped = threading.Event()

        def mock_pattern():
            pattern_stopped.wait(5)  # Wait for stop signal or timeout

        led_control.pattern_thread = threading.Thread(target=mock_pattern)
        led_control.pattern_thread.daemon = True
        led_control.pattern_thread.start()

        # Give monitoring thread time to start
        time.sleep(0.1)

        # Signal this process to stop its pattern
        state = self.load_state()
        state['stop_request_for_pid'] = 1234
        state['requesting_pid'] = 5678
        self.save_state(state)

        # Give monitoring thread time to detect and act
        time.sleep(0.2)

        # Verify the pattern thread was stopped
        self.assertFalse(led_control.pattern_thread.is_alive())

        # Verify stop request was cleared
        final_state = self.load_state()
        self.assertNotIn('stop_request_for_pid', final_state)

    @patch('led_control.os.getpid')
    def test_start_pattern_thread_signals_existing_controller(self, mock_getpid):
        """Test that starting a pattern thread signals existing controllers to stop"""
        mock_getpid.return_value = 5678

        # Set up state with existing pattern controller
        initial_state = {
            "current_state": None,
            "active_pattern_pid": 1234,
            "pattern_timestamp": time.time()
        }
        self.save_state(initial_state)

        from led_control import LedControl
        led_control = LedControl()

        # Mock the pattern function to avoid infinite loop
        def mock_wifi_pattern():
            time.sleep(0.1)

        with patch.object(led_control, 'wifi_issue_pattern', mock_wifi_pattern):
            led_control.start_pattern_thread(mock_wifi_pattern)

        # Verify stop signal was sent to existing controller
        state = self.load_state()
        self.assertEqual(state.get('stop_request_for_pid'), 1234)
        self.assertEqual(state.get('requesting_pid'), 5678)

        # Verify new controller is registered
        time.sleep(0.4)  # Wait for coordination delay
        state = self.load_state()
        self.assertEqual(state.get('active_pattern_pid'), 5678)


def simulate_led_control_process(process_id, test_duration=2, led_state_file=None):
    """Function to run in separate process for integration testing"""
    import sys
    import time
    import threading

    # Mock GPIO for subprocess
    sys.modules['RPi'] = MagicMock()
    sys.modules['RPi.GPIO'] = MagicMock()

    if led_state_file:
        # Patch the led_state_file path
        import led_control
        led_control.led_state_file = led_state_file

    from led_control import LedControl

    # Mock os.getpid to return our process_id
    with patch('led_control.os.getpid', return_value=process_id):
        led_control = LedControl()

        pattern_running = threading.Event()

        def mock_wifi_pattern():
            pattern_running.set()
            while not led_control.pattern_stop_event.is_set():
                if led_control.pattern_stop_event.wait(0.1):
                    break
            pattern_running.clear()

        # Replace the pattern with our mock
        led_control.wifi_issue_pattern = mock_wifi_pattern

        # Start wifi issue pattern
        led_control.set_state("wifi_issue")

        # Run for test duration
        start_time = time.time()
        while time.time() - start_time < test_duration:
            time.sleep(0.1)

            # Check if our pattern is running
            if pattern_running.is_set():
                print(f"Process {process_id}: Pattern is running")

        led_control.cleanup()
        return f"Process {process_id} completed"


class TestCrossProcessCoordination(TestLedControlCoordination):
    """Integration tests with actual multiple processes"""

    def test_multiple_processes_only_one_pattern_runs(self):
        """Test that when multiple processes try to run patterns, only the newest succeeds"""

        # Start first process
        process1 = multiprocessing.Process(
            target=simulate_led_control_process,
            args=(1111, 3, self.led_state_file)
        )
        process1.start()

        # Give first process time to start pattern
        time.sleep(0.5)

        # Verify first process registered itself
        state = self.load_state()
        self.assertEqual(state.get('active_pattern_pid'), 1111)

        # Start second process
        process2 = multiprocessing.Process(
            target=simulate_led_control_process,
            args=(2222, 2, self.led_state_file)
        )
        process2.start()

        # Give second process time to signal first process
        time.sleep(0.8)

        # Verify second process took over
        state = self.load_state()
        self.assertEqual(state.get('active_pattern_pid'), 2222)

        # Clean up processes
        process1.join(timeout=5)
        process2.join(timeout=5)

        if process1.is_alive():
            process1.terminate()
        if process2.is_alive():
            process2.terminate()

    def test_process_cleanup_removes_pattern_registration(self):
        """Test that process cleanup removes its pattern registration"""

        # Start process
        process = multiprocessing.Process(
            target=simulate_led_control_process,
            args=(3333, 1, self.led_state_file)
        )
        process.start()

        # Give process time to register
        time.sleep(0.5)

        # Verify process registered
        state = self.load_state()
        self.assertEqual(state.get('active_pattern_pid'), 3333)

        # Wait for process to complete cleanup
        process.join(timeout=5)

        # Give cleanup time to complete
        time.sleep(0.2)

        # Verify registration was removed
        state = self.load_state()
        self.assertNotIn('active_pattern_pid', state)


class TestRobustnessAndErrorHandling(TestLedControlCoordination):
    """Test error conditions and edge cases"""

    @patch('led_control.os.getpid')
    def test_corrupted_state_file_handled_gracefully(self, mock_getpid):
        """Test that corrupted state file doesn't crash the system"""
        mock_getpid.return_value = 1234

        # Write corrupted JSON to state file
        with open(self.led_state_file, 'w') as f:
            f.write("{ invalid json }")

        from led_control import LedControl

        # Should not raise exception
        led_control = LedControl()

        # Should be able to register pattern thread despite corrupted file
        led_control.register_pattern_thread()

    @patch('led_control.os.getpid')
    def test_missing_state_file_creates_new_one(self, mock_getpid):
        """Test that missing state file gets created"""
        mock_getpid.return_value = 1234

        # Remove state file
        os.remove(self.led_state_file)

        from led_control import LedControl
        led_control = LedControl()

        led_control.register_pattern_thread()

        # Verify file was created
        self.assertTrue(os.path.exists(self.led_state_file))

        # Verify content is correct
        state = self.load_state()
        self.assertEqual(state['active_pattern_pid'], 1234)


if __name__ == '__main__':
    # Run tests with different levels of verbosity
    unittest.main(verbosity=2)