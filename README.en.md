# qwenkit

**[Русская версия](README.md)** — основной документ.

Setup, migration and a starter pack for [Qwen Code](https://github.com/QwenLM/qwen-code),
the open-source terminal coding agent.

One Python script, one dependency (`pyyaml`). Works on Windows, macOS and Linux.

> 👉 Russian-speaking users: see **[docs/GUIDE.md](docs/GUIDE.md)** for a
> step-by-step user guide (in Russian). This file is the reference for internals
> and mapping tables.

```
qwenkit doctor      diagnose your environment
qwenkit providers   catalogue of free API providers
qwenkit setup       install Qwen Code + generate ~/.qwen/settings.json
qwenkit probe       live test: which models actually support tool-calling
qwenkit convert     migrate a Claude Code project to Qwen Code
qwenkit pack        starter pack: 8 slash commands + 6 subagents
qwenkit install     install a third-party agent/command pack from GitHub
qwenkit search      find such packs on GitHub
```

## What it does

Eight commands cover the whole path: from "no key, no config" to a working agent
with a starter pack of commands and subagents.

| Goal | Command | Result |
| --- | --- | --- |
| Find out what is broken | `doctor` | report on Node.js, `qwen`, network, keys and `settings.json`, with a concrete hint for each problem |
| Pick a free provider | `providers` | allowances, key links and models, plus a live catalogue of free OpenRouter models with tool-calling |
| Connect a model | `setup` | installs Qwen Code (with `--install`) and writes `~/.qwen/settings.json` for the chosen provider |
| Make sure the model fits an agent | `probe` | a real request that declares a tool, showing whether tool-calling actually works |
| Move off Claude Code | `convert` | `CLAUDE.md` → `QWEN.md`, commands, subagents, `.mcp.json`, `settings.json`; ambiguous items go to `MIGRATION_TODO.md`, originals to a backup |
| Get a starter pack | `pack` | 8 commands and 6 subagents into `~/.qwen` or `./.qwen` |
| Install a third-party pack | `search`, `install` | search and install with conversion to the Qwen Code format, plus a manifest for exact removal |

**Three typical flows**

- **From scratch:** `doctor` → ModelScope key → `setup --provider modelscope --install --refresh-models` → `probe` → `pack`.
- **Migrating from Claude Code:** `convert --dry-run .` → `convert .` → `convert --global`.
- **Ready-made commands:** `search` → `install owner/repo --dry-run` → `install owner/repo`.

Details for each command are in the sections below; the step-by-step guide is in
[docs/GUIDE.md](docs/GUIDE.md) (Russian).

## Why this exists

**The free Qwen OAuth tier (2000 requests/day) was discontinued on 2026-04-15.**
Most articles and videos still tell you to run `qwen` → `/auth` → Qwen OAuth.
That no longer works — the official docs section is literally titled
"Option 2: Qwen OAuth (Discontinued)".

What is actually free now:

| Provider | Free allowance | Key |
| --- | --- | --- |
| **ModelScope API-Inference** ⭐ | ~2000 requests/day, ~37 models: Qwen3.5/3.8, DeepSeek-V4, GLM-5.2 | [modelscope.cn/my/myaccesstoken](https://www.modelscope.cn/my/myaccesstoken) |
| OpenRouter | 50 requests/day (1000 with purchased credits) | [openrouter.ai/settings/keys](https://openrouter.ai/settings/keys) |
| Groq | ~1000 requests/day, ~200K tokens/day | [console.groq.com/keys](https://console.groq.com/keys) |
| Cloudflare Workers AI | 10,000 Neurons/day | [dash.cloudflare.com](https://dash.cloudflare.com/profile/api-tokens) |
| Ollama | unlimited, offline | none |

Allowances change. `qwenkit providers` prints the reference with links,
`qwenkit probe` checks the real situation with a live request.

### Tool-calling is mandatory

Qwen Code is an **agent**: it calls tools (read files, run shell, search).
A model without function calling will not work as an agent even if plain chat
works fine. `qwenkit probe` tests exactly that — it sends a request with a
declared tool and checks whether the model returned `tool_calls`.

## Quick start

```bash
git clone https://github.com/vovadruzhinin/qwenkit && cd qwenkit
pip install -r requirements.txt     # the only dependency is pyyaml

qwenkit_cli() { python3 qwenkit-cli "$@"; }     # or: pip install .

export MODELSCOPE_API_KEY='ms-...'              # free key, link above
qwenkit_cli setup --provider modelscope --install --refresh-models
qwenkit_cli probe --provider modelscope
qwenkit_cli pack
cd your-project && qwen
```

Or install as a package to get the `qwenkit` command:

```bash
pip install .
qwenkit doctor
```

## Migrating from Claude Code

```bash
qwenkit convert --dry-run .     # preview
qwenkit convert .               # convert this project
qwenkit convert --global        # ~/.claude -> ~/.qwen
```

Nothing is overwritten silently: existing files go to `.qwen-backup-<timestamp>/`,
everything ambiguous lands in `MIGRATION_TODO.md`.

| Claude Code | Qwen Code |
| --- | --- |
| `CLAUDE.md` | `QWEN.md` (Qwen also reads `AGENTS.md` natively) |
| `CLAUDE.local.md` | `.qwen/QWEN.local.md` + a `.gitignore` rule |
| `.claude/commands/**.md` | `.qwen/commands/**.md` |
| `.claude/agents/**.md` | `.qwen/agents/**.md` |
| `.mcp.json` | `.qwen/.mcp.json` (identical format) |
| `$ARGUMENTS` | `{{args}}` |
| `` !`cmd` `` | `!{cmd}` |
| `@docs/file.md` | `@{docs/file.md}` |
| `permissionMode: acceptEdits` | `approvalMode: auto-edit` |
| `model: haiku` | `model: fast` |
| `Read` / `Bash` / `Task` | `read_file` / `run_shell_command` / `agent` |

### The trap worth knowing about

Claude Code has `BashOutput` and `KillShell`; Qwen Code has no separate tools
for those — `run_shell_command` covers everything. A naive converter would turn
`disallowedTools: [KillShell]` into `disallowedTools: [run_shell_command]` and
**silently strip the agent of all shell access**. qwenkit drops those tools and
warns loudly instead.

Two more things it fixes: hook matchers (`"Edit|Write"` → `"edit|write_file"`,
because Qwen matches on canonical tool names) and hook timeouts (seconds in Qwen,
though values ≥ 1000 are still read as milliseconds for compatibility).

## Starter pack

`qwenkit pack` installs 8 commands (`/git:commit`, `/review`, `/tests`,
`/refactor`, `/security`, `/fix-ci`, `/explain`, `/doc`) and 6 subagents
(`reviewer` — read-only in `plan` mode, `tester`, `researcher` on the fast model,
`documenter`, `refactorer`, `python-expert`).

```bash
qwenkit pack --list              # show contents
qwenkit pack --target project    # into ./.qwen instead of ~/.qwen
qwenkit pack --only agents
```

## Installing third-party packs from GitHub

Hundreds of Claude Code packs are published on GitHub — folders of `.md` agents
and commands. `qwenkit` installs them in one command, converting to the Qwen
Code format on the fly.

```bash
qwenkit search                                # find packs
qwenkit install owner/repo --dry-run          # preview the plan
qwenkit install owner/repo                    # install into ~/.qwen
qwenkit install owner/repo/agents             # only a subdirectory
qwenkit install owner/repo --only commands
qwenkit install owner/repo --prefix mypack-   # namespace to avoid collisions
qwenkit install --list                        # what qwenkit installed
qwenkit install x --uninstall owner/repo      # remove it again
```

### Why it does not hit the rate limit

Unauthenticated GitHub API access allows only **60 requests/hour**, so:

1. the full file list comes from **one** `git/trees?recursive=1` call;
2. file contents are downloaded from `raw.githubusercontent.com`, which does
   **not** count against the `api.github.com` limit;
3. `search` uses the Search API (10 req/min unauthenticated) and sleeps between
   queries.

Set `GITHUB_TOKEN` for a 5000/hour limit if you install a lot.

### What gets installed

| Repo content | Behaviour |
| --- | --- |
| `agents/**.md`, `subagents/**.md` | converted → `.qwen/agents/` |
| `commands/**.md`, `commands/**.toml` | converted → `.qwen/commands/` |
| `.mcp.json`, `mcp.json` | merged into yours, with a warning |
| `CLAUDE.md`, `AGENTS.md` | **not** merged into your `QWEN.md`; saved to `.qwen/imported-notes/` for review |
| `.claude/settings.json` | **never installed** — it may contain hooks that run arbitrary commands. You get a link instead |
| `README`, `CHANGELOG`, `LICENSE`, source code | ignored |

If agents from different sections collide by name, one of them gets its parent
directory as a prefix, so files never overwrite each other.

### Content-based detection

Not every pack keeps agents in an `agents/` folder. The largest ones look like this:

```
categories/01-core-development/api-designer.md
categories/03-infrastructure/backend-developer.md
```

Paths alone cannot tell those apart from documentation. So if path heuristics find
fewer than three agents/commands, `qwenkit` downloads the `.md` files (in parallel,
up to 250) and inspects the frontmatter: `name` + `description` plus any agent field
(`tools`, `model`, `permissionMode`, `color`, `maxTurns`, …) means it is an agent.
`allowed-tools` or `argument-hint` overrides that — those mark a command.

On a 198-file repository this takes ~10 seconds and finds 157 agents. When the
layout is conventional, the content scan is skipped entirely.

Every install is recorded in `.qwen/.qwenkit-installed.json`, so `--uninstall`
removes exactly what qwenkit added and nothing of yours.

### Security

Agents and commands are **prompts that your agent will execute with access to
your files and shell**. A third-party pack means third-party instructions.
qwenkit reduces the risk (it refuses foreign `settings.json`, does not merge
foreign memory files, warns on every `!{...}` shell injection, and makes
installs reversible) but it does not replace reading the files.

## Tests

```bash
python3 tests/test_qwenkit.py    # 155 checks, no pytest required
```

## Sources

Every mapping table comes from primary sources: the docs and source of
`QwenLM/qwen-code` **0.26.0**, verified on **2026-10-24**. Full list of files
and update instructions: [`SOURCES.md`](SOURCES.md).

## License

MIT — see [LICENSE](LICENSE).

qwenkit is an independent third-party tool. It is not part of Qwen Code, does not
modify it, and is not affiliated with Alibaba Group. Qwen Code and Qwen are
trademarks of Alibaba Group, mentioned here for identification purposes.
