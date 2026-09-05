import copy
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


FILE_NAME = "substances.json"
REQUIRED_FIELDS = {
    "id",
    "name",
    "kind",
    "formula",
    "composition",
    "notes",
    "physical",
    "explosion",
    "toxicity",
    "reactivity",
    "odor",
    "corrosiveness",
    "precautions",
    "impact",
    "protection",
    "neutralization_methods",
    "first_aid",
}
KIND_NAMES = {
    0: "Легковоспламеняющаяся жидкость (ЛВЖ)",
    1: "Токсичная ЛВЖ",
    2: "Горючий газ",
    3: "Горючий газ (токсичный)",
    4: "Сжиженный горючий газ",
    5: "Сжиженный горючий газ (токсичный)",
    6: "Токсичная жидкость (практически не испаряемая)",
    7: "Токсичный газ",
    8: "Сжиженный токсичный газ",
    9: "Горючая жидкость (практически неиспаряемая)",
}


class SubstanceError(Exception):
    pass


def substance_fingerprint(data: dict[str, Any]) -> str:
    value = copy.deepcopy(data)
    value.pop("id", None)
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


@dataclass(frozen=True)
class Substance:
    data: dict[str, Any]
    source_path: Path

    @property
    def source_id(self) -> int:
        return int(self.data["id"])

    @property
    def name(self) -> str:
        return str(self.data["name"]).strip()

    @property
    def kind(self) -> int:
        return int(self.data["kind"])

    @property
    def group(self) -> str:
        return self.source_path.parent.name

    @property
    def fingerprint(self) -> str:
        return substance_fingerprint(self.data)

    def snapshot(self, project_id: int) -> dict[str, Any]:
        result = copy.deepcopy(self.data)
        result["id"] = project_id
        return result


def _read_substance(path: Path) -> Substance:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SubstanceError(f"Не удалось прочитать {path}") from exc
    if not isinstance(raw, dict):
        raise SubstanceError(f"Корневой элемент {path} должен быть объектом")
    missing = REQUIRED_FIELDS - raw.keys()
    if missing:
        raise SubstanceError(f"В файле {path} отсутствуют поля: {', '.join(sorted(missing))}")
    if not isinstance(raw["id"], int):
        raise SubstanceError(f"В файле {path} поле id должно быть целым числом")
    if not str(raw["name"]).strip():
        raise SubstanceError(f"В файле {path} не заполнено поле name")
    if not isinstance(raw["kind"], int) or raw["kind"] not in KIND_NAMES:
        raise SubstanceError(f"В файле {path} поле kind должно быть от 0 до 9")
    return Substance(copy.deepcopy(raw), path)


class SubstanceService:
    def load_archive(self, path: Path | str | None = None) -> tuple[Substance, ...]:
        archive = Path(path) if path is not None else Path.cwd() / "substances" / "archive"
        paths = (
            sorted(
                item
                for item in archive.rglob("*.json")
                if item.name != FILE_NAME
            )
            if archive.is_dir()
            else []
        )
        if not paths:
            paths = [Path(__file__).parent / "data" / "substance.json"]
        return tuple(_read_substance(item) for item in paths)

    def load_project(self, project_directory: Path | str) -> tuple[dict[str, Any], ...]:
        path = Path(project_directory) / FILE_NAME
        if not path.is_file():
            return ()
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SubstanceError(f"Не удалось прочитать {path}") from exc
        if not isinstance(raw, list) or not all(isinstance(item, dict) for item in raw):
            raise SubstanceError("Корневой элемент substances.json должен быть массивом")
        return tuple(copy.deepcopy(item) for item in raw)

    def save_project(
        self,
        project_directory: Path | str,
        selected: Iterable[Substance],
    ) -> Path:
        substances = tuple(selected)
        if not substances:
            raise SubstanceError("Не выбрано ни одного вещества")
        fingerprints = [item.fingerprint for item in substances]
        if len(fingerprints) != len(set(fingerprints)):
            raise SubstanceError("Нельзя выбрать одно и то же вещество дважды")

        directory = Path(project_directory)
        if not directory.is_dir():
            raise SubstanceError(f"Папка проекта не найдена: {directory}")
        data = [item.snapshot(index) for index, item in enumerate(substances, start=1)]
        path = directory / FILE_NAME
        temporary_path = directory / f".{FILE_NAME}.tmp"
        try:
            temporary_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            temporary_path.replace(path)
        except OSError as exc:
            raise SubstanceError(f"Не удалось сохранить {path}") from exc
        return path
