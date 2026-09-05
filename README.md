# IRIS v2 — минимальное ядро

Поддерживается Python 3.10.

## Установка

```powershell
python -m pip install -e ".[dev]"
```

## Создание проекта

```powershell
iris-v2 create "D:\IRIS_projects\Test" `
  --name "Тестовый проект" `
  --code "TEST-001" `
  --organization "АО Пример" `
  --opo "Тестовый ОПО" `
  --registration-number "А00-00000-0000"
```

## Открытие проекта

```powershell
iris-v2 open "D:\IRIS_projects\Test"
```

Папка проекта содержит `project.sqlite3`, `project.json`, `input` и `output`.

## Окно программы

```powershell
python main.py
```

Также окно можно запустить командой `iris-v2-gui`.

## Организации и ОПО

Создайте в корне проекта локальную копию справочника:

```powershell
Copy-Item .\src\iris_v2\data\organization.json .\organization.json
```

Заполняйте `organization.json` реальными данными. Используется исходная
вложенная структура: сведения об организации находятся в `organization`,
а список её ОПО — в `sites`. После изменения файла перезапустите программу.

Локальный справочник исключён из Git. Если его нет, программа использует
обезличенный пример `src/iris_v2/data/organization.json`.

При создании проекта в его базу копируются все разделы организации и все поля
выбранного ОПО без распрямления. Список остальных ОПО в снимок не попадает.

Значение `sanitary_protection_zone_m: 0` означает, что санитарно-защитная
зона у ОПО отсутствует. `employees_other_opo_count` — суммарная численность
людей на соседних ОПО в возможной зоне воздействия.
