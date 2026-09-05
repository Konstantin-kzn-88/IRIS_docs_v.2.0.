import sys
import copy
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from iris_v2.service import CreateProjectData, ProjectError, ProjectInfo, ProjectService
from iris_v2.catalog import CatalogError, Organization, load_organizations
from iris_v2.developer_catalog import (
    Developer,
    DeveloperCatalogError,
    load_developers,
)
from iris_v2.project_common import ProjectCommonError, ProjectCommonService


class ProjectCommonDialog(QDialog):
    EXECUTOR_FIELDS = (
        ("name", "Наименование разработчика"),
        ("address", "Адрес"),
        ("sro", "СРО"),
        ("inn", "ИНН"),
        ("ogrn", "ОГРН"),
        ("tel", "Телефон"),
        ("head_position", "Должность руководителя"),
        ("head_full_name", "Ф.И.О. руководителя"),
        ("specialist_info", "Сведения о специалисте"),
        ("email", "Электронная почта"),
        ("website", "Сайт"),
    )

    def __init__(
        self,
        project_directory: Path,
        project: ProjectInfo,
        developers: tuple[Developer, ...],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.project_directory = project_directory
        self.service = ProjectCommonService()
        self.data = self.service.load(
            project_directory, project.name, project.code
        )
        self.setWindowTitle("Данные проекта")
        self.resize(760, 620)

        self.year_edit = QSpinBox()
        self.year_edit.setRange(2000, 2100)
        self.year_edit.setValue(int(self.data["year"]))
        self.project_name_edit = QLineEdit(str(self.data["project_name"]))
        self.project_code_edit = QLineEdit(str(self.data["project_code"]))
        self.dpb_code_edit = QLineEdit(str(self.data["dpb_code"]))
        self.gochs_code_edit = QLineEdit(str(self.data["gochs_code"]))
        self.pb_code_edit = QLineEdit(str(self.data["pb_code"]))

        project_form = QFormLayout()
        project_form.addRow("Год:", self.year_edit)
        project_form.addRow("Название проекта:", self.project_name_edit)
        project_form.addRow("Шифр проекта:", self.project_code_edit)
        project_form.addRow("Шифр ДПБ:", self.dpb_code_edit)
        project_form.addRow("Шифр ГОЧС:", self.gochs_code_edit)
        project_form.addRow("Шифр ПБ:", self.pb_code_edit)
        project_page = QWidget()
        project_page.setLayout(project_form)

        executor = self.data["executor"]
        self.executor_edits: dict[str, QLineEdit | QPlainTextEdit] = {}
        executor_form = QFormLayout()
        self.developer_combo = QComboBox()
        self.developer_combo.addItem("— Ввести вручную —", None)
        for developer in developers:
            self.developer_combo.addItem(developer.name, developer)
        executor_form.addRow("Постоянный разработчик:", self.developer_combo)
        for key, label in self.EXECUTOR_FIELDS:
            if key in {"address", "specialist_info"}:
                edit = QPlainTextEdit(str(executor.get(key, "")))
                edit.setMaximumHeight(100)
            else:
                edit = QLineEdit(str(executor.get(key, "")))
            self.executor_edits[key] = edit
            executor_form.addRow(f"{label}:", edit)
        self.developer_combo.currentIndexChanged.connect(self._fill_executor)
        for index, developer in enumerate(developers, start=1):
            if developer.name == str(executor.get("name", "")).strip():
                self.developer_combo.blockSignals(True)
                self.developer_combo.setCurrentIndex(index)
                self.developer_combo.blockSignals(False)
                break
        executor_page = QWidget()
        executor_page.setLayout(executor_form)

        tabs = QTabWidget()
        tabs.addTab(project_page, "Проект и шифры")
        tabs.addTab(executor_page, "Разработчик")

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Сохранить")
        buttons.button(QDialogButtonBox.StandardButton.Save).clicked.connect(
            self._save
        )
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(tabs)
        layout.addWidget(buttons)

    def _fill_executor(self) -> None:
        developer = self.developer_combo.currentData()
        if developer is None:
            return
        values = developer.snapshot()
        for key, edit in self.executor_edits.items():
            value = str(values.get(key, ""))
            if isinstance(edit, QPlainTextEdit):
                edit.setPlainText(value)
            else:
                edit.setText(value)

    def _save(self) -> None:
        data = copy.deepcopy(self.data)
        data.update(
            {
                "year": self.year_edit.value(),
                "project_name": self.project_name_edit.text().strip(),
                "project_code": self.project_code_edit.text().strip(),
                "dpb_code": self.dpb_code_edit.text().strip(),
                "gochs_code": self.gochs_code_edit.text().strip(),
                "pb_code": self.pb_code_edit.text().strip(),
            }
        )
        executor = dict(data.get("executor", {}))
        for key, edit in self.executor_edits.items():
            value = edit.toPlainText() if isinstance(edit, QPlainTextEdit) else edit.text()
            executor[key] = value.strip()
        data["executor"] = executor
        try:
            self.service.save(self.project_directory, data)
        except ProjectCommonError as exc:
            QMessageBox.critical(self, "Ошибка", str(exc))
            return
        self.accept()


class CreateProjectDialog(QDialog):
    def __init__(
        self,
        organizations: tuple[Organization, ...],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Создание проекта")
        self.setMinimumWidth(600)

        self.path_edit = QLineEdit()
        self.name_edit = QLineEdit()
        self.code_edit = QLineEdit()
        self.organization_combo = QComboBox()
        self.opo_combo = QComboBox()
        self.registration_edit = QLineEdit()
        self.registration_edit.setReadOnly(True)

        for organization in organizations:
            self.organization_combo.addItem(organization.name, organization)
        self.organization_combo.currentIndexChanged.connect(self._update_facilities)
        self.opo_combo.currentIndexChanged.connect(self._update_registration_number)
        self._update_facilities()

        browse_button = QPushButton("Выбрать…")
        browse_button.clicked.connect(self._select_project_path)
        path_layout = QHBoxLayout()
        path_layout.addWidget(self.path_edit)
        path_layout.addWidget(browse_button)

        form = QFormLayout()
        form.addRow("Папка проекта:", path_layout)
        form.addRow("Название проекта:", self.name_edit)
        form.addRow("Шифр проекта:", self.code_edit)
        form.addRow("Организация:", self.organization_combo)
        form.addRow("Наименование ОПО:", self.opo_combo)
        form.addRow("Регистрационный номер ОПО:", self.registration_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Создать")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def _select_project_path(self) -> None:
        parent_directory = QFileDialog.getExistingDirectory(
            self, "Выберите папку для проектов"
        )
        if not parent_directory:
            return
        folder_name = self.code_edit.text().strip() or "Новый проект"
        self.path_edit.setText(str(Path(parent_directory) / folder_name))

    def _update_facilities(self) -> None:
        organization = self.organization_combo.currentData()
        self.opo_combo.clear()
        if organization is not None:
            for facility in organization.facilities:
                self.opo_combo.addItem(facility.name, facility)
        self._update_registration_number()

    def _update_registration_number(self) -> None:
        facility = self.opo_combo.currentData()
        self.registration_edit.setText(
            facility.registration_number if facility is not None else ""
        )

    def project_path(self) -> str:
        return self.path_edit.text().strip()

    def project_data(self) -> CreateProjectData:
        organization = self.organization_combo.currentData()
        facility = self.opo_combo.currentData()
        return CreateProjectData(
            name=self.name_edit.text(),
            code=self.code_edit.text(),
            organization_name=organization.name if organization else "",
            opo_name=facility.name if facility else "",
            opo_registration_number=(
                facility.registration_number if facility else ""
            ),
            organization_snapshot=(
                organization.snapshot() if organization else None
            ),
            opo_snapshot=facility.snapshot() if facility else None,
        )


class MainWindow(QMainWindow):
    def __init__(
        self,
        service: ProjectService | None = None,
        organizations: tuple[Organization, ...] | None = None,
    ) -> None:
        super().__init__()
        self.service = service or ProjectService()
        self.current_project: ProjectInfo | None = None
        self.current_project_directory: Path | None = None
        try:
            self.organizations = organizations or load_organizations()
        except CatalogError as exc:
            self.organizations = ()
            QMessageBox.critical(self, "Ошибка справочника", str(exc))
        try:
            self.developers = load_developers()
        except DeveloperCatalogError as exc:
            self.developers = ()
            QMessageBox.warning(self, "Ошибка справочника разработчиков", str(exc))
        self.setWindowTitle("IRIS v2")
        self.resize(720, 360)

        title = QLabel("IRIS v2")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 24px; font-weight: bold;")

        self.project_label = QLabel("Проект не открыт")
        self.project_label.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.project_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )

        create_button = QPushButton("Создать проект")
        create_button.setObjectName("create_project_button")
        create_button.clicked.connect(self.create_project)

        open_button = QPushButton("Открыть проект")
        open_button.setObjectName("open_project_button")
        open_button.clicked.connect(self.open_project)

        self.project_common_button = QPushButton("Данные проекта")
        self.project_common_button.setObjectName("project_common_button")
        self.project_common_button.setEnabled(False)
        self.project_common_button.clicked.connect(self.edit_project_common)

        button_layout = QHBoxLayout()
        button_layout.addWidget(create_button)
        button_layout.addWidget(open_button)
        button_layout.addWidget(self.project_common_button)

        layout = QVBoxLayout()
        layout.addWidget(title)
        layout.addLayout(button_layout)
        layout.addWidget(self.project_label, 1)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

    def create_project(self) -> None:
        if not self.organizations:
            self._show_error("Справочник организаций пуст или повреждён")
            return
        dialog = CreateProjectDialog(self.organizations, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        if not dialog.project_path():
            self._show_error("Не выбрана папка проекта")
            return
        try:
            project = self.service.create(dialog.project_path(), dialog.project_data())
        except (ProjectError, OSError) as exc:
            self._show_error(str(exc))
            return
        self.show_project(project, Path(dialog.project_path()).resolve())

    def open_project(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Открыть проект IRIS v2")
        if not directory:
            return
        try:
            project = self.service.open(directory)
        except (ProjectError, OSError) as exc:
            self._show_error(str(exc))
            return
        self.show_project(project, Path(directory).resolve())

    def show_project(self, project: ProjectInfo, directory: Path) -> None:
        self.current_project = project
        self.current_project_directory = directory
        self.project_common_button.setEnabled(True)
        self.project_label.setText(
            f"Проект: {project.name}\n"
            f"Шифр: {project.code}\n"
            f"Организация: {project.organization_name}\n"
            f"ОПО: {project.opo_name}\n"
            f"Регистрационный номер: {project.opo_registration_number}"
        )

    def edit_project_common(self) -> None:
        if self.current_project is None or self.current_project_directory is None:
            self._show_error("Сначала создайте или откройте проект")
            return
        try:
            dialog = ProjectCommonDialog(
                self.current_project_directory,
                self.current_project,
                self.developers,
                self,
            )
        except ProjectCommonError as exc:
            self._show_error(str(exc))
            return
        dialog.exec()

    def _show_error(self, message: str) -> None:
        QMessageBox.critical(self, "Ошибка", message)


def main() -> int:
    application = QApplication.instance() or QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
