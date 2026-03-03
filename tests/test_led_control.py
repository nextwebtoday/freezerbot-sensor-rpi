"""Unit tests for led_control.py (FRE-119)"""
import sys
import os
import threading
import pytest
from unittest.mock import patch, MagicMock


def _import_led_control():
    """Fresh-import led_control module, resetting singleton state."""
    for mod_name in list(sys.modules.keys()):
        if 'led_control' in mod_name:
            del sys.modules[mod_name]
    sys.modules.pop('api', None)
    sys.modules.pop('restarts', None)
    sys.modules.pop('config', None)

    sys.modules['api'] = MagicMock()
    sys.modules['restarts'] = MagicMock()
    sys.modules['config'] = MagicMock()

    import led_control
    led_control.LedControl._instance = None
    led_control.LedControl._initialized = False
    return led_control


@pytest.fixture(autouse=True)
def reset_singleton():
    # Save modules that _import_led_control replaces so we can restore them
    saved_modules = {k: sys.modules.get(k) for k in ('restarts', 'api', 'config')}
    yield
    for mod_name in list(sys.modules.keys()):
        if 'led_control' in mod_name:
            try:
                lc_mod = sys.modules[mod_name]
                if hasattr(lc_mod, 'LedControl'):
                    lc_mod.LedControl._instance = None
                    lc_mod.LedControl._initialized = False
            except Exception:
                pass
    # Restore modules that were replaced with MagicMocks
    for mod_name, mod in saved_modules.items():
        if mod is not None:
            sys.modules[mod_name] = mod
        elif mod_name in sys.modules:
            del sys.modules[mod_name]


def _make_lc():
    """Create a fresh LedControl instance with mocked setup methods."""
    led_control = _import_led_control()
    gpio = led_control.GPIO
    gpio.reset_mock()
    gpio.BCM = 11
    gpio.OUT = 0
    gpio.IN = 1
    gpio.HIGH = 1
    gpio.LOW = 0
    gpio.PUD_UP = 22
    gpio.getmode.return_value = gpio.BCM
    gpio.gpio_function.return_value = gpio.IN
    gpio.input.return_value = gpio.HIGH
    gpio.PWM.return_value = MagicMock()

    with patch.dict(os.environ, {}, clear=True), \
         patch.object(led_control.LedControl, 'setup_button'), \
         patch.object(led_control.LedControl, 'setup_led'):
        lc = led_control.LedControl()
        lc.module_disabled = False
        lc.led_disabled = False
        lc.button_disabled = False
        lc.button_being_pressed = False
        lc.pwm = None
        lc.pattern_thread = None
        lc.running = True
        lc.current_state = None
        lc.previous_state = None
        lc.reboot_triggered = False
        lc.setup_mode_triggered = False
        lc.factory_reset_triggered = False
    return led_control, lc, gpio


class TestSingletonPattern:

    def test_same_instance_returned(self):
        led_control, lc1, gpio = _make_lc()
        # Second call should return same instance (already initialized)
        lc2 = led_control.LedControl()
        assert lc1 is lc2

    def test_initialized_only_once(self):
        led_control = _import_led_control()
        gpio = led_control.GPIO
        gpio.reset_mock()
        with patch.dict(os.environ, {}, clear=True), \
             patch.object(led_control.LedControl, 'setup_button'), \
             patch.object(led_control.LedControl, 'setup_led') as mock_setup_led:
            led_control.LedControl()
            led_control.LedControl()
            assert mock_setup_led.call_count == 1

    def test_reset_allows_new_instance(self):
        led_control, lc1, _ = _make_lc()
        led_control.LedControl._instance = None
        led_control.LedControl._initialized = False
        with patch.object(led_control.LedControl, 'setup_button'), \
             patch.object(led_control.LedControl, 'setup_led'):
            lc2 = led_control.LedControl()
            assert lc1 is not lc2


class TestThreadSafety:

    def test_concurrent_creation_returns_same_instance(self):
        led_control, _, _ = _make_lc()
        instances = []
        errors = []

        def create_instance():
            try:
                instances.append(led_control.LedControl())
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=create_instance) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(instances) == 10
        assert all(inst is instances[0] for inst in instances)


class TestDisabledMode:

    def test_module_disabled_when_env_set(self):
        led_control = _import_led_control()
        with patch.dict(os.environ, {'LED_DISABLED': 'true'}), \
             patch.object(led_control.LedControl, 'setup_button'):
            lc = led_control.LedControl()
            assert lc.module_disabled is True

    def test_module_enabled_when_env_not_set(self):
        led_control = _import_led_control()
        with patch.dict(os.environ, {}, clear=True), \
             patch.object(led_control.LedControl, 'setup_button'):
            lc = led_control.LedControl()
            assert lc.module_disabled is False

    def test_setup_led_skips_when_disabled(self):
        led_control = _import_led_control()
        gpio = led_control.GPIO
        gpio.reset_mock()
        with patch.dict(os.environ, {'LED_DISABLED': 'true'}), \
             patch.object(led_control.LedControl, 'setup_button'):
            lc = led_control.LedControl()
            # setup_led runs but returns early — no GPIO.setup for LED pin
            setup_calls = [c for c in gpio.setup.call_args_list
                           if len(c[0]) > 0 and c[0][0] == led_control.LED_PIN]
            assert len(setup_calls) == 0

    def test_set_state_noop_when_disabled(self):
        _, lc, gpio = _make_lc()
        lc.module_disabled = True
        gpio.output.reset_mock()
        lc.set_state('running')
        gpio.output.assert_not_called()


class TestSetState:

    def test_running_sets_high(self):
        led_control, lc, gpio = _make_lc()
        lc.set_state('running')
        gpio.output.assert_called_with(led_control.LED_PIN, gpio.HIGH)
        assert lc.current_state == 'running'

    def test_off_sets_low(self):
        led_control, lc, gpio = _make_lc()
        lc.set_state('off')
        gpio.output.assert_called_with(led_control.LED_PIN, gpio.LOW)
        assert lc.current_state == 'off'

    def test_setup_starts_pwm_1hz(self):
        led_control, lc, gpio = _make_lc()
        lc.set_state('setup')
        gpio.PWM.assert_called_with(led_control.LED_PIN, 1)
        gpio.PWM.return_value.start.assert_called_with(50)
        assert lc.current_state == 'setup'

    def test_error_starts_pwm_5hz(self):
        led_control, lc, gpio = _make_lc()
        lc.set_state('error')
        gpio.PWM.assert_called_with(led_control.LED_PIN, 5)
        gpio.PWM.return_value.start.assert_called_with(50)
        assert lc.current_state == 'error'

    def test_wifi_issue_starts_pattern_thread(self):
        _, lc, _ = _make_lc()
        with patch.object(lc, 'start_pattern_thread') as mock_start:
            lc.set_state('wifi_issue')
            mock_start.assert_called_once()
            assert lc.current_state == 'wifi_issue'

    def test_previous_state_tracked(self):
        _, lc, _ = _make_lc()
        lc.set_state('running')
        lc.set_state('error')
        assert lc.previous_state == 'running'
        assert lc.current_state == 'error'

    def test_stops_existing_pwm_before_new_state(self):
        _, lc, _ = _make_lc()
        old_pwm = MagicMock()
        lc.pwm = old_pwm
        lc.set_state('running')
        old_pwm.stop.assert_called_once()

    def test_noop_when_button_being_pressed(self):
        _, lc, gpio = _make_lc()
        lc.button_being_pressed = True
        gpio.output.reset_mock()
        lc.set_state('running')
        gpio.output.assert_not_called()


class TestButtonPressDetection:

    def test_2s_press_triggers_reboot(self):
        led_control, lc, gpio = _make_lc()
        call_count = [0]

        def fake_input(pin):
            call_count[0] += 1
            if call_count[0] <= 3:
                return gpio.LOW  # pressed
            return gpio.HIGH  # released

        gpio.input.side_effect = fake_input
        times = iter([1000.0, 1000.0, 1003.0, 1003.0, 1003.5])

        with patch('led_control.time') as mock_time, \
             patch.object(lc, 'reboot_system') as mock_reboot, \
             patch.object(lc, 'signal_reboot_preparation'):
            mock_time.time.side_effect = lambda: next(times, 1003.5)
            iteration = [0]
            def stop_eventually(x):
                iteration[0] += 1
                if iteration[0] > 5:
                    lc.running = False
            mock_time.sleep.side_effect = stop_eventually
            lc.poll_button_state()
            mock_reboot.assert_called_once()

    def test_10s_press_triggers_setup_mode(self):
        led_control, lc, gpio = _make_lc()
        call_count = [0]

        def fake_input(pin):
            call_count[0] += 1
            if call_count[0] <= 4:
                return gpio.LOW
            return gpio.HIGH

        gpio.input.side_effect = fake_input
        times = iter([1000.0, 1000.0, 1003.0, 1011.0, 1015.0, 1015.0])

        with patch('led_control.time') as mock_time, \
             patch.object(lc, 'signal_reboot_preparation'), \
             patch.object(lc, 'signal_reset_mode'):
            mock_time.time.side_effect = lambda: next(times, 1015.0)
            iteration = [0]
            def stop_eventually(x):
                iteration[0] += 1
                if iteration[0] > 6:
                    lc.running = False
            mock_time.sleep.side_effect = stop_eventually

            api_mod = sys.modules['api']
            restarts_mod = sys.modules['restarts']
            lc.poll_button_state()
            api_mod.clear_api_token.assert_called_once()
            restarts_mod.restart_in_setup_mode.assert_called_once()

    def test_30s_press_triggers_factory_reset(self):
        led_control, lc, gpio = _make_lc()
        call_count = [0]

        def fake_input(pin):
            call_count[0] += 1
            if call_count[0] <= 5:
                return gpio.LOW
            return gpio.HIGH

        gpio.input.side_effect = fake_input
        times = iter([1000.0, 1000.0, 1003.0, 1011.0, 1031.0, 1035.0, 1035.0])

        with patch('led_control.time') as mock_time, \
             patch.object(lc, 'signal_reboot_preparation'), \
             patch.object(lc, 'signal_reset_mode'), \
             patch.object(lc, 'signal_factory_reset'), \
             patch.object(lc, 'perform_factory_reset') as mock_factory:
            mock_time.time.side_effect = lambda: next(times, 1035.0)
            iteration = [0]
            def stop_eventually(x):
                iteration[0] += 1
                if iteration[0] > 7:
                    lc.running = False
            mock_time.sleep.side_effect = stop_eventually
            lc.poll_button_state()
            mock_factory.assert_called_once()

    def test_short_press_restores_previous_state(self):
        _, lc, gpio = _make_lc()
        lc.previous_state = 'running'
        call_count = [0]

        def fake_input(pin):
            call_count[0] += 1
            if call_count[0] <= 2:
                return gpio.LOW
            return gpio.HIGH

        gpio.input.side_effect = fake_input
        times = iter([1000.0, 1000.0, 1000.5, 1000.5])

        with patch('led_control.time') as mock_time, \
             patch.object(lc, 'set_state') as mock_set_state:
            mock_time.time.side_effect = lambda: next(times, 1000.5)
            iteration = [0]
            def stop_eventually(x):
                iteration[0] += 1
                if iteration[0] > 4:
                    lc.running = False
            mock_time.sleep.side_effect = stop_eventually
            lc.poll_button_state()
            # Should restore to 'running' on release
            calls = [c for c in mock_set_state.call_args_list if c[0][0] == 'running']
            assert len(calls) > 0


class TestSignalMethods:

    def test_signal_reboot_blinks_twice(self):
        led_control, lc, gpio = _make_lc()
        with patch('led_control.time'):
            gpio.output.reset_mock()
            lc.signal_reboot_preparation()
            assert gpio.output.call_count == 4

    def test_signal_reset_mode_blinks_five_times(self):
        _, lc, gpio = _make_lc()
        with patch('led_control.time'):
            gpio.output.reset_mock()
            lc.signal_reset_mode()
            assert gpio.output.call_count == 10

    def test_signal_factory_reset_blinks_ten_times(self):
        _, lc, gpio = _make_lc()
        with patch('led_control.time'):
            gpio.output.reset_mock()
            lc.signal_factory_reset()
            assert gpio.output.call_count == 20

    def test_signal_skipped_when_disabled(self):
        _, lc, gpio = _make_lc()
        lc.module_disabled = True
        gpio.output.reset_mock()
        lc.signal_reboot_preparation()
        lc.signal_reset_mode()
        lc.signal_factory_reset()
        gpio.output.assert_not_called()

    def test_signal_skipped_when_led_disabled(self):
        _, lc, gpio = _make_lc()
        lc.led_disabled = True
        gpio.output.reset_mock()
        lc.signal_reboot_preparation()
        gpio.output.assert_not_called()


class TestCleanup:

    def test_cleanup_stops_pwm(self):
        _, lc, _ = _make_lc()
        pwm_mock = MagicMock()
        lc.pwm = pwm_mock
        lc.cleanup()
        pwm_mock.stop.assert_called_once()

    def test_cleanup_calls_gpio_cleanup(self):
        led_control, lc, gpio = _make_lc()
        lc.pwm = None
        gpio.cleanup.reset_mock()
        lc.cleanup()
        gpio.cleanup.assert_called_once()


class TestSuccessfulTransmission:

    def test_blinks_twice(self):
        _, lc, gpio = _make_lc()
        with patch('led_control.time'):
            gpio.output.reset_mock()
            lc.signal_successful_transmission()
            assert gpio.output.call_count == 4

    def test_noop_when_button_pressed(self):
        _, lc, gpio = _make_lc()
        lc.button_being_pressed = True
        gpio.output.reset_mock()
        lc.signal_successful_transmission()
        gpio.output.assert_not_called()
