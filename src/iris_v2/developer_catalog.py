import copy
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class DeveloperCatalogError(Exception):
    pass


@dataclass(frozen=True)
class Developer:
    data: dict[str, Any]

    @property
    def name(self) -> str:
        return str(self.data.get("name", "")).strip()

    def snapshot(self) -> dict[str, Any]:
        return copy.deepcopy(self.data)


def _read_developer(path: Path) -> Developer:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DeveloperCatalogError(f"Не удалось прочитать {path}") from exc
    if not isinstance(raw, dict):
        raise DeveloperCatalogError(f"Корневой элемент {path} должен быть объектом")
    developer = Developer(copy.deepcopy(raw))
    if not developer.name:
        raise DeveloperCatalogError(f"В файле {path} не заполнено поле name")
    return developer


def load_developers(path: Path | str | None = None) -> tuple[Developer, ...]:
    if path is not None:
        source = Path(path)
        paths = sorted(source.glob("*/developer.json")) if source.is_dir() else [source]
    else:
        paths = sorted((Path.cwd() / "developers").glob("*/developer.json"))
        if not paths:
            paths = [Path(__file__).parent / "data" / "developer.json"]
    return tuple(_read_developer(developer_path) for developer_path in paths)
