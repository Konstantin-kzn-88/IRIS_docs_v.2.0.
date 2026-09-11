from pathlib import Path

import pytest

from iris_v2.workflow_status import (
    DONE,
    NOT_REQUIRED,
    PENDING,
    REFRESH_STEP_ORDER,
    WorkflowRefreshError,
    refresh_workflow,
)


def test_refresh_runs_pending_steps_in_order(tmp_path: Path) -> None:
    calls: list[str] = []
    states = {
        "amount_button": PENDING,
        "calculation_cases_button": DONE,
        "frequency_button": PENDING,
    }
    runners = {
        name: (lambda current=name: calls.append(current))
        for name in states
        if states[name] == PENDING
    }

    result = refresh_workflow(
        tmp_path,
        runners,
        status_provider=lambda _path: {
            name: states.get(name, DONE)
            for name, _label in REFRESH_STEP_ORDER
        },
    )

    assert calls == ["amount_button", "frequency_button"]
    assert result.completed == ("amount_button", "frequency_button")


def test_refresh_skips_not_required_steps(tmp_path: Path) -> None:
    calls: list[str] = []

    result = refresh_workflow(
        tmp_path,
        {"pool_fire_button": lambda: calls.append("pool")},
        status_provider=lambda _path: {
            name: NOT_REQUIRED if name == "pool_fire_button" else DONE
            for name, _label in REFRESH_STEP_ORDER
        },
    )

    assert calls == []
    assert "pool_fire_button" in result.skipped


def test_refresh_stops_on_first_error(tmp_path: Path) -> None:
    calls: list[str] = []

    def fail() -> None:
        calls.append("amount")
        raise ValueError("неверные исходные данные")

    with pytest.raises(WorkflowRefreshError, match="Количество ОВ.*неверные"):
        refresh_workflow(
            tmp_path,
            {
                "amount_button": fail,
                "calculation_cases_button": lambda: calls.append("cases"),
            },
            status_provider=lambda _path: {
                name: (
                    PENDING
                    if name in {"amount_button", "calculation_cases_button"}
                    else DONE
                )
                for name, _label in REFRESH_STEP_ORDER
            },
        )

    assert calls == ["amount"]
