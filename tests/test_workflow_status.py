import json
import os
from pathlib import Path

from iris_v2.workflow_status import DONE, NOT_REQUIRED, PENDING, workflow_statuses


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def prepare_hazard_results(project: Path, codes: tuple[int, ...]) -> None:
    for file_name in (
        "project_common.json",
        "substances.json",
        "equipments.json",
        "calculation_config.json",
        "amount_results.json",
        "calculation_cases.json",
        "frequency_results.json",
        "release_results.json",
        "spill_results.json",
        "evaporation_results.json",
    ):
        write_json(project / file_name, {})
    write_json(
        project / "hazard_factor_results.json",
        {"results": [{"calc_code": code} for code in codes]},
    )


def test_empty_project_requires_all_steps(tmp_path: Path) -> None:
    statuses = workflow_statuses(tmp_path)

    assert statuses["substances_button"] == PENDING
    assert statuses["pool_fire_button"] == PENDING
    assert statuses["report_generation_button"] == PENDING


def test_effect_steps_follow_project_calculation_codes(tmp_path: Path) -> None:
    prepare_hazard_results(tmp_path, (1, 2))
    (tmp_path / "pool_fire_results.json").write_text("{}", encoding="utf-8")

    statuses = workflow_statuses(tmp_path)

    assert statuses["pool_fire_button"] == DONE
    assert statuses["explosion_button"] == PENDING
    assert statuses["toxic_button"] == NOT_REQUIRED
    assert statuses["chemical_spill_button"] == NOT_REQUIRED


def test_changed_input_marks_result_for_update(tmp_path: Path) -> None:
    equipment = tmp_path / "equipments.json"
    substances = tmp_path / "substances.json"
    result = tmp_path / "amount_results.json"
    for path in (equipment, substances, result):
        path.write_text("{}", encoding="utf-8")
    os.utime(result, ns=(1_000_000_000, 1_000_000_000))
    os.utime(equipment, ns=(2_000_000_000, 2_000_000_000))
    os.utime(substances, ns=(2_000_000_000, 2_000_000_000))

    assert workflow_statuses(tmp_path)["amount_button"] == PENDING


def test_stale_hazard_data_does_not_mark_effects_unnecessary(
    tmp_path: Path,
) -> None:
    prepare_hazard_results(tmp_path, (1,))
    os.utime(
        tmp_path / "evaporation_results.json",
        ns=(3_000_000_000, 3_000_000_000),
    )
    os.utime(
        tmp_path / "hazard_factor_results.json",
        ns=(2_000_000_000, 2_000_000_000),
    )

    statuses = workflow_statuses(tmp_path)
    assert statuses["pool_fire_button"] == PENDING
    assert statuses["toxic_button"] == PENDING
