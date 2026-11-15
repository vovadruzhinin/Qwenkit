"""qwenkit — обвязка для Qwen Code: бесплатный API, миграция с Claude Code, стартовый набор.

Запуск:  python3 -m qwenkit <команда>   или   ./qwenkit <команда>
"""

from __future__ import annotations

import sys

__version__ = "1.0.0"

USAGE = f"""\
qwenkit {__version__} — обвязка для Qwen Code

Команды:
  doctor              проверить окружение: Node.js, qwen, сеть, ключи, settings.json
  setup               установить Qwen Code и настроить бесплатный API-провайдер
  providers           справочник бесплатных и платных провайдеров (ссылки, лимиты, модели)
  probe               живой тест API: какие модели реально работают с tool-calling
  convert             конвертировать проект Claude Code в формат Qwen Code
  pack                установить стартовый набор команд и субагентов
  install             поставить чужой набор агентов/команд с GitHub (с конвертацией)
  search              найти такие наборы на GitHub

Быстрый старт (бесплатно):
  1) qwenkit doctor
  2) возьмите ключ: https://www.modelscope.cn/my/myaccesstoken
     export MODELSCOPE_API_KEY=<ключ>
  3) qwenkit setup --provider modelscope --install
  4) qwenkit probe --provider modelscope
  5) qwenkit pack
  6) cd ваш-проект && qwen

Миграция с Claude Code:
  qwenkit convert .            # проект
  qwenkit convert --global     # ~/.claude -> ~/.qwen
  qwenkit convert --dry-run .  # посмотреть, что будет

Чужие наборы агентов и команд с GitHub:
  qwenkit search                                   # найти наборы
  qwenkit install owner/repo --dry-run             # посмотреть план
  qwenkit install owner/repo                       # поставить в ~/.qwen
  qwenkit install owner/repo --only agents         # только агентов
  qwenkit install --list                           # что установлено
  qwenkit install x --uninstall owner/repo         # удалить

Справка по команде: qwenkit <команда> --help
"""


def _providers(argv: list[str]) -> int:
    from .providers import FREE_ORDER, PAID_ORDER, PROVIDERS, openrouter_free_with_tools

    reset = bold = dim = ""
    if sys.stdout.isatty():
        reset, bold, dim = "\033[0m", "\033[1m", "\033[2m"

    def show(keys: list[str], title: str) -> None:
        print(f"\n{bold}{title}{reset}")
        for k in keys:
            p = PROVIDERS[k]
            print(f"\n  {bold}{p.title}{reset}   {dim}[--provider {p.key}]{reset}")
            print(f"  base_url : {p.base_url}")
            print(f"  env key  : {p.env_key}")
            print(f"  где взять: {p.signup}")
            print(f"  бесплатно: {p.free}")
            if p.models:
                print(f"  модели   : {', '.join(p.models[:6])}"
                      + (f" … (+{len(p.models) - 6})" if len(p.models) > 6 else ""))
            if p.notes:
                print(f"  {dim}заметка  : {p.notes}{reset}")

    show(FREE_ORDER, "БЕСПЛАТНЫЕ")
    show(PAID_ORDER, "ПЛАТНЫЕ (родной Qwen API)")

    print(f"\n{bold}Актуальные бесплатные модели OpenRouter с tool-calling{reset}")
    print(f"{dim}(запрашиваем живой каталог…){reset}")
    free = openrouter_free_with_tools()
    if free:
        for m in free[:15]:
            print(f"  · {m['id']:<52s} контекст {m['ctx']}")
        print(f"  {dim}всего: {len(free)}. Каталог меняется — сверяйтесь перед настройкой.{reset}")
    else:
        print("  не удалось получить каталог (нет сети?)")

    print(f"""
{bold}Важно{reset}
  Qwen OAuth (бесплатные 2000 запросов/день напрямую от Qwen) ОТКЛЮЧЁН 2026-04-15.
  Инструкции в старых статьях и видео больше не работают. Бесплатные пути сейчас:
  сторонний OpenAI-совместимый провайдер (ModelScope, OpenRouter, Groq,
  Cloudflare) или локальная модель через Ollama.
{reset}""")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(USAGE)
        return 0
    if argv[0] in ("-V", "--version", "version"):
        print(f"qwenkit {__version__}")
        return 0

    cmd, rest = argv[0], argv[1:]
    try:
        if cmd == "doctor":
            from .doctor import run
        elif cmd == "setup":
            from .setup_cmd import run
        elif cmd == "probe":
            from .probe import run
        elif cmd == "convert":
            from .convert import run
        elif cmd == "pack":
            from .pack import run
        elif cmd == "install":
            from .install import run
        elif cmd == "search":
            from .search import run
        elif cmd == "providers":
            return _providers(rest)
        else:
            print(f"неизвестная команда: {cmd}\n", file=sys.stderr)
            print(USAGE, file=sys.stderr)
            return 2
    except ImportError as e:
        print(f"ошибка импорта: {e}", file=sys.stderr)
        if "yaml" in str(e):
            print("установите зависимости: pip install pyyaml", file=sys.stderr)
        return 2
    return run(rest)


if __name__ == "__main__":
    raise SystemExit(main())
