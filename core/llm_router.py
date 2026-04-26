"""
Web Analyst OS — LiteLLM 統一ラッパー
analyst_config.yaml のモデル設定を読み取り litellm.completion() に渡す。
"""
import os
import time
from pathlib import Path
from typing import Optional
import yaml
import litellm

litellm.set_verbose = False
litellm.suppress_debug_info = True
os.environ.setdefault("LITELLM_LOG", "ERROR")

_CONFIG_PATH = Path(__file__).parent.parent / "analyst_config.yaml"
_config_cache: Optional[dict] = None


def load_config() -> dict:
    global _config_cache
    if _config_cache is None:
        with open(_CONFIG_PATH, encoding="utf-8") as f:
            _config_cache = yaml.safe_load(f)
    return _config_cache


def _resolve_model(role: str) -> str:
    """役割名からモデル名を返す（specialist / red_team / synthesis / technical）"""
    cfg = load_config()
    models = cfg.get("models", {})
    return models.get(role, models.get("specialist", "claude-sonnet-4-6"))


def _litellm_model(model_name: str) -> str:
    """
    model_name を litellm が理解できる形式に変換する。
    claude-* → anthropic/claude-*, gpt-* はそのまま。
    """
    if model_name.startswith("claude-"):
        return f"anthropic/{model_name}"
    return model_name


def call_llm(
    role: str,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 1500,
    max_retries: int = 3,
    base_delay: float = 1.0,
    model_override: Optional[str] = None,
) -> str:
    """
    指定ロールのモデルで LLM を呼び出す。
    model_override が指定された場合はそちらを優先する。
    APIエラー時は指数バックオフでリトライ。
    """
    raw_model = model_override if model_override else _resolve_model(role)
    model = _litellm_model(raw_model)

    last_error = None
    for attempt in range(max_retries):
        try:
            response = litellm.completion(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=max_tokens,
                temperature=0.7,
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            last_error = e
            err_str = str(e)
            if any(kw in err_str for kw in ("RESOURCE_EXHAUSTED", "quota", "billing", "prepayment", "429", "credit balance", "credit_balance")):
                raise RuntimeError(f"LLM quota/billing error [{role}]: {e}") from e
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                print(f"    [LLM retry {attempt+1}/{max_retries}] {role} | {delay:.1f}s 待機")
                time.sleep(delay)

    raise RuntimeError(f"LLM call failed [{role}] after {max_retries} retries: {last_error}")
