#!/usr/bin/env bash
# Публикация qwenkit на GitHub.
#
# Использование:
#   OWNER=ваш-логин ./publish.sh
#
# Скрипт НЕ хранит и не просит никаких токенов: аутентификацию делает
# GitHub CLI (gh) или ваш обычный git-credential-helper.

set -euo pipefail

OWNER="${OWNER:-}"
REPO="${REPO:-qwenkit}"
VISIBILITY="${VISIBILITY:-public}"      # public | private
PYPI="${PYPI:-0}"                       # PYPI=1 — также опубликовать в PyPI

if [[ -z "$OWNER" ]]; then
  echo "Укажите владельца репозитория:" >&2
  echo "  OWNER=ваш-логин-github ./publish.sh" >&2
  exit 1
fi

cd "$(dirname "$0")"

echo "==> Проверка перед публикацией"

# 1. тесты
python3 tests/test_qwenkit.py > /tmp/qwenkit-tests.log 2>&1 || {
  echo "ТЕСТЫ УПАЛИ — публикация отменена. Лог: /tmp/qwenkit-tests.log" >&2
  tail -20 /tmp/qwenkit-tests.log >&2
  exit 1
}
grep -E "провалено: 0" /tmp/qwenkit-tests.log > /dev/null || {
  echo "Есть упавшие проверки — публикация отменена." >&2
  tail -20 /tmp/qwenkit-tests.log >&2
  exit 1
}
echo "    тесты: OK"

# 2. не тащим ли мусор и секреты
git add -A
if git diff --cached --name-only | grep -E "(^|/)(__pycache__|build|dist)/|\.egg-info/|\.pyc$"; then
  echo "В индексе мусор — проверьте .gitignore" >&2
  exit 1
fi
echo "    мусор: нет"

if git diff --cached | grep -nE "(sk-[A-Za-z0-9_-]{20,}|ms-[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|BEGIN [A-Z ]*PRIVATE KEY)"; then
  echo "Похоже на секрет в диффе — публикация отменена." >&2
  exit 1
fi
echo "    секреты: не найдены"

# 3. обязательные файлы
for f in README.md LICENSE pyproject.toml .gitignore; do
  [[ -f "$f" ]] || { echo "Нет обязательного файла: $f" >&2; exit 1; }
done
echo "    обязательные файлы: на месте"

# 4. коммит
if [[ -z "$(git log --oneline -1 2>/dev/null || true)" ]]; then
  git commit -q -m "$(cat <<'MSG'
qwenkit 1.0.0 — free API setup, Claude Code migration and a starter pack for Qwen Code

Инструмент решает три задачи вокруг Qwen Code (CLI-агент @qwen-code/qwen-code):

1. Бесплатный API. Qwen OAuth (2000 запросов/день) отключён 2026-04-15, поэтому
   setup подключает сторонние OpenAI-совместимые провайдеры (ModelScope,
   OpenRouter, Groq, Cloudflare, Cerebras) или локальную Ollama и генерирует
   ~/.qwen/settings.json в формате qwen-code 0.26+: modelProviders как голый
   массив ModelConfig, ключи через envKey, а не в файле.

2. Миграция с Claude Code. convert переносит CLAUDE.md -> QWEN.md, команды,
   субагентов, MCP-серверы и хуки; конвертирует синтаксис ($ARGUMENTS ->
   {{args}}, !`cmd` -> !{cmd}, @file -> @{file}) и имена инструментов
   (Read -> read_file, Bash -> run_shell_command, Task -> agent).

   Отдельно обрабатывается мина: BashOutput/KillShell не имеют аналога в Qwen
   Code, и наивная подстановка в disallowedTools полностью заблокировала бы
   агенту терминал. Такие инструменты отбрасываются с явным предупреждением.

3. Стартовый набор. pack ставит 8 команд и 6 субагентов с русскими промптами.

78 проверок в tests/test_qwenkit.py, запускаются без pytest и без сети.
Все таблицы соответствий взяты из первоисточников — см. SOURCES.md.
MSG
)"
  echo "    коммит создан"
else
  git commit -q -m "chore: подготовка к публикации" || echo "    нечего коммитить"
fi

# 5. публикация
if command -v gh > /dev/null 2>&1; then
  echo "==> Публикация через GitHub CLI"
  gh auth status > /dev/null 2>&1 || { echo "Сначала: gh auth login" >&2; exit 1; }
  gh repo create "$OWNER/$REPO" --"$VISIBILITY" --source=. --remote=origin \
      --description "Free API setup, Claude Code migration and a starter pack for Qwen Code CLI" \
      --push 2>/dev/null || {
        git remote get-url origin > /dev/null 2>&1 || \
          git remote add origin "https://github.com/$OWNER/$REPO.git"
        git push -u origin main
      }
else
  echo "==> GitHub CLI не найден — публикуем через обычный git"
  echo "    1. создайте пустой репозиторий: https://github.com/new"
  echo "       имя: $REPO, видимость: $VISIBILITY, БЕЗ README и .gitignore"
  echo "    2. затем:"
  git remote get-url origin > /dev/null 2>&1 || \
    git remote add origin "https://github.com/$OWNER/$REPO.git"
  echo "       git push -u origin main"
fi

# 6. PyPI (по желанию)
if [[ "$PYPI" == "1" ]]; then
  echo "==> Публикация в PyPI"
  # URL в pyproject.toml не должен оставаться с заглушкой <owner>
  if grep -q "<owner>" pyproject.toml; then
    echo "    Замените <owner> в [project.urls] на $OWNER перед публикацией в PyPI" >&2
    exit 1
  fi
  python3 -m pip install --quiet --upgrade build twine || {
    echo "    не удалось поставить build/twine" >&2; exit 1; }
  rm -rf dist build ./*.egg-info
  python3 -m build
  python3 -m twine check dist/*
  echo "    Загрузка: python3 -m twine upload dist/*"
  echo "    (нужен токен PyPI; сознательно не выполняется автоматически)"
fi

echo
echo "==> Готово: https://github.com/$OWNER/$REPO"
echo "    Не забудьте проставить topics в About:"
echo "      qwen qwen-code claude-code ai cli coding-agent migration mcp"
echo "    Описание: Free API setup, Claude Code migration and a starter pack for Qwen Code"
