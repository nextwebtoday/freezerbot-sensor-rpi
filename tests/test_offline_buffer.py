"""Unit tests for offline_buffer.py"""
import json
import os
import sys
import tempfile
import pytest

# Add raspberry_pi to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'raspberry_pi'))

from offline_buffer import OfflineBuffer


@pytest.fixture
def buffer(tmp_path):
    """Provide a fresh OfflineBuffer backed by a temp directory."""
    db_path = str(tmp_path / 'test_buffer.db')
    return OfflineBuffer(db_path=db_path)


SAMPLE_PAYLOAD = {
    'degrees_c': -80.2,
    'cpu_degrees_c': 45.0,
    'battery_level': 95.0,
}
SAMPLE_TIMESTAMP = '2026-03-04T10:00:00Z'


class TestAddReading:
    def test_add_single_reading(self, buffer):
        buffer.add_reading(SAMPLE_PAYLOAD, SAMPLE_TIMESTAMP)
        assert buffer.count() == 1

    def test_add_multiple_readings(self, buffer):
        for i in range(5):
            buffer.add_reading({'degrees_c': float(i)}, f'2026-03-04T10:0{i}:00Z')
        assert buffer.count() == 5

    def test_payload_is_persisted(self, buffer):
        buffer.add_reading(SAMPLE_PAYLOAD, SAMPLE_TIMESTAMP)
        readings = buffer.get_buffered_readings()
        assert readings[0]['payload'] == SAMPLE_PAYLOAD

    def test_timestamp_is_persisted(self, buffer):
        buffer.add_reading(SAMPLE_PAYLOAD, SAMPLE_TIMESTAMP)
        readings = buffer.get_buffered_readings()
        assert readings[0]['taken_at'] == SAMPLE_TIMESTAMP


class TestGetBufferedReadings:
    def test_empty_buffer_returns_empty_list(self, buffer):
        assert buffer.get_buffered_readings() == []

    def test_returns_readings_in_fifo_order(self, buffer):
        timestamps = [
            '2026-03-04T10:00:00Z',
            '2026-03-04T10:01:00Z',
            '2026-03-04T10:02:00Z',
        ]
        for ts in timestamps:
            buffer.add_reading({'degrees_c': -80.0}, ts)

        readings = buffer.get_buffered_readings()
        assert [r['taken_at'] for r in readings] == timestamps

    def test_returns_id_field(self, buffer):
        buffer.add_reading(SAMPLE_PAYLOAD, SAMPLE_TIMESTAMP)
        readings = buffer.get_buffered_readings()
        assert 'id' in readings[0]
        assert readings[0]['id'] > 0


class TestClearBuffer:
    def test_clear_empties_buffer(self, buffer):
        buffer.add_reading(SAMPLE_PAYLOAD, SAMPLE_TIMESTAMP)
        buffer.clear_buffer()
        assert buffer.count() == 0

    def test_clear_on_empty_buffer_is_safe(self, buffer):
        buffer.clear_buffer()  # Should not raise
        assert buffer.count() == 0

    def test_clear_removes_all_readings(self, buffer):
        for i in range(10):
            buffer.add_reading({'degrees_c': float(i)}, f'2026-03-04T10:{i:02d}:00Z')
        buffer.clear_buffer()
        assert buffer.count() == 0


class TestPruneToLimit:
    def test_prune_removes_oldest_when_over_limit(self, buffer):
        timestamps = [f'2026-03-04T{h:02d}:00:00Z' for h in range(10)]
        for ts in timestamps:
            buffer.add_reading({'degrees_c': -80.0}, ts)

        buffer.prune_to_limit(limit=5)
        assert buffer.count() == 5

    def test_prune_keeps_newest_readings(self, buffer):
        timestamps = [f'2026-03-04T{h:02d}:00:00Z' for h in range(10)]
        for ts in timestamps:
            buffer.add_reading({'degrees_c': -80.0}, ts)

        buffer.prune_to_limit(limit=5)
        remaining = buffer.get_buffered_readings()
        # Should have kept the 5 most recent (hours 5–9)
        kept_timestamps = [r['taken_at'] for r in remaining]
        assert kept_timestamps == timestamps[5:]

    def test_prune_does_nothing_when_under_limit(self, buffer):
        for i in range(3):
            buffer.add_reading({'degrees_c': float(i)}, f'2026-03-04T10:0{i}:00Z')
        buffer.prune_to_limit(limit=10)
        assert buffer.count() == 3

    def test_prune_default_limit_is_1440(self, buffer):
        # Add exactly 1440 readings — should not prune any
        for i in range(1440):
            buffer.add_reading({'degrees_c': -80.0}, f'2026-03-04T00:{i // 60:02d}:{i % 60:02d}Z')
        buffer.prune_to_limit()
        assert buffer.count() == 1440

    def test_prune_1441_drops_one(self, buffer):
        for i in range(1441):
            buffer.add_reading({'degrees_c': -80.0}, f'2026-03-04T00:{i // 60:02d}:{i % 60:02d}Z')
        buffer.prune_to_limit()
        assert buffer.count() == 1440


class TestPersistence:
    def test_readings_survive_across_instances(self, tmp_path):
        db_path = str(tmp_path / 'persist_test.db')
        buf1 = OfflineBuffer(db_path=db_path)
        buf1.add_reading(SAMPLE_PAYLOAD, SAMPLE_TIMESTAMP)

        buf2 = OfflineBuffer(db_path=db_path)
        readings = buf2.get_buffered_readings()
        assert len(readings) == 1
        assert readings[0]['payload'] == SAMPLE_PAYLOAD
