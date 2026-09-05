import json
from pathlib import Path

import pytest

from iris_v2.calculation_config import (
    CalculationConfigError,
    CalculationConfigService,
    new_calculation_config,
)


def test_defaults_are_returned_without_file(tmp_path: Path) -> None:
    config = CalculationConfigService().load(tmp_path)

    assert config["partial_release_fraction"] == 0.125
    assert config["frequency_multipliers"] == {
        "standard": 1.0,
        "without_compensation": 1.25,
        "with_compensation": 0.6,
    }


def test_config_is_saved_and_loaded(tmp_path: Path) -> None:
    config = new_calculation_config()
    config["wind_speed_m_s"] = 2.5
    config["frequency_multipliers"]["with_compensation"] = 0.55

    path = CalculationConfigService().save(tmp_path, config)
    loaded = CalculationConfigService().load(tmp_path)

    assert path == tmp_path / "calculation_config.json"
    assert loaded == config
    assert json.loads(path.read_text(encoding="utf-8")) == config


def test_invalid_config_is_not_saved(tmp_path: Path) -> None:
    config = new_calculation_config()
    config["partial_spill_fraction"] = 1.5

    with pytest.raises(CalculationConfigError, match="не больше 1"):
        CalculationConfigService().save(tmp_path, config)

    assert not (tmp_path / "calculation_config.json").exists()
