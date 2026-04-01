import json
import os
import subprocess

import RPi.GPIO as GPIO
import time
import sys
import threading
import traceback

from dotenv import load_dotenv

from api import clear_api_token
from restarts import restart_in_setup_mode
from config import Config

LED_CONTROL_DISABLED = 'LED_DISABLED'
BUTTON_PIN = 17
LED_PIN = 27

led_state_file = "/home/pi/led_state.json"
def load_state()-> dict[str, None|str|int|bool|float]:
    try:
        if os.path.exists(led_state_file):
            with open(led_state_file, 'r') as f:
                return json.load(f)
        else:
            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(led_state_file), exist_ok=True)
            # Return default values
            return {
                'current_state': None
            }
    except Exception as e:
        print(f"Error getting led state: {traceback.format_exc()}")
        return {
            'current_state': None
        }

def save_led_state(led_state):
    try:
        os.makedirs(os.path.dirname(led_state_file), exist_ok=True)

        with open(led_state_file, 'w') as f:
            json.dump(led_state, f, indent=2)
        return True
    except Exception as e:
        print(f"Error saving led state: {traceback.format_exc()}")
        return False


class LedControl:
    """Class for controlling the button's built-in LED with singleton pattern"""

    # Class variable to track the single instance
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        """Ensure only one instance of LedControl exists"""
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(LedControl, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        """Initialize the LED control with the specified pin"""
        # Skip initialization if already done
        if self._initialized:
            return

        self._initialized = True

        load_dotenv(override=True)
        self.module_disabled = os.getenv(LED_CONTROL_DISABLED) == 'true'
        self.led_disabled = False
        self.button_disabled = False
        self.config = Config()

        self.BUTTON_PIN = BUTTON_PIN
        self.LED_PIN = LED_PIN
        self.led_state = load_state()
        self.current_state = self.led_state['current_state']
        self.pattern_thread = None
        self.pwm = None
        self.running = self.current_state is not None
        self.previous_state = None
        self.button_being_pressed = False
        self.button_thread = None

        self.pattern_stop_event = threading.Event()
        self.pattern_thread_lock = threading.Lock()
        self.current_pid = os.getpid()
        self.coordination_check_thread = None
        self.coordination_running = False

        # Action trigger flags
        self.reboot_triggered = False
        self.setup_mode_triggered = False
        self.factory_reset_triggered = False

        # Ensure we're starting with a clean state
        self.cleanup()

        # Initialize GPIO
        GPIO.setmode(GPIO.BCM)

        self.setup_led()
        self.setup_button()
        self.start_coordination_monitoring()

        print("LedControl initialized - ID: " + str(id(self)))

    def setup_led(self):
        """Set up the LED pin separately from button"""
        if self.module_disabled:
            return

        try:
            GPIO.setup(self.LED_PIN, GPIO.OUT)
            print(f"LED pin {self.LED_PIN} configured successfully")

            # Test the LED by blinking once
            GPIO.output(self.LED_PIN, GPIO.HIGH)
            time.sleep(0.2)
            GPIO.output(self.LED_PIN, GPIO.LOW)
        except Exception as e:
            print(f"LED setup failed: {traceback.format_exc()}")
            self.led_disabled = True

    def setup_button(self):
        """Set up the button separately with fallback"""
        if self.module_disabled:
            return

        try:
            GPIO.setup(self.BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

            # Start a separate thread to poll the button state instead of using event detection
            self.running = True

            # Make sure we don't have an existing thread running
            if self.button_thread is not None and self.button_thread.is_alive():
                print("Button thread already running - not starting a new one")
                return

            self.button_thread = threading.Thread(target=self.poll_button_state)
            self.button_thread.daemon = True
            self.button_thread.start()
            print(f"Button pin {self.BUTTON_PIN} configured in polling mode - Thread ID: {self.button_thread.ident}")
        except Exception as e:
            print(f"Button setup failed: {traceback.format_exc()}")
            print("Button functionality will be disabled")
            self.button_disabled = True

    def start_coordination_monitoring(self):
        """Start a thread to monitor for cross-process pattern stop signals"""
        self.coordination_running = True
        self.coordination_check_thread = threading.Thread(target=self.monitor_pattern_coordination)
        self.coordination_check_thread.daemon = True
        self.coordination_check_thread.start()

    def monitor_pattern_coordination(self):
        """Monitor the led_state.json file for signals to stop our pattern thread"""
        while self.coordination_running:
            try:
                current_state = load_state()

                # Check if another process is requesting us to stop our pattern
                stop_request_pid = current_state.get('stop_request_for_pid')
                if stop_request_pid == self.current_pid:
                    requesting_pid = current_state.get('requesting_pid')
                    print(f"Received cross-process signal to stop pattern thread from PID {requesting_pid}")

                    # Stop our pattern thread
                    with self.pattern_thread_lock:
                        if self.pattern_thread and self.pattern_thread.is_alive():
                            self.pattern_stop_event.set()
                            self.pattern_thread.join(timeout=2.0)
                            self.pattern_thread = None
                            print("Pattern thread stopped due to cross-process request")

                    # Clear the stop request
                    self.clear_stop_request()

                time.sleep(0.1)  # Check every 100ms

            except Exception as e:
                print(f"Error in coordination monitoring: {traceback.format_exc()}")
                time.sleep(1)

    def register_pattern_thread(self):
        """Register this process as having an active pattern thread"""
        current_state = load_state()
        current_state['active_pattern_pid'] = self.current_pid
        current_state['pattern_timestamp'] = time.time()
        save_led_state(current_state)

    def signal_stop_to_other_pattern(self, other_pid):
        """Signal another process to stop its pattern thread"""
        current_state = load_state()
        current_state['stop_request_for_pid'] = other_pid
        current_state['requesting_pid'] = self.current_pid
        current_state['stop_request_timestamp'] = time.time()
        save_led_state(current_state)

    def clear_stop_request(self):
        """Clear any stop request from the led state"""
        current_state = load_state()
        current_state.pop('stop_request_for_pid', None)
        current_state.pop('requesting_pid', None)
        current_state.pop('stop_request_timestamp', None)
        save_led_state(current_state)

    def stop_any_existing_pattern_threads(self):
        """Stop pattern threads in other processes before starting our own"""
        current_state = load_state()
        active_pattern_pid = current_state.get('active_pattern_pid')

        if active_pattern_pid and active_pattern_pid != self.current_pid:
            print(f"Signaling PID {active_pattern_pid} to stop its pattern thread")
            self.signal_stop_to_other_pattern(active_pattern_pid)

            # Wait a bit for the other process to stop its thread
            time.sleep(0.3)

    def poll_button_state(self):
        """Poll the button state instead of using event detection"""
        thread_id = threading.get_ident()
        print(f"Starting button polling thread - Thread ID: {thread_id}")

        self.button_being_pressed = False
        press_start_time = 0
        two_second_mark_reached = False
        ten_second_mark_reached = False
        thirty_second_mark_reached = False

        while self.running and not self.button_disabled:
            try:
                if GPIO.getmode() != GPIO.BCM:
                    GPIO.setmode(GPIO.BCM)

                current_function = GPIO.gpio_function(self.BUTTON_PIN)
                if current_function != GPIO.IN:
                    GPIO.setup(self.BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
                    print(f"Button pin {self.BUTTON_PIN} reconfigured as input with pull-up")
                    time.sleep(0.1)  # Short delay to allow hardware to stabilize

                current_time = time.time()
                current_state = GPIO.input(self.BUTTON_PIN)

                # Button pressed (LOW when pressed with pull-up resistor)
                if current_state == GPIO.LOW and not self.button_being_pressed:
                    self.button_being_pressed = True
                    self.set_state('off')
                    press_start_time = time.time()
                    two_second_mark_reached = False
                    ten_second_mark_reached = False
                    thirty_second_mark_reached = False
                    self.reboot_triggered = False
                    self.setup_mode_triggered = False
                    self.factory_reset_triggered = False
                    print(f"[Thread {thread_id}] Button pressed")

                # Button still pressed - check for 2 second mark
                elif current_state == GPIO.LOW and self.button_being_pressed and not two_second_mark_reached and current_time - press_start_time > 2:
                    print(f"[Thread {thread_id}] 2 second press detected - preparing for reboot")
                    two_second_mark_reached = True
                    self.signal_reboot_preparation()

                # Check for 10 second press while button is still pressed
                elif current_state == GPIO.LOW and self.button_being_pressed and not ten_second_mark_reached and current_time - press_start_time > 10:
                    print(f"[Thread {thread_id}] Long press detected (10 seconds) - preparing for reset mode")
                    ten_second_mark_reached = True
                    self.signal_reset_mode()

                # Check for 30 second press while button is still pressed
                elif current_state == GPIO.LOW and self.button_being_pressed and not thirty_second_mark_reached and current_time - press_start_time > 30:
                    print(f"[Thread {thread_id}] Extra long press detected (30 seconds) - preparing for factory reset")
                    thirty_second_mark_reached = True
                    self.signal_factory_reset()

                # Button released
                elif current_state == GPIO.HIGH and self.button_being_pressed:
                    self.button_being_pressed = False
                    duration = current_time - press_start_time
                    print(f"[Thread {thread_id}] Button released after {duration:.1f} seconds")

                    if thirty_second_mark_reached and not self.factory_reset_triggered:
                        print(f"[Thread {thread_id}] Factory resetting system...")
                        self.factory_reset_triggered = True
                        self.perform_factory_reset()
                    # If we have passed the 10 second mark but not the 30 second mark, reset to setup mode
                    elif ten_second_mark_reached and duration < 30 and not self.setup_mode_triggered:
                        print(f"[Thread {thread_id}] Resetting to setup mode...")
                        self.setup_mode_triggered = True
                        # clear just the api token so we still have the current config to allow editing
                        # the user will just have to re-enter their email/password
                        clear_api_token()
                        self.config.clear_creds_from_config()
                        restart_in_setup_mode()
                    # If we have passed the 2 second mark but not the 10 second mark, reboot
                    elif two_second_mark_reached and duration < 10 and not self.reboot_triggered:
                        print(f"[Thread {thread_id}] Rebooting system...")
                        self.reboot_triggered = True
                        self.reboot_system()
                    elif not self.reboot_triggered and not self.setup_mode_triggered and not self.factory_reset_triggered and self.previous_state:
                        # if the button was released without triggering anything we should set it back to the previous state
                        self.set_state(self.previous_state)

                    two_second_mark_reached = False
                    ten_second_mark_reached = False
                    thirty_second_mark_reached = False

                # Small sleep to prevent CPU hogging
                time.sleep(0.1)

            except Exception as e:
                print(f"[Thread {thread_id}] Error in button polling: {traceback.format_exc()}")
                time.sleep(1)  # Longer sleep on error

        print(f"[Thread {thread_id}] Button polling thread exiting")

    def set_state(self, state):
        """Set the LED to different states based on mode"""
        if self.module_disabled or self.led_disabled or self.button_being_pressed:
            return
        # Stop any existing pattern thread
        self.stop_pattern_thread()
        if self.pwm:
            self.pwm.stop()
            self.pwm = None

        self.previous_state = self.current_state
        # Set the current state
        self.current_state = state
        self.led_state['current_state'] = state
        save_led_state(self.led_state)

        if state == "setup":
            # Blinking blue in setup mode (1 Hz)
            self.pwm = GPIO.PWM(self.LED_PIN, 1)
            self.pwm.start(50)  # 50% duty cycle - half on, half off
        elif state == "running":
            # Solid on in normal operation
            GPIO.output(self.LED_PIN, GPIO.HIGH)
        elif state == "error":
            # Fast blinking in error state (5 Hz)
            self.pwm = GPIO.PWM(self.LED_PIN, 5)
            self.pwm.start(50)
        elif state == "wifi_issue":
            # Double-blink pattern for WiFi connectivity issues
            self.start_pattern_thread(self.wifi_issue_pattern)
        elif state == 'off':
            GPIO.output(self.LED_PIN, GPIO.LOW)

    def wifi_issue_pattern(self):
        """LED pattern for WiFi connectivity issues: double-blink with pause"""
        if self.module_disabled or self.led_disabled:
            return

        while not self.pattern_stop_event.is_set():
            # Double blink
            if self.pattern_stop_event.is_set():
                break

            GPIO.output(self.LED_PIN, GPIO.HIGH)
            if self.pattern_stop_event.wait(0.2):
                break

            GPIO.output(self.LED_PIN, GPIO.LOW)
            if self.pattern_stop_event.wait(0.2):
                break

            GPIO.output(self.LED_PIN, GPIO.HIGH)
            if self.pattern_stop_event.wait(0.2):
                break

            GPIO.output(self.LED_PIN, GPIO.LOW)

            # Longer pause
            if self.pattern_stop_event.wait(1.0):
                break

        # Ensure LED is off when pattern stops
        try:
            GPIO.output(self.LED_PIN, GPIO.LOW)
        except:
            pass

    def signal_reboot_preparation(self):
        """Visual indication that the system is preparing to reboot (2 blinks)"""
        if self.module_disabled or self.led_disabled:
            return

        # Stop any current patterns
        self.stop_pattern_thread()

        # Blink twice to indicate reboot preparation
        if self.pwm:
            self.pwm.stop()
            self.pwm = None

        for _ in range(2):
            GPIO.output(self.LED_PIN, GPIO.HIGH)
            time.sleep(0.1)
            GPIO.output(self.LED_PIN, GPIO.LOW)
            time.sleep(0.1)

    def signal_reset_mode(self):
        """Visual indication that the system is resetting to setup mode (5 blinks)"""
        if self.module_disabled or self.led_disabled:
            return

        # Stop any current patterns
        self.stop_pattern_thread()

        # Blink 5 times to indicate reset to setup mode
        if self.pwm:
            self.pwm.stop()
            self.pwm = None

        for _ in range(5):
            GPIO.output(self.LED_PIN, GPIO.HIGH)
            time.sleep(0.2)
            GPIO.output(self.LED_PIN, GPIO.LOW)
            time.sleep(0.2)

    def signal_factory_reset(self):
        """Visual indication that the system is preparing for factory reset (10 rapid blinks)"""
        if self.module_disabled or self.led_disabled:
            return

        # Stop any current patterns
        self.stop_pattern_thread()

        # Blink 10 times rapidly to indicate factory reset
        if self.pwm:
            self.pwm.stop()
            self.pwm = None

        for _ in range(10):
            GPIO.output(self.LED_PIN, GPIO.HIGH)
            time.sleep(0.05)
            GPIO.output(self.LED_PIN, GPIO.LOW)
            time.sleep(0.05)

    def signal_successful_transmission(self):
        """Visual indication that a temperature reading was successfully sent (2 fast blinks)"""
        if self.module_disabled or self.led_disabled or self.button_being_pressed:
            return

        # Stop any current patterns
        self.stop_pattern_thread()

        # Blink twice very quickly to indicate successful transmission
        if self.pwm:
            self.pwm.stop()
            self.pwm = None

        for _ in range(2):
            GPIO.output(self.LED_PIN, GPIO.HIGH)
            time.sleep(0.05)  # Very short on time (50ms)
            GPIO.output(self.LED_PIN, GPIO.LOW)
            time.sleep(0.05)  # Very short off time (50ms)

    def start_pattern_thread(self, pattern_function):
        """Start a thread to run a custom LED pattern"""
        if self.module_disabled:
            return

        with self.pattern_thread_lock:
            # Stop any existing pattern threads (including cross-process)
            self.stop_any_existing_pattern_threads()
            self.stop_pattern_thread()

            if self.pwm:
                self.pwm.stop()
                self.pwm = None

            # Clear the stop event for the new thread
            self.pattern_stop_event.clear()

            # Register this process as having the active pattern thread
            self.register_pattern_thread()

            # Start new pattern thread
            self.pattern_thread = threading.Thread(target=pattern_function)
            self.pattern_thread.daemon = True
            self.pattern_thread.start()

    def stop_pattern_thread(self):
        """Stop any running pattern thread in this process"""
        with self.pattern_thread_lock:
            if self.pattern_thread and self.pattern_thread.is_alive():
                # Signal the thread to stop
                self.pattern_stop_event.set()

                # Wait for thread to finish with longer timeout
                self.pattern_thread.join(timeout=2.0)

                # Force cleanup if thread is still alive
                if self.pattern_thread.is_alive():
                    print(f"Warning: Pattern thread did not stop gracefully")

                self.pattern_thread = None

    def perform_factory_reset(self):
        """Perform a factory reset of the device using the factory-reset.sh script"""
        try:
            print("Performing factory reset...")

            # Path to the factory reset script
            script_path = "/home/pi/freezerbot/bin/factory-reset.sh"

            # Check if script exists and is executable
            if not os.path.exists(script_path):
                script_dir = os.path.dirname(os.path.abspath(__file__))
                script_path = os.path.join(os.path.dirname(script_dir), 'bin', "factory-reset.sh")

                if not os.path.exists(script_path):
                    print(f"Factory reset script not found at {script_path}")
                    self.set_state("error")
                    return

            # Make sure the script is executable
            subprocess.run(["/usr/bin/sudo", "/usr/bin/chmod", "+x", script_path], check=True)

            # Run the factory reset script with sudo
            result = subprocess.run(["/usr/bin/sudo", script_path], check=True)

            if result.returncode != 0:
                print(f"Factory reset script failed with exit code {result.returncode}")
                self.set_state("error")
                return

            print("Factory reset completed. Rebooting...")
            self.reboot_system()

        except Exception as e:
            print(f"Error during factory reset: {traceback.format_exc()}")
            self.set_state("error")

    def reboot_system(self):
        """Reboot the system"""
        try:
            subprocess.run(["/usr/bin/sudo", "/usr/sbin/reboot"], check=True)
        except Exception as e:
            print(f"Error rebooting system: {traceback.format_exc()}")

    def cleanup(self):
        """Clean up resources"""
        self.coordination_running = False
        self.running = False

        # Stop coordination monitoring
        if self.coordination_check_thread and self.coordination_check_thread.is_alive():
            self.coordination_check_thread.join(timeout=0.5)

        # Stop pattern thread
        self.stop_pattern_thread()

        if hasattr(self, 'button_thread') and self.button_thread and self.button_thread.is_alive():
            self.button_thread.join(timeout=0.5)

        if self.pwm:
            try:
                self.pwm.stop()
                self.pwm = None
            except:
                pass

        # Clean up pattern thread registration if we were the active controller
        try:
            current_state = load_state()
            if current_state.get('active_pattern_pid') == self.current_pid:
                current_state.pop('active_pattern_pid', None)
                current_state.pop('pattern_timestamp', None)
                save_led_state(current_state)
        except:
            pass

        try:
            GPIO.cleanup()
        except:
            pass


if __name__ == "__main__":
    if len(sys.argv) > 1:
        try:
            LedControl().set_state(sys.argv[1])
        except KeyboardInterrupt:
            LedControl().cleanup()
        except Exception as e:
            print(f"Error: {str(e)}")
            try:
                GPIO.cleanup()
            except:
                pass