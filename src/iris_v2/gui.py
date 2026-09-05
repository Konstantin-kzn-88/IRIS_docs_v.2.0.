import sys
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
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from iris_v2.service import CreateProjectData, ProjectError, ProjectInfo, ProjectService
from iris_v2.catalog import CatalogError, Organization, load_organizations


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
        try:
            self.organizations = organizations or load_organizations()
        except CatalogError as exc:
            self.organizations = ()
            QMessageBox.critical(self, "Ошибка справочника", str(exc))
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

        button_layout = QHBoxLayout()
        button_layout.addWidget(create_button)
        button_layout.addWidget(open_button)

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
        self.show_project(project)

    def open_project(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Открыть проект IRIS v2")
        if not directory:
            return
        try:
            project = self.service.open(directory)
        except (ProjectError, OSError) as exc:
            self._show_error(str(exc))
            return
        self.show_project(project)

    def show_project(self, project: ProjectInfo) -> None:
        self.project_label.setText(
            f"Проект: {project.name}\n"
            f"Шифр: {project.code}\n"
            f"Организация: {project.organization_name}\n"
            f"ОПО: {project.opo_name}\n"
            f"Регистрационный номер: {project.opo_registration_number}"
        )

    def _show_error(self, message: str) -> None:
        QMessageBox.critical(self, "Ошибка", message)


def main() -> int:
    application = QApplication.instance() or QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
