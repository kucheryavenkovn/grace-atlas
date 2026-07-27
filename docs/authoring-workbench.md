# GRACE Atlas Authoring Workbench

## Назначение

Authoring Workbench — опциональный контур поверх read-only ядра GRACE Atlas. Он нужен для работы с моделью вне кодового агента:

- построение минимального контекста по сущностям Atlas;
- перевод карточек и требований через OpenAI-compatible API;
- формирование трассируемых черновиков use case;
- генерация GracePatch;
- безопасный `plan → validate → apply` для `requirements.xml` и `knowledge-graph.xml`;
- локальный JSON API как контракт будущего графического интерфейса.

Snapshot и Obsidian Vault остаются производными представлениями. Источник истины — исходные GRACE XML и разметка кода.

## Архитектура

```text
Interface
  grace-atlas-author CLI
  loopback JSON API
        ↓
Application
  AuthoringService
  ContextBuilder
  TranslationUseCase
  RequirementUseCase
  AuthoringPatchPipeline
        ↓
Domain
  AuthoringDraft
  EvidenceRef
  TranslationInput
  RequirementInput
        ↓
Infrastructure
  OpenAI-compatible LLM adapter
  AuthoringWorkspace
  XML overlay / backup / audit
```

Удалённый HTTP apply намеренно отсутствует. Применение patch возможно только локальной CLI-командой с `--confirm`.

## Настройки

Добавьте в `grace-atlas.toml`:

```toml
[authoring]
workspace = ".grace-atlas/authoring"
allow_source_replace = false
require_validation = true
require_confirmation = true
context_depth = 2
context_max_nodes = 40

[authoring.llm]
provider = "openai-compatible"
base_url = "http://127.0.0.1:1234/v1"
model = "qwen3.5-35b"
api_key_env = "GRACE_ATLAS_API_KEY"
timeout_seconds = 120
temperature = 0.1
max_tokens = 4096

[authoring.translation]
source_language = "auto"
target_language = "en"
fields = ["name", "description"]
preserve_terms = ["GRACE", "GracePatch", "M-ID", "UC", "DDD"]
```

API-ключ хранится только в переменной окружения, имя которой задаётся в `api_key_env`.

Поддерживаются LM Studio, vLLM, Ollama OpenAI compatibility и другие серверы с `/v1/chat/completions`.

## CLI

```powershell
# Показать effective settings
grace-atlas-author settings --project-root .

# Создать безопасный пример настроек
grace-atlas-author settings --project-root . --init

# Получить минимальный контекст
grace-atlas-author context UC-001 M-APP-AUTO --project-root .

# Перевод в sidecar. Исходный XML не изменяется
grace-atlas-author translate UC-001 --target-language en --project-root .

# Перевод с подготовкой update_property patch
# Требует authoring.allow_source_replace=true
grace-atlas-author translate UC-001 --target-language en --replace-source --project-root .

# Сформировать требование на основе существующих сущностей
grace-atlas-author requirement --from M-APP-AUTO VF-001 --project-root .

# Без LLM — все обязательные поля задаёт человек
grace-atlas-author requirement \
  --from M-APP-AUTO \
  --id UC-AUTH-001 \
  --actor "Аналитик" \
  --action "Открывает карточку требования" \
  --goal "Проверить трассировку до кода и тестов" \
  --acceptance "Карточка показывает связанные M-ID и V-M-ID" \
  --no-llm \
  --project-root .
```

Результаты сохраняются в:

```text
.grace-atlas/authoring/
  drafts/
  patches/
  translations/<language>/
  backups/
  audit.jsonl
  apply-audit.jsonl
```

## Применение изменений

```powershell
grace-atlas-author patch plan <patch.json> --project-root .
grace-atlas-author patch validate <patch.json> --project-root .
grace-atlas-author patch apply <patch.json> --project-root . --confirm
```

Проверяются:

- ожидаемые старые значения;
- хеши исходных файлов;
- XML well-formedness;
- построение AtlasGraph на временных overlay-файлах;
- отсутствие прироста error diagnostics;
- появление созданных сущностей;
- резервная копия перед atomic replace.

## Локальный API

```powershell
grace-atlas-author serve --project-root . --port 8765
```

Доступны:

- `GET /health`
- `GET /settings`
- `GET /context?id=UC-001,M-APP-AUTO`
- `POST /translate`
- `POST /requirements`

Сервер разрешает только loopback binding. Apply endpoint отсутствует, поэтому будущий GUI сначала создаёт draft/patch, а подтверждение выполняется локальной CLI-командой.

## Переводы

По умолчанию перевод хранится как sidecar и не меняет исходный язык GRACE XML. Это позволяет:

- иметь несколько языков одновременно;
- видеть модель и идентификатор LLM;
- повторно переводить после изменения оригинала;
- не превращать перевод в конкурирующий источник истины.

`--replace-source` используется только осознанно и формирует проверяемый `update_property` patch.

## Следующий этап — GUI

GUI должен работать только через `AuthoringService`/локальный API и показывать:

1. Atlas graph и карточку сущности;
2. исходный текст и переводы;
3. редактор requirement draft;
4. evidence и обратную трассировку;
5. diff patch;
6. результаты validate;
7. отдельное локальное подтверждение apply.
