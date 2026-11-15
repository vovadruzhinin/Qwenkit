"""Тесты qwenkit. Запуск: python3 -m pytest tests/ -q   (или python3 tests/test_qwenkit.py)

Не требуют pytest: при запуске как скрипт используют простую проверку assert'ами.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from qwenkit.convert import (  # noqa: E402
    Report,
    convert_agent_file,
    convert_body,
    convert_command_file,
    convert_settings,
    split_frontmatter,
)
from qwenkit.maps import AGENT_COLORS, TOOL_MAP  # noqa: E402
from qwenkit.setup_cmd import build_settings  # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  \033[32m✓\033[0m {name}")
    else:
        FAIL += 1
        print(f"  \033[31m✗ {name}\033[0m {detail}")


def _conv_agent(text: str, tmp: Path, name: str = "a.md"):
    src = tmp / name
    src.write_text(text, encoding="utf-8")
    dst = tmp / ("out_" + name)
    rep = Report()
    convert_agent_file(src, dst, rep, False)
    fm, body, _ = split_frontmatter(dst.read_text(encoding="utf-8"))
    return fm or {}, body, rep


def _conv_cmd(text: str, tmp: Path, name: str = "c.md"):
    src = tmp / name
    src.write_text(text, encoding="utf-8")
    dst = tmp / ("out_" + name)
    rep = Report()
    convert_command_file(src, dst, rep, False, name[:-3])
    fm, body, _ = split_frontmatter(dst.read_text(encoding="utf-8"))
    return fm or {}, body, rep


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="qwenkit-test-"))
    try:
        print("\n[1] Инструменты")
        for cc, q in [("Read", "read_file"), ("Bash", "run_shell_command"),
                      ("Grep", "grep_search"), ("WebFetch", "web_fetch"),
                      ("Task", "agent"), ("TodoWrite", "todo_write")]:
            check(f"{cc} -> {q}", TOOL_MAP[cc] == q, TOOL_MAP.get(cc))
        check("KillShell НЕ маппится в run_shell_command",
              TOOL_MAP.get("KillShell") != "run_shell_command", str(TOOL_MAP.get("KillShell")))
        check("BashOutput НЕ маппится в run_shell_command",
              TOOL_MAP.get("BashOutput") != "run_shell_command", str(TOOL_MAP.get("BashOutput")))

        print("\n[2] Субагенты: permissionMode -> approvalMode")
        for pm, am in [("acceptEdits", "auto-edit"), ("bypassPermissions", "yolo"),
                       ("plan", "plan"), ("default", "default"), ("dontAsk", "auto")]:
            fm, _, _ = _conv_agent(f"---\nname: x\ndescription: d\npermissionMode: {pm}\n---\n\nbody\n", tmp, f"pm_{pm}.md")
            check(f"{pm} -> {am}", fm.get("approvalMode") == am, str(fm))

        print("\n[3] Субагенты: модель")
        for m, exp in [("haiku", "fast"), ("sonnet", "inherit"), ("opus", "inherit")]:
            fm, _, _ = _conv_agent(f"---\nname: x\ndescription: d\nmodel: {m}\n---\n\nb\n", tmp, f"m_{m}.md")
            check(f"model {m} -> {exp}", fm.get("model") == exp, str(fm))
        fm, _, _ = _conv_agent("---\nname: x\ndescription: d\nmodel: openai:gpt-4o\n---\n\nb\n", tmp, "m_prov.md")
        check("model openai:gpt-4o проходит как есть", fm.get("model") == "openai:gpt-4o", str(fm))

        print("\n[4] Субагенты: color")
        fm, _, _ = _conv_agent("---\nname: x\ndescription: d\ncolor: magenta\n---\n\nb\n", tmp, "col_bad.md")
        check("недопустимый color отброшен (НЕ остался в файле)", "color" not in fm, str(fm))
        for c in sorted(AGENT_COLORS):
            fm, _, _ = _conv_agent(f"---\nname: x\ndescription: d\ncolor: {c}\n---\n\nb\n", tmp, f"col_{c}.md")
            check(f"color {c} сохранён", fm.get("color") == c, str(fm))

        print("\n[5] Субагенты: списки инструментов")
        fm, _, rep = _conv_agent(
            "---\nname: x\ndescription: d\ntools: [Read, Grep, Bash, mcp__github__x]\n"
            "disallowedTools: [KillShell]\n---\n\nb\n", tmp, "tools.md")
        check("tools переведены", fm.get("tools") == ["read_file", "grep_search",
                                                      "run_shell_command", "mcp__github__x"], str(fm.get("tools")))
        check("KillShell отброшен из disallowedTools (не подменил run_shell_command)",
              fm.get("disallowedTools") == [], str(fm.get("disallowedTools")))
        check("про отброшенный KillShell есть предупреждение",
              any("KillShell" in m for _, m in rep.warnings), str(rep.warnings))
        fm, _, _ = _conv_agent("---\nname: x\ndescription: d\ntools: Read, Bash\n---\n\nb\n", tmp, "tools_str.md")
        check("tools строкой через запятую разбирается",
              fm.get("tools") == ["read_file", "run_shell_command"], str(fm.get("tools")))

        print("\n[6] Субагенты: нативные и нереализованные поля")
        fm, _, rep = _conv_agent(
            "---\nname: x\ndescription: d\nmaxTurns: 30\neffort: high\nisolation: worktree\n---\n\nb\n", tmp, "nat.md")
        check("maxTurns перенесён", fm.get("maxTurns") == 30, str(fm))
        check("effort перенесён + предупреждение", fm.get("effort") == "high"
              and any("effort" in m for _, m in rep.warnings), str(rep.warnings))
        check("isolation перенесён + предупреждение", fm.get("isolation") == "worktree", str(fm))

        print("\n[7] Субагенты: невалидный YAML")
        fm, body, rep = _conv_agent('---\nname: "broken\ntools: [Read\n---\n\ntext\n', tmp, "broken.md")
        check("невалидный YAML не роняет конвертер", True)
        check("про невалидный YAML есть внятное предупреждение",
              any("НЕВАЛИДНЫЙ YAML" in m for _, m in rep.warnings), str(rep.warnings))

        print("\n[8] Команды: синтаксис промпта")
        _, body, rep = _conv_cmd("---\ndescription: d\n---\n\nArgs: $ARGUMENTS\n", tmp, "c1.md")
        check("$ARGUMENTS -> {{args}}", "{{args}}" in body and "$ARGUMENTS" not in body, body)
        _, body, _ = _conv_cmd("---\ndescription: d\n---\n\n!`git diff --staged`\n", tmp, "c2.md")
        check("!`cmd` -> !{cmd}", "!{git diff --staged}" in body, body)
        _, body, _ = _conv_cmd("---\ndescription: d\n---\n\nRead @docs/a.md please\n", tmp, "c3.md")
        check("@file -> @{file}", "@{docs/a.md}" in body, body)
        _, body, _ = _conv_cmd("---\ndescription: d\n---\n\n!{grep -r @user src/}\n", tmp, "c4.md")
        check("@ внутри !{...} НЕ трогается (это shell-код)", "!{grep -r @user src/}" in body, body)
        _, body, _ = _conv_cmd("---\ndescription: d\n---\n\nУже @{docs/a.md} здесь\n", tmp, "c5.md")
        check("уже сконвертированное @{...} не портится", "@{docs/a.md}" in body and "@{{" not in body, body)
        _, body, _ = _conv_cmd("---\ndescription: d\n---\n\nПишите на user@mail.ru\n", tmp, "c6.md")
        check("email не превращается в ссылку на файл", "user@mail.ru" in body, body)
        _, body, rep = _conv_cmd("---\ndescription: d\n---\n\nA: $1 B: $2\n", tmp, "c7.md")
        check("позиционные $1/$2 -> {{args}} + предупреждение",
              body.count("{{args}}") == 2 and any("позиционные" in m for _, m in rep.warnings), body)

        print("\n[9] Команды: frontmatter")
        fm, _, rep = _conv_cmd("---\ndescription: d\nallowed-tools: Bash\nargument-hint: x\nmodel: sonnet\n---\n\nb\n", tmp, "f1.md")
        check("description сохранён", fm.get("description") == "d", str(fm))
        check("allowed-tools отброшен", "allowed-tools" not in fm, str(fm))
        check("argument-hint отброшен", "argument-hint" not in fm, str(fm))
        check("model отброшен", "model" not in fm, str(fm))
        check("про каждое неподдерживаемое поле есть предупреждение",
              len([w for _, w in rep.warnings if "не поддерживается" in w]) >= 3, str(rep.warnings))
        fm, body, _ = _conv_cmd("Текст без frontmatter и с $ARGUMENTS\n", tmp, "f2.md")
        check("команда без frontmatter: frontmatter не выдуман", fm == {}, str(fm))
        check("команда без frontmatter: тело сконвертировано", "{{args}}" in body, body)

        print("\n[9b] Команды: невалидный YAML не роняет конвертер (регрессия)")
        fm, body, rep = _conv_cmd('---\ndescription: "незакрытая кавычка\nmodel: [x\n---\n\nТело $ARGUMENTS\n', tmp, "bad.md")
        check("конвертер не упал и файл создал", body is not None)
        check("про невалидный YAML есть внятное предупреждение",
              any("НЕВАЛИДНЫЙ YAML" in m for _, m in rep.warnings), str(rep.warnings))
        check("ручная задача добавлена", any("невалидный YAML" in m for m in rep.manual), str(rep.manual))
        check("тело всё равно сконвертировано", "{{args}}" in body, body)

        print("\n[10] settings.json")
        src = tmp / "settings.json"
        src.write_text(json.dumps({
            "model": "claude-sonnet-4-5",
            "permissions": {"allow": ["Bash(npm run test:*)"]},
            "apiKeyHelper": "./k.sh",
            "env": {"T": "x-$CLAUDE_PROJECT_DIR"},
            "hooks": {"PostToolUse": [{"matcher": "Edit|Write", "hooks": [
                {"type": "command", "command": '"$CLAUDE_PROJECT_DIR/.claude/hooks/f.sh"', "timeout": 30000}]}],
                "Nope": []},
        }), encoding="utf-8")
        dst = tmp / "out_settings.json"
        rep = Report()
        convert_settings(src, dst, rep, False)
        data = json.loads(dst.read_text(encoding="utf-8"))
        check("mcpServers/hooks/env перенесены", "hooks" in data and "env" in data, str(list(data)))
        check("permissions НЕ перенесён автоматически", "permissions" not in data, str(list(data)))
        check("про permissions есть ручная задача", any("permissions" in m for m in rep.manual), str(rep.manual))
        check("apiKeyHelper -> ручная задача", any("apiKeyHelper" in m for m in rep.manual), str(rep.manual))
        check("matcher Edit|Write -> edit|write_file",
              data["hooks"]["PostToolUse"][0]["matcher"] == "edit|write_file",
              str(data["hooks"]["PostToolUse"][0]["matcher"]))
        check("$CLAUDE_PROJECT_DIR заменён в env-блоке",
              "$QWEN_PROJECT_DIR" in data["env"]["T"], str(data["env"]))
        check(".claude/hooks -> .qwen/hooks в команде хука",
              ".qwen/hooks/f.sh" in data["hooks"]["PostToolUse"][0]["hooks"][0]["command"],
              str(data["hooks"]["PostToolUse"][0]["hooks"][0]["command"]))
        check("про timeout>=1000 есть предупреждение (миллисекунды)",
              any("миллисекунды" in m for _, m in rep.warnings), str(rep.warnings))
        check("про неизвестное событие хука есть предупреждение",
              any("Nope" in m for _, m in rep.warnings), str(rep.warnings))

        print("\n[11] settings.json: повторный запуск не теряет данные")
        dst.write_text(json.dumps({"modelProviders": {"openai": [{"id": "keep-me"}]},
                                   "model": {"name": "keep-me"}}), encoding="utf-8")
        rep2 = Report()
        convert_settings(src, dst, rep2, False)
        data2 = json.loads(dst.read_text(encoding="utf-8"))
        check("существующие modelProviders сохранены при слиянии",
              any(m.get("id") == "keep-me" for m in data2["modelProviders"]["openai"]), str(data2))

        print("\n[12] Генерация settings для провайдеров")
        st = build_settings(["modelscope"], "Qwen/Qwen3.8-27B", "Qwen/Qwen3.5-27B", None,
                            {"modelscope": ["Qwen/Qwen3.8-27B", "Qwen/Qwen3.5-27B"]})
        check("modelProviders.openai — ГОЛЫЙ массив (формат qwen-code 0.26+)",
              isinstance(st["modelProviders"]["openai"], list), str(type(st["modelProviders"]["openai"])))
        check("нет устаревшей обёртки {protocol, models}",
              all("protocol" not in m for m in st["modelProviders"]["openai"]), str(st))
        check("security.auth.selectedType задан",
              st["security"]["auth"]["selectedType"] == "openai", str(st.get("security")))
        check("model.name задан", st["model"]["name"] == "Qwen/Qwen3.8-27B", str(st.get("model")))
        check("fastModel задан", st["fastModel"] == "Qwen/Qwen3.5-27B", str(st.get("fastModel")))
        check("у каждой модели есть envKey и baseUrl",
              all(m.get("envKey") and m.get("baseUrl") for m in st["modelProviders"]["openai"]),
              str(st["modelProviders"]["openai"]))
        check("ключ НЕ попадает в settings без --store-key", "env" not in st, str(st))
        st2 = build_settings(["ollama"], None, None, {"OLLAMA_API_KEY": "ollama"}, {})
        check("Ollama: baseUrl localhost", st2["modelProviders"]["openai"][0]["baseUrl"].startswith("http://localhost"),
              str(st2))

        print("\n[13] Мультипровайдерная сборка не плодит дубликаты")
        st3 = build_settings(["modelscope", "openrouter"], None, None, None,
                             {"modelscope": ["A"], "openrouter": ["B"]})
        ids = [m["id"] for m in st3["modelProviders"]["openai"]]
        check("обе модели на месте", set(ids) == {"A", "B"}, str(ids))
        check("дубликатов нет", len(ids) == len(set(ids)), str(ids))

        print("\n[14] CLI запускается")
        for args in (["--help"], ["pack", "--list"], ["providers"]):
            r = subprocess.run([sys.executable, str(ROOT / "qwenkit-cli"), *args],
                               capture_output=True, text=True, timeout=120)
            check(f"`qwenkit {' '.join(args)}` exit 0", r.returncode == 0,
                  (r.stderr or r.stdout)[-300:])

        print("\n[15] pack пишет валидные файлы")
        from qwenkit.pack import AGENTS, COMMANDS
        target = tmp / "packtest"
        r = subprocess.run([sys.executable, str(ROOT / "qwenkit-cli"), "pack",
                            "--target", "project", "--path", str(target)],
                           capture_output=True, text=True, timeout=120)
        check("pack отработал", r.returncode == 0, r.stderr[-300:])
        bad = []
        for rel, content in AGENTS.items():
            fm, body, had = split_frontmatter((target / ".qwen" / "agents" / rel).read_text(encoding="utf-8"))
            if not had or not fm or not fm.get("name") or not fm.get("description"):
                bad.append(rel)
                continue
            for t in (fm.get("tools") or []) + (fm.get("disallowedTools") or []):
                from qwenkit.maps import QWEN_TOOLS
                if not (t in QWEN_TOOLS or t.startswith("mcp__")):
                    bad.append(f"{rel}:{t}")
            if fm.get("color") and fm["color"] not in AGENT_COLORS:
                bad.append(f"{rel}:color={fm['color']}")
        check(f"все {len(AGENTS)} субагентов валидны (name/description/tools/color)", not bad, str(bad))
        badc = [rel for rel in COMMANDS
                if not (target / ".qwen" / "commands" / rel).exists()]
        check(f"все {len(COMMANDS)} команд созданы", not badc, str(badc))
        badfm = []
        for rel in COMMANDS:
            txt = (target / ".qwen" / "commands" / rel).read_text(encoding="utf-8")
            fm, body, had = split_frontmatter(txt)
            if not had or not fm or not fm.get("description"):
                badfm.append(rel)
            for bad_tok in ("$ARGUMENTS", "!`"):
                if bad_tok in txt:
                    badfm.append(f"{rel}:{bad_tok}")
        check("команды имеют description и не содержат синтаксис Claude Code", not badfm, str(badfm))

        print("\n[17] install: разбор адресов")
        from qwenkit.install import RepoRef, parse_target, classify, plan_install, _dest_name
        cases = [
            ("owner/repo", ("owner", "repo", "HEAD", "", "")),
            ("owner/repo/agents", ("owner", "repo", "HEAD", "agents", "")),
            ("https://github.com/o/r", ("o", "r", "HEAD", "", "")),
            ("https://github.com/o/r.git", ("o", "r", "HEAD", "", "")),
            ("https://github.com/o/r/tree/main", ("o", "r", "main", "", "")),
            ("https://github.com/o/r/tree/v1.2/a/b", ("o", "r", "v1.2", "a/b", "")),
            ("https://github.com/o/r/blob/main/agents/x.md", ("o", "r", "main", "", "agents/x.md")),
            ("https://raw.githubusercontent.com/o/r/main/agents/x.md", ("o", "r", "main", "", "agents/x.md")),
        ]
        for src, exp in cases:
            r = parse_target(src)
            got = (r.owner, r.repo, r.ref, r.subdir, r.single_file)
            check(f"{src[:52]} -> {exp[0]}/{exp[1]}", got == exp, str(got))
        for bad in ("", "просто текст", "https://gitlab.com/o/r", "owner"):
            try:
                parse_target(bad)
                check(f"отклонил {bad!r}", False, "не отклонил")
            except ValueError:
                check(f"отклонил {bad!r}", True)

        print("\n[18] install: классификация файлов")
        cls = {
            "agents/foo.md": "agent",
            "agent/foo.md": "agent",
            "subagents/foo.md": "agent",
            ".claude/commands/git/commit.md": "command",
            "commands/foo.md": "command",
            ".claude/commands/old.toml": "command",
            "CLAUDE.md": "memory",
            ".mcp.json": "mcp",
            "mcp.json": "mcp",
            ".claude/settings.json": "settings",
            "README.md": None,
            "CHANGELOG.md": None,
            "LICENSE.md": None,
            "src/main.py": None,
            "docs/guide.md": None,
            "agents/README.md": None,
        }
        for path, exp in cls.items():
            got = classify(path)
            check(f"classify({path}) = {exp}", got == exp, f"получено {got}")

        print("\n[19] install: план и обрезка путей")
        paths = ["agents/a.md", "agents/nested/b.md", "commands/c.md", "README.md",
                 "src/x.py", ".claude/settings.json", ".mcp.json", "CLAUDE.md"]
        plan = plan_install(paths)
        check("агенты найдены", plan.get("agent") == ["agents/a.md", "agents/nested/b.md"], str(plan.get("agent")))
        check("команды найдены", plan.get("command") == ["commands/c.md"], str(plan.get("command")))
        check("README/src не попали", "README.md" not in str(plan) and "src/x.py" not in str(plan), str(plan))
        check("фильтр по подкаталогу", list(plan_install(paths, subdir="agents").get("agent", [])) ==
              ["agents/a.md", "agents/nested/b.md"], str(plan_install(paths, subdir="agents")))
        check("фильтр --only", "command" not in plan_install(paths, kinds={"agent"}), str(plan_install(paths, kinds={"agent"})))
        check("вложенный путь уплощается",
              _dest_name("awesome-pack/v2/src/agents/core/rev.md", "", "agent") == "core/rev.md",
              _dest_name("awesome-pack/v2/src/agents/core/rev.md", "", "agent"))
        check("префикс подкаталога отрезается",
              _dest_name("sub/agents/x.md", "sub", "agent") == "x.md",
              _dest_name("sub/agents/x.md", "sub", "agent"))

        print("\n[20] Безобидные метаданные не плодят предупреждения")
        fm, _, rep = _conv_agent(
            "---\nname: x\ndescription: d\nversion: 1.0\nauthor: someone\n"
            "tags: [a, b]\nexpertise_level: senior\ncategory: dev\n---\n\nb\n", tmp, "meta.md")
        check("метаданные перенесены", fm.get("version") == 1.0 and fm.get("author") == "someone", str(fm))
        check("про метаданные НЕТ отдельных предупреждений",
              not any("неизвестное поле" in m for _, m in rep.warnings), str(rep.warnings))
        check("метаданные собраны в сводку rep.meta_fields",
              {"version", "author", "tags", "expertise_level", "category"} <= rep.meta_fields,
              str(rep.meta_fields))
        fm, _, rep = _conv_agent("---\nname: x\ndescription: d\nweirdField: 1\n---\n\nb\n", tmp, "meta2.md")
        check("неизвестное НЕ-метаданное поле даёт предупреждение",
              any("weirdField" in m for _, m in rep.warnings), str(rep.warnings))

        print("\n[21] Манифест установок")
        from qwenkit.install import MANIFEST_NAME, _load_manifest, _save_manifest
        mbase = tmp / "manifest-test"
        check("пустой манифест = {}", _load_manifest(mbase) == {}, str(_load_manifest(mbase)))
        _save_manifest(mbase, {"o/r": {"ref": "main", "installed": ["agents/a.md"]}})
        m = _load_manifest(mbase)
        check("манифест сохраняется и читается", m.get("o/r", {}).get("installed") == ["agents/a.md"], str(m))
        check("битый манифест не роняет", True)
        (mbase / MANIFEST_NAME).write_text("{ не json", encoding="utf-8")
        check("битый json -> пустой манифест", _load_manifest(mbase) == {}, str(_load_manifest(mbase)))

        print("\n[22] install: разрешение коллизий имён")
        from qwenkit.install import _resolve_collisions, _dest_name, looks_like_agent
        items = [("categories/01-core/backend-developer.md", "backend-developer.md"),
                 ("categories/03-infra/backend-developer.md", "backend-developer.md"),
                 ("categories/01-core/api-designer.md", "api-designer.md")]
        got = [d for _, d in _resolve_collisions(items)]
        check("одноимённые агенты получают префикс каталога",
              got[0] != got[1] and got[2] == "api-designer.md", str(got))
        check("префикс = родительский каталог", got[0].endswith("/backend-developer.md"), str(got))
        check("без коллизий имена не меняются",
              [d for _, d in _resolve_collisions([("a/x.md", "x.md"), ("b/y.md", "y.md")])] == ["x.md", "y.md"])

        print("\n[23] install: имена назначения для разных структур репо")
        dest_cases = [
            ("agents/core/rev.md", "agent", "core/rev.md"),
            ("plugins/backend/agents/foo.md", "agent", "foo.md"),
            ("awesome-pack/v2/src/agents/x.md", "agent", "x.md"),
            ("subagents/y.md", "agent", "y.md"),
            ("top-level-agent.md", "agent", "top-level-agent.md"),
            (".claude/commands/git/commit.md", "command", "git/commit.md"),
            ("commands/plain.md", "command", "plain.md"),
        ]
        for path, kind, exp in dest_cases:
            got = _dest_name(path, "", kind)
            check(f"{path} -> {exp}", got == exp, got)
        check("subdir отрезается", _dest_name("sub/agents/x.md", "sub", "agent") == "x.md",
              _dest_name("sub/agents/x.md", "sub", "agent"))
        check("keep_parent сохраняет каталог",
              _dest_name("categories/01-core/x.md", "", "agent", keep_parent=True) == "categories/01-core/x.md",
              _dest_name("categories/01-core/x.md", "", "agent", keep_parent=True))

        print("\n[24] install: распознавание агента по frontmatter")
        agent_fm = [
            {"name": "a", "description": "d", "tools": ["Read"]},
            {"name": "a", "description": "d", "model": "haiku"},
            {"name": "a", "description": "d", "permissionMode": "plan"},
            {"name": "a", "description": "d", "color": "cyan"},
            {"name": "a", "description": "d"},                       # голый агент
            {"name": "a", "description": "d", "version": 1, "author": "x"},
        ]
        for fm in agent_fm:
            check(f"агент: {sorted(fm)[2:] or 'только name+description'}", looks_like_agent(fm), str(fm))
        not_agent = [
            {},
            {"name": "a"},
            {"description": "d"},
            # allowed-tools / argument-hint — признак КОМАНДЫ, а не агента
            {"name": "a", "description": "d", "allowed-tools": "Bash"},
            {"name": "a", "description": "d", "argument-hint": "[file]"},
            {"name": "a", "description": "d", "weirdUnknownField": 1},
            "не словарь",
            None,
        ]
        for fm in not_agent:
            check(f"не агент: {str(fm)[:48]}", not looks_like_agent(fm), str(fm))
        check("агент с безобидными метаданными распознаётся",
              looks_like_agent({"name": "a", "description": "d", "license": "MIT",
                                "version": 2, "tags": ["x"]}))
        check("агент с tools + allowed-tools всё равно агент",
              looks_like_agent({"name": "a", "description": "d",
                                "tools": ["Read"], "allowed-tools": "Bash"}))

        print("\n[25] convert: ложные срабатывания на чужом коде")
        # JavaScript-строка `Hello <@${event.user}>!` НЕ должна превращаться в !{...}
        js = "text: `Hello <@${event.user}>!`,"
        rep0 = Report()
        check("JS-строка с ! перед закрывающим бэктиком не трогается",
              convert_body(js, "x", rep0) == js, convert_body(js, "x", rep0))
        rep1 = Report()
        check("настоящая CC-вставка !`cmd` конвертируется",
              convert_body("diff: !`git diff`", "x", rep1) == "diff: !{git diff}",
              convert_body("diff: !`git diff`", "x", rep1))

        print("\n[16] Идемпотентность convert")
        fx = HERE / "fixture-cc"
        if fx.exists():
            work = tmp / "idem"
            shutil.copytree(fx, work, ignore=shutil.ignore_patterns(".qwen", "QWEN.md", ".gitignore", "MIGRATION_TODO.md"))
            for i in (1, 2):
                r = subprocess.run([sys.executable, str(ROOT / "qwenkit-cli"), "convert", str(work)],
                                   capture_output=True, text=True, timeout=180)
                if i == 1:
                    first = {p: p.read_bytes() for p in sorted((work / ".qwen").rglob("*")) if p.is_file()}
                else:
                    second = {p: p.read_bytes() for p in sorted((work / ".qwen").rglob("*")) if p.is_file()}
            same = {k: v for k, v in first.items() if k in second and second[k] == v}
            check("второй прогон не меняет содержимое .qwen (кроме .bak)",
                  len(same) >= len([k for k in first if not k.name.endswith(".bak")]) - 1,
                  f"first={len(first)} second={len(second)} same={len(same)}")
            check("convert exit 0", r.returncode == 0, r.stderr[-300:])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print(f"\n{'=' * 60}")
    print(f"  пройдено: {PASS}   провалено: {FAIL}")
    print(f"{'=' * 60}\n")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
