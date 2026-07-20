# GRACE Workbench для VS Code

**Язык:** [Русский](README.md) · [English](README.en.md)

Read-only CASE-оболочка в духе Rose для [GRACE Atlas](../).  
Тот же контракт, что у плагина Obsidian: читает **только** snapshot `.grace-atlas/model` (GRACE XML не разбирает).

## Предварительные условия

1. Соберите workbench snapshot из корня проекта:

```powershell
$env:PYTHONPATH = "src"   # из корня grace-atlas, либо tools/grace_atlas/src из host
python -m grace_atlas snapshot build --project-root .
```

2. Откройте в VS Code **корень проекта** (не vault).

## Собрать и установить (рекомендуется: .vsix)

```powershell
cd vscode-extension
npm install
npm run package
# → grace-workbench-0.4.0.vsix
```

В VS Code / Cursor:

1. `Ctrl+Shift+P` → **Extensions: Install from VSIX…**
2. Выберите `grace-workbench-0.4.0.vsix`
3. Reload при необходимости
4. Откройте workspace **корня проекта**
5. Command Palette → **GRACE: Open Workbench**

Или:

```powershell
code --install-extension path\to\grace-workbench-0.4.0.vsix
```

Готовые сборки: https://github.com/kucheryavenkovn/grace-atlas/releases/tag/v0.4.0

### Только dev (без .vsix)

```powershell
npm run build
# F5 из папки vscode-extension → Extension Development Host
```

## Интерфейс

| Поверхность | Роль |
|-------------|------|
| Activity bar **GRACE** | дерево Model Browser |
| **GRACE: Open Workbench** | webview на 4 панели: Browser · Diagram · Inspector · Problems/Trace/History |
| Status bar | число nodes / статус модели |

## Настройки

| Setting | По умолчанию | Смысл |
|---------|--------------|--------|
| `graceWorkbench.modelPath` | `.grace-atlas/model` | каталог snapshot относительно workspace |
| `graceWorkbench.autoLoad` | `true` | загружать snapshot при активации |

## Архитектура

```
Python GRACE Core → Workbench Snapshot → расширение VS Code (это)
                                      → плагин Obsidian
                                      → CLI
```

Без Neo4j, без сети, без обязательного LLM. Inferred-связи UI не записывает.

## Тесты

```powershell
npm test
npm run typecheck
```
