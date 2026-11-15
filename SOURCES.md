# Источники фактов

Все таблицы соответствий и схемы конфигов в `qwenkit/maps.py`, `qwenkit/providers.py`
и `qwenkit/setup_cmd.py` взяты из первоисточников, а не из статей в интернете.

**Версия-эталон:** `@qwen-code/qwen-code` **0.26.0** (npm `latest`)
**Дата проверки:** 2026-10-24
**Репозиторий:** https://github.com/QwenLM/qwen-code (Apache License 2.0)
**Ветка:** `main`

## Документация qwen-code, на которую опирается конвертер

| Файл в репозитории QwenLM/qwen-code | Что оттуда взято |
| --- | --- |
| [`docs/users/features/sub-agents.md`](https://github.com/QwenLM/qwen-code/blob/main/docs/users/features/sub-agents.md) | формат агентов `.qwen/agents/*.md`; раздел «Claude Code Compatibility Fields» — какие поля CC принимаются нативно (`maxTurns`, `color`, `mcpServers`, `hooks`); какие задокументированы, но не реализованы (`effort`, `skills`, `initialPrompt`, `memory`, `isolation`); семантика `tools` / `disallowedTools`; селекторы `model` (`inherit` / `fast` / `id` / `authType:id`); режимы `approvalMode` |
| [`docs/users/features/commands.md`](https://github.com/QwenLM/qwen-code/blob/main/docs/users/features/commands.md) | пользовательские команды: Markdown + YAML frontmatter, TOML deprecated; маппинг пути в имя команды (`commands/git/commit.md` → `/git:commit`); синтаксис `{{args}}`, `!{shell}`, `@{file}`; приоритет project > user |
| [`docs/users/features/hooks.md`](https://github.com/QwenLM/qwen-code/blob/main/docs/users/features/hooks.md) | имена событий хуков; четыре типа (`command`, `http`, `function`, `prompt`); `$QWEN_PROJECT_DIR` / `$CLAUDE_PROJECT_DIR` / `$GEMINI_PROJECT_DIR` выставляются одновременно; таймауты command-хуков в секундах, но ≥ 1000 читаются как миллисекунды |
| [`docs/users/features/memory.md`](https://github.com/QwenLM/qwen-code/blob/main/docs/users/features/memory.md) | `~/.qwen/QWEN.md`, `QWEN.md` в корне, `.qwen/QWEN.local.md`; импорт через `@path`; `AGENTS.md` читается нативно; `.gitignore` не создаётся автоматически |
| [`docs/users/configuration/auth.md`](https://github.com/QwenLM/qwen-code/blob/main/docs/users/configuration/auth.md) | **Qwen OAuth отключён 2026-04-15** (раздел «Option 2: Qwen OAuth (Discontinued)»); четыре варианта в `/auth`; однофайловая настройка через `settings.json`; протоколы `openai` / `anthropic` / `gemini` / `vertex-ai` |
| [`docs/users/configuration/model-providers.md`](https://github.com/QwenLM/qwen-code/blob/main/docs/users/configuration/model-providers.md) | `modelProviders` — **голый массив** `ModelConfig[]`; обёртка `{protocol, models}` отменена и молча игнорируется; поля `id` / `envKey` / `baseUrl` / `wireApi` / `generationConfig`; `providerProtocol` для своих id; ключи никогда не хранятся в настройках |
| [`docs/users/configuration/settings.md`](https://github.com/QwenLM/qwen-code/blob/main/docs/users/configuration/settings.md) | `fastModel`, `security.auth.selectedType`, `model.name`, `env`, `mcpServers`, `hooks` |
| [`docs/users/features/mcp.md`](https://github.com/QwenLM/qwen-code/blob/main/docs/users/features/mcp.md) | `mcpServers` в `settings.json`, stdio/http-серверы, команда `qwen mcp add` |
| [`packages/core/src/tools/tool-names.ts`](https://github.com/QwenLM/qwen-code/blob/main/packages/core/src/tools/tool-names.ts) | **канонические имена инструментов** — единственный надёжный источник для маппинга `Read` → `read_file`, `Bash` → `run_shell_command` и т. д. |

## Как обновить таблицы под новую версию qwen-code

```bash
# канонические имена инструментов
curl -s https://raw.githubusercontent.com/QwenLM/qwen-code/main/packages/core/src/tools/tool-names.ts \
  | grep -oE "': *'[a-z_]+'"

# список полей совместимости с Claude Code
curl -s https://raw.githubusercontent.com/QwenLM/qwen-code/main/docs/users/features/sub-agents.md \
  | sed -n '/Claude Code Compatibility Fields/,/Example Usage/p'
```

После обновления прогоните тесты: `python3 tests/test_qwenkit.py`.

## Лимиты бесплатных тарифов

Проверялись 2026-10-24 живыми запросами к каталогам моделей и по открытым страницам
провайдеров. Цифры меняются — всегда сверяйтесь:

| Провайдер | Страница с условиями |
| --- | --- |
| ModelScope API-Inference | https://www.modelscope.ai/docs/model-service/API-Inference/limits |
| OpenRouter | https://openrouter.ai/docs/api-reference/limits |
| Groq | https://console.groq.com/docs/rate-limits |
| Cloudflare Workers AI | https://developers.cloudflare.com/workers-ai/platform/pricing/ |
| Cerebras | https://cerebras.ai/pricing |
| Alibaba DashScope | https://www.alibabacloud.com/en/product/modelstudio |

Сводная таблица бесплатных тарифов, использованная при составлении каталога:
https://novita.ai/compare/best-free-llm-api

Живой каталог моделей без ключа:

```bash
# OpenRouter: бесплатные модели с поддержкой tool-calling
qwenkit providers

# ModelScope: полный список (ключ не нужен для чтения каталога)
curl -s https://api-inference.modelscope.cn/v1/models
```

## Отношение к qwen-code

qwenkit — независимый сторонний инструмент. Он не является частью Qwen Code,
не модифицирует его и распространяется отдельно под лицензией MIT.
Qwen Code и Qwen — торговые марки Alibaba Group; упоминаются здесь
в информационных целях.
