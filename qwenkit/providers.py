"""Каталог провайдеров для Qwen Code: бесплатные и платные.

Qwen OAuth (бесплатные 2000 запросов/день) ОТКЛЮЧЁН 2026-04-15 — старые
инструкции из интернета больше не работают. Бесплатный путь теперь:
сторонний OpenAI-совместимый провайдер или локальная модель.

Лимиты указаны по данным на 2026-10-24 и могут меняться — всегда сверяйтесь
со страницей провайдера. Функция live_models() отдаёт актуальный список моделей.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Provider:
    key: str                 # внутренний идентификатор
    title: str               # человекочитаемое имя
    base_url: str            # OpenAI-совместимый корень (/v1)
    env_key: str             # имя env-переменной с ключом
    signup: str              # где взять ключ
    free: str                # что именно бесплатно
    models: list = field(default_factory=list)   # проверенные id моделей
    models_url: str | None = None                # откуда брать живой список
    protocol: str = "openai"
    notes: str = ""
    local: bool = False


PROVIDERS: dict[str, Provider] = {}


def _reg(p: Provider) -> Provider:
    PROVIDERS[p.key] = p
    return p


# ============================== БЕСПЛАТНЫЕ =================================

_reg(Provider(
    key="modelscope",
    title="ModelScope API-Inference (Alibaba)",
    base_url="https://api-inference.modelscope.cn/v1",
    env_key="MODELSCOPE_API_KEY",
    signup="https://www.modelscope.cn/my/myaccesstoken  (бесплатная регистрация, "
           "для международного доступа — modelscope.ai)",
    free="~2000 запросов в день, OpenAI-совместимый API, каталог из ~37 моделей "
         "(Qwen3.5 / Qwen3.8, DeepSeek-V4, GLM-4.7/5.2). Лимит сверяйте на "
         "modelscope.ai/docs/model-service/API-Inference/limits",
    models=[
        "Qwen/Qwen3.5-397B-A17B",
        "Qwen/Qwen3.5-122B-A10B",
        "Qwen/Qwen3.8-Flash-Next",
        "Qwen/Qwen3.8-27B",
        "Qwen/Qwen3.5-35B-A3B",
        "Qwen/Qwen3.5-27B",
        "deepseek-ai/DeepSeek-V4.1-Flash",
        "deepseek-ai/DeepSeek-V4-Pro",
        "ZhipuAI/GLM-5.2",
        "ZhipuAI/GLM-4.7-Flash",
    ],
    models_url="https://api-inference.modelscope.cn/v1/models",
    notes="Лучший бесплатный вариант для агентного кодинга: большой каталог, "
          "щедрая дневная квота, родные модели Qwen.",
))

_reg(Provider(
    key="openrouter",
    title="OpenRouter (:free модели)",
    base_url="https://openrouter.ai/api/v1",
    env_key="OPENROUTER_API_KEY",
    signup="https://openrouter.ai/settings/keys",
    free="50 бесплатных запросов в день (1000/день, если на аккаунте есть "
         "купленные кредиты от ~9-10$), 20 RPM. Каталог :free-моделей плавает.",
    models=[
        "openrouter/free",                      # роутер: сам выбирает бесплатную модель
        "cohere/north-mini-code:free",
        "nvidia/nemotron-3-ultra-550b-a55b:free",
        "nvidia/nemotron-3.5-lightning:free",
        "thinkingmachines/inkling:free",
        "google/gemma-4-31b-it:free",
        "poolside/laguna-s-2.1:free",
        "xingchen-agi/xing4.0-29b-a4b:free",
    ],
    models_url="https://openrouter.ai/api/v1/models",
    notes="`openrouter/free` — роутер случайных бесплатных моделей: удобно для "
          "экспериментов, но поведение нестабильно между запусками. "
          "Для кодинга берите конкретную :free-модель с tools=True.",
))

_reg(Provider(
    key="groq",
    title="Groq (free tier)",
    base_url="https://api.groq.com/openai/v1",
    env_key="GROQ_API_KEY",
    signup="https://console.groq.com/keys",
    free="~1000 запросов/день и ~200K токенов/день на бесплатных моделях, "
         "8K токенов/минуту, 30 RPM",
    models=[],       # каталог доступен только с ключом
    models_url="https://api.groq.com/openai/v1/models",
    notes="Очень быстрый инференс. Бесплатные модели меняются; список смотрите "
          "в консоли. Хорош как `fastModel` для субагентов.",
))

_reg(Provider(
    key="cerebras",
    title="Cerebras Cloud",
    base_url="https://api.cerebras.ai/v1",
    env_key="CEREBRAS_API_KEY",
    signup="https://cloud.cerebras.ai/",
    free="разовые ~5$ кредита на 30 дней (требуется привязка карты), 5 RPM",
    models=[],
    models_url="https://api.cerebras.ai/v1/models",
    notes="До ~3000 токенов/с — самый быстрый из бесплатных. Это триал, а не "
          "постоянная квота.",
))

_reg(Provider(
    key="cloudflare",
    title="Cloudflare Workers AI",
    base_url="https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/ai/v1",
    env_key="CLOUDFLARE_API_TOKEN",
    signup="https://dash.cloudflare.com/profile/api-tokens",
    free="10 000 «нейронов» в день (~эквивалент десятков тысяч запросов к "
         "небольшим моделям), 300 RPM",
    models=[
        "@cf/openai/gpt-oss-120b",
        "@cf/meta/llama-3.3-70b-instruct-fp8-fast",
        "@hf/Qwen/Qwen3-Coder-30B-A3B-Instruct",
    ],
    notes="В base_url нужно подставить свой ACCOUNT_ID (взять в дашборде). "
          "Каталог моделей: developers.cloudflare.com/workers-ai/models",
))

_reg(Provider(
    key="ollama",
    title="Ollama (локально, без интернета и без ключей)",
    base_url="http://localhost:11434/v1",
    env_key="OLLAMA_API_KEY",   # Ollama ключ не проверяет, но поле обязательно
    signup="https://ollama.com/download",
    free="полностью бесплатно и без лимитов; нужна видеопамять/RAM под модель",
    models=[
        "qwen3-coder:30b",
        "qwen3:14b",
        "qwen2.5-coder:7b",
        "gpt-oss:20b",
    ],
    models_url="http://localhost:11434/v1/models",
    local=True,
    notes="Единственный вариант с нулевыми ограничениями и полной приватностью. "
          "Для агентного кодинга нужно от ~16 ГБ RAM (7-14B) до 24+ ГБ (30B). "
          "Ключ можно задать любой строкой, например `ollama`.",
))

# ================================ ПЛАТНЫЕ ==================================

_reg(Provider(
    key="dashscope",
    title="Alibaba DashScope (официальный Qwen API)",
    base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
    env_key="DASHSCOPE_API_KEY",
    signup="https://www.alibabacloud.com/en/product/modelstudio  "
           "(для Китая: https://dashscope.aliyuncs.com/compatible-mode/v1)",
    free="новым аккаунтам обычно дают пробные токены на каждую модель; "
         "далее оплата по факту. Есть отдельные Coding Plan / Token Plan — "
         "в Qwen Code они настраиваются через /auth, а не через modelProviders.",
    models=["qwen3-coder-plus", "qwen-max", "qwen-plus", "qwen-turbo"],
    models_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1/models",
    notes="Родной провайдер Qwen: лучшие результаты на qwen3-coder-plus.",
))

FREE_ORDER = ["modelscope", "openrouter", "groq", "cloudflare", "cerebras", "ollama"]
PAID_ORDER = ["dashscope"]


def live_models(p: Provider, api_key: str | None = None, timeout: int = 20) -> tuple[bool, list[str], str]:
    """Запросить живой список моделей провайдера.

    Возвращает (ок?, список id, сообщение об ошибке).
    """
    import json
    import ssl
    import urllib.request

    if not p.models_url:
        return False, [], "нет URL каталога"
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    headers = {"User-Agent": "qwenkit/1.0", "Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    try:
        req = urllib.request.Request(p.models_url, headers=headers)
        data = json.load(urllib.request.urlopen(req, timeout=timeout, context=ctx))
        items = data.get("data", data if isinstance(data, list) else [])
        ids = [m.get("id") for m in items if isinstance(m, dict) and m.get("id")]
        return True, ids, ""
    except Exception as e:                                    # noqa: BLE001
        return False, [], f"{type(e).__name__}: {e}"


def openrouter_free_with_tools(timeout: int = 25) -> list[dict]:
    """Полностью бесплатные модели OpenRouter с поддержкой tool-calling.

    Tool-calling обязателен: без него агент в Qwen Code не сможет вызывать
    инструменты.
    """
    import json
    import ssl
    import urllib.request

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        req = urllib.request.Request(
            "https://openrouter.ai/api/v1/models",
            headers={"User-Agent": "qwenkit/1.0"},
        )
        data = json.load(urllib.request.urlopen(req, timeout=timeout, context=ctx))
    except Exception:                                          # noqa: BLE001
        return []
    out = []
    for m in data.get("data", []):
        pr = m.get("pricing") or {}
        if str(pr.get("prompt")) != "0" or str(pr.get("completion")) != "0":
            continue
        params = m.get("supported_parameters") or []
        if "tools" not in params:
            continue
        out.append({
            "id": m["id"],
            "ctx": m.get("context_length"),
            "name": m.get("name"),
        })
    return sorted(out, key=lambda x: -(x["ctx"] or 0))
