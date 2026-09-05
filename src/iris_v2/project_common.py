import copy
import json
from datetime import datetime
from pathlib import Path
from typing import Any


FILE_NAME = "project_common.json"


class ProjectCommonError(Exception):
    pass


def new_project_common(project_name: str = "", project_code: str = "") -> dict[str, Any]:
    return {
        "year": datetime.now().year,
        "project_name": project_name,
        "project_code": project_code,
        "dpb_code": "",
        "gochs_code": "",
        "pb_code": "",
        "executor": {
            "name": "",
            "address": "",
            "sro": "",
            "inn": "",
            "ogrn": "",
            "tel": "",
            "head_position": "",
            "head_full_name": "",
            "specialist_info": "",
            "email": "",
            "website": "",
        },
    }


class ProjectCommonService:
    def load(
        self,
        project_directory: Path | str,
        project_name: str = "",
        project_code: str = "",
    ) -> dict[str, Any]:
        path = Path(project_directory) / FILE_NAME
        if not path.is_file():
            return new_project_common(project_name, project_code)

        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ProjectCommonError(f"Не удалось прочитать {path}") from exc
        if not isinstance(raw, dict):
            raise ProjectCommonError("Корневой элемент project_common.json должен быть объектом")

        result = new_project_common(project_name, project_code)
        result.update(raw)
        executor = new_project_common()["executor"]
        raw_executor = raw.get("executor", {})
        if not isinstance(raw_executor, dict):
            raise ProjectCommonError("Поле executor должно быть объектом")
        executor.update(raw_executor)
        result["executor"] = executor
        return result

    def save(
        self, project_directory: Path | str, data: dict[str, Any]
    ) -> Path:
        self._validate(data)
        directory = Path(project_directory)
        if not directory.is_dir():
            raise ProjectCommonError(f"Папка проекта не найдена: {directory}")

        path = directory / FILE_NAME
        temporary_path = directory / f".{FILE_NAME}.tmp"
        try:
            temporary_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            temporary_path.replace(path)
        except OSError as exc:
            raise ProjectCommonError(f"Не удалось сохранить {path}") from exc
        return path

    @staticmethod
    def _validate(data: dict[str, Any]) -> None:
        if not isinstance(data, dict):
            raise ProjectCommonError("Данные проекта должны быть объектом")
        year = data.get("year")
        if not isinstance(year, int) or not 2000 <= year <= 2100:
            raise ProjectCommonError("Год должен быть целым числом от 2000 до 2100")
        for key, label in (
            ("project_name", "Название проекта"),
            ("project_code", "Шифр проекта"),
        ):
            if not str(data.get(key, "")).strip():
                raise ProjectCommonError(f"Не заполнено поле: {label}")
        if not isinstance(data.get("executor"), dict):
            raise ProjectCommonError("Поле executor должно быть объектом")
