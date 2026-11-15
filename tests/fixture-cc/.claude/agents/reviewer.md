---
name: reviewer
description: Ревьюер кода
model: haiku
permissionMode: acceptEdits
color: cyan
maxTurns: 25
tools: Read, Grep, Glob, Bash
mcpServers:
  github:
    type: http
    url: https://api.example.com/mcp
hooks:
  PreToolUse:
    - matcher: Bash
      hooks:
        - type: command
          command: "$CLAUDE_PROJECT_DIR/.claude/hooks/guard.sh"
          timeout: 10000
effort: high
skills:
  - code-review
---

Ты ревьюер. Используй Bash для git diff и Read для чтения файлов.
См. @docs/code-standards.md
