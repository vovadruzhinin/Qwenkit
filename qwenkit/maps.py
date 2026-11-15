"""Таблицы соответствий Claude Code -> Qwen Code.

Источники (проверено 2026-10-24, qwen-code 0.26.0):
  - packages/core/src/tools/tool-names.ts      (канонические имена инструментов)
  - docs/users/features/sub-agents.md          (раздел "Claude Code Compatibility Fields")
  - docs/users/features/commands.md            (раздел 4 "Custom Commands")
  - docs/users/features/hooks.md               (события хуков + CLAUDE_PROJECT_DIR)
  - docs/users/features/memory.md              (QWEN.md и импорт через @path)
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Инструменты: Claude Code -> канонические имена Qwen Code
# ---------------------------------------------------------------------------
TOOL_MAP = {
    # файловые
    "Read": "read_file",
    "Write": "write_file",
    "Edit": "edit",
    "MultiEdit": "edit",              # в Qwen нет отдельного MultiEdit
    "NotebookEdit": "notebook_edit",
    "NotebookRead": "read_file",
    # поиск и навигация
    "Grep": "grep_search",
    "Glob": "glob",
    "LS": "list_directory",
    # выполнение
    "Bash": "run_shell_command",
    # сеть
    "WebFetch": "web_fetch",
    "WebSearch": "web_search",
    # планирование и память
    "TodoWrite": "todo_write",
    "ExitPlanMode": "exit_plan_mode",
    "EnterPlanMode": "enter_plan_mode",
    # взаимодействие
    "AskUserQuestion": "ask_user_question",
    "Task": "agent",                  # запуск субагента в Qwen = инструмент agent
    # LSP / прочее
    "LSP": "lsp",
    "Skill": "skill",
}

# Инструменты Qwen, у которых нет аналога в Claude Code (для справки/подсказок)
QWEN_ONLY_TOOLS = [
    "tool_search", "tool_call", "exec", "zoom_image", "image_gen",
    "save_memory", "manage_memory", "search_memory",
    "cron_create", "cron_list", "cron_delete", "loop_wakeup",
    "create_sub_session", "list_agents", "send_message",
    "task_create", "task_update", "task_list", "task_stop",
    "team_create", "team_delete", "team_plan_approval",
    "enter_worktree", "exit_worktree", "workflow",
    "artifact", "record_artifact", "record_source", "report_findings",
    "get_goal", "propose_goal", "update_goal",
    "monitor", "advisor", "structured_output", "read_mcp_resource",
    "request_shutdown",
]

# Инструменты Claude Code, которые НЕЛЬЗЯ маппить один-к-одному.
# Особенно опасно в disallowedTools: «BashOutput -> run_shell_command» молча
# заблокировало бы всю работу в терминале. Поэтому их отбрасываем с пояснением.
TOOL_DROP = {
    "BashOutput": "в Qwen Code вывод фонового процесса читается самим run_shell_command, "
                  "отдельного инструмента нет",
    "KillShell": "в Qwen Code остановкой процесса управляет run_shell_command, "
                 "отдельного инструмента нет",
    "SlashCommand": "аналога нет",
}

# Известные канонические имена Qwen Code (из tool-names.ts). Всё, что входит в
# этот набор, проходит без изменений.
QWEN_TOOLS = {
    "exec", "edit", "write_file", "read_file", "zoom_image", "grep_search",
    "glob", "run_shell_command", "todo_write", "save_memory", "manage_memory",
    "search_memory", "agent", "skill", "exit_plan_mode", "enter_plan_mode",
    "web_fetch", "web_search", "image_gen", "list_directory", "lsp",
    "ask_user_question", "cron_create", "cron_list", "cron_delete",
    "loop_wakeup", "create_sub_session", "list_agents", "task_stop",
    "task_create", "task_update", "task_list", "team_create", "team_delete",
    "team_plan_approval", "request_shutdown", "send_message",
    "structured_output", "monitor", "notebook_edit", "tool_call",
    "tool_search", "read_mcp_resource", "advisor", "enter_worktree",
    "exit_worktree", "workflow", "artifact", "record_artifact",
    "record_source", "report_findings", "get_goal", "update_goal",
}

# ---------------------------------------------------------------------------
# Субагенты: frontmatter
# ---------------------------------------------------------------------------
# Qwen Code нативно принимает эти поля Claude Code 2.1.168 (менять не нужно):
AGENT_NATIVE_FIELDS = {"maxTurns", "color", "mcpServers", "hooks"}

# permissionMode (CC) -> approvalMode (Qwen). Qwen также понимает permissionMode
# напрямую и сам смапит его при разборе, но явная запись approvalMode надёжнее:
# при обоих полях выигрывает approvalMode.
PERMISSION_MODE_MAP = {
    "acceptEdits": "auto-edit",
    "auto": "auto",
    "bypassPermissions": "yolo",
    "default": "default",
    "dontAsk": "auto",
    "plan": "plan",
}

# Селекторы модели в CC -> Qwen. В Qwen: inherit | fast | <modelId> | <authType>:<modelId>
MODEL_MAP = {
    "inherit": "inherit",
    "sonnet": "inherit",
    "opus": "inherit",
    "haiku": "fast",
    "default": "inherit",
}

# Поля CC, которые в Qwen задокументированы, но ещё не реализованы
# (docs: "land in follow-up PRs"). Оставляем в файле + предупреждаем.
AGENT_PENDING_FIELDS = {"effort", "skills", "initialPrompt", "memory", "isolation"}

# Допустимые значения color в Qwen (список _Y из CC совпадает)
AGENT_COLORS = {"red", "blue", "green", "yellow", "purple", "orange", "pink", "cyan"}

# ---------------------------------------------------------------------------
# Команды: frontmatter и тело
# ---------------------------------------------------------------------------
# Qwen Code поддерживает в Markdown-командах только `description`.
COMMAND_UNSUPPORTED_FIELDS = {
    "allowed-tools": "Qwen Code не ограничивает инструменты на уровне команды",
    "argument-hint": "подсказки аргументов не поддерживаются; опишите формат в тексте",
    "model": "модель команды не задаётся; используйте /model или субагента",
    "disable-model-invocation": "поле не поддерживается",
    "user-invocable": "поле не поддерживается",
}

# Поля CC, которые переносим как есть
COMMAND_PASSTHROUGH_FIELDS = {"description"}

# События хуков: у CC и Qwen имена совпадают
HOOK_EVENTS_SHARED = {
    "PreToolUse", "PostToolUse", "UserPromptSubmit", "Notification",
    "SessionStart", "SessionEnd", "Stop", "SubagentStop", "PreCompact",
}
# Есть только в Qwen (переносить нечего, но полезно знать)
HOOK_EVENTS_QWEN_ONLY = {
    "PostToolUseFailure", "PostToolBatch", "UserPromptExpansion",
    "SessionDelete", "MessageDisplay", "StopFailure", "SubagentStart",
    "PostCompact", "PermissionRequest", "PermissionDenied", "TodoCreated",
}

# Переменные окружения в командах хуков. Qwen выставляет ВСЕ ТРИ, поэтому
# CLAUDE_PROJECT_DIR продолжает работать — но роднее QWEN_PROJECT_DIR.
ENV_VAR_MAP = {
    "CLAUDE_PROJECT_DIR": "QWEN_PROJECT_DIR",
    "GEMINI_PROJECT_DIR": "QWEN_PROJECT_DIR",
}

# ---------------------------------------------------------------------------
# Пути и файлы
# ---------------------------------------------------------------------------
CLAUDE_DIR = ".claude"
QWEN_DIR = ".qwen"

MEMORY_FILES = {
    "CLAUDE.md": "QWEN.md",
    "CLAUDE.local.md": "QWEN.local.md",      # -> .qwen/QWEN.local.md
}

# Что Qwen Code читает и так (дублировать не нужно)
ALSO_READ_NATIVELY = ["AGENTS.md"]

# Ключи settings.json, которые переносим автоматически
SETTINGS_AUTO_KEYS = ["mcpServers", "hooks", "env"]
# Ключи, по которым пишем ручные задачи в MIGRATION_TODO.md
SETTINGS_MANUAL_KEYS = {
    "permissions": "allow/deny/ask правила вида `Bash(npm run *)` в Qwen устроены иначе "
                   "(permissions.deny / approvalMode). Перенесите вручную.",
    "apiKeyHelper": "в Qwen ключи берутся из env-переменной, указанной в modelProviders[].envKey, "
                    "либо из блока env в settings.json.",
    "statusLine": "аналога нет; состояние показывается встроенным UI.",
    "outputStyle": "аналога нет; используйте QWEN.md или системный промпт субагента.",
    "includeCoAuthoredBy": "аналога нет.",
    "cleanupPeriodDays": "аналога нет; история сессий управляется через `qwen sessions`.",
    "env": "перенесён автоматически, проверьте имена переменных.",
    "model": "в Qwen это model.name + modelProviders[].id.",
    "awsAuthRefresh": "не применимо.",
}

# Безобидные метаданные, которые встречаются в чужих наборах агентов.
# Qwen Code их игнорирует; конвертер переносит их молча и сообщает один раз
# сводкой, а не по предупреждению на каждое поле в каждом файле.
HARMLESS_METADATA_FIELDS = {
    "version", "author", "authors", "tags", "category", "subcategory",
    "expertise_level", "expertise", "difficulty", "priority", "order",
    "icon", "emoji", "title", "label", "slug", "id", "uuid",
    "created", "created_at", "updated", "updated_at", "date",
    "license", "source", "homepage", "documentation", "docs",
    "dependencies", "requires", "language", "languages", "framework",
    "frameworks", "use_cases", "examples", "notes", "metadata",
}
