from __future__ import annotations

from app.scanner.dump_detector import detect_sudden_dump
from app.scanner.surge_detector import detect_sudden_pump
from app.scanner.volume_detector import detect_volume_spike


def test_surge_dump_and_volume_detectors() -> None:
    indicators = {"relative_volume": 2.5}
    assert detect_sudden_pump({"change_1h": 5}, indicators)["detected"]
    assert detect_sudden_dump({"change_1h": -6}, indicators)["detected"]
    assert detect_volume_spike(indicators)["detected"]
