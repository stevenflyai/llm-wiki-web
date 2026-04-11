"""
config.py — LLM Wiki 统一配置加载器
=====================================
从项目根目录的 .env 文件读取配置，并提供统一的 LLM 客户端工厂函数。

支持的 Provider：
  - anthropic  — Anthropic Claude（直接使用 anthropic SDK）
  - azure      — Azure OpenAI（使用 openai SDK 的 AzureOpenAI 客户端）
  - openai     — OpenAI（或任何兼容 OpenAI API 的服务）
  - ollama     — 本地 Ollama（基于 openai SDK，指向本地端口）
  - custom     — 任意 OpenAI 兼容第三方服务（DeepSeek、通义、Moonshot 等）

优先级（LLM_PROVIDER 留空时自动检测）：
  custom > anthropic > azure > openai > ollama
"""

from __future__ import annotations

__version__ = "0.2"
__release_date__ = "2026-04-11"
__author__ = "Steven Lian"
import os
import sys
from pathlib import Path
from typing import Optional

# ── .env 加载 ─────────────────────────────────────────────────────────────
def _load_dotenv(env_path: Path) -> None:
    """
    极简 .env 解析器（不依赖 python-dotenv）。
    规则：
      - # 开头的行为注释，跳过
      - KEY=VALUE，将 VALUE 写入 os.environ（已有值不覆盖）
      - VALUE 可用单引号或双引号包裹（自动去掉）
    """
    if not env_path.exists():
        return
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, raw_val = line.partition("=")
            key = key.strip()
            raw_val = raw_val.strip()
            # 处理带引号的值（引号内的 # 不是注释）
            if raw_val and raw_val[0] in ('"', "'"):
                quote = raw_val[0]
                end = raw_val.find(quote, 1)
                if end != -1:
                    val = raw_val[1:end]
                else:
                    val = raw_val[1:]
            else:
                # 无引号：去掉行内注释（# 及其后面的内容）
                if '#' in raw_val:
                    raw_val = raw_val[:raw_val.index('#')]
                val = raw_val.strip()
            # 只在环境变量尚未设置时写入（命令行 export 优先）
            if key and val and key not in os.environ:
                os.environ[key] = val


# 向上查找项目根目录的 .env（支持从 scripts/ 子目录调用）
_SCRIPTS_DIR = Path(__file__).parent
_PROJECT_ROOT = _SCRIPTS_DIR.parent
_load_dotenv(_PROJECT_ROOT / ".env")


# ── 配置读取 ──────────────────────────────────────────────────────────────
def _get(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


class LLMConfig:
    """从 .env / 环境变量中读取的配置快照"""

    provider: str           # 实际使用的 provider
    model: str              # 实际使用的模型名
    base_url: str           # API base URL
    api_key: str            # API Key（Ollama 时为占位符）
    api_version: str        # Azure OpenAI API 版本（仅 azure provider 使用）
    timeout: int            # 请求超时（秒）

    # PDF 相关
    pdf_backend: Optional[str]
    pdf_workers: int
    pdf_max_chars: int

    def __init__(self):
        requested = _get("LLM_PROVIDER").lower()

        # custom 必须显式配置
        if requested == "custom" or (not requested and _get("CUSTOM_BASE_URL") and _get("CUSTOM_API_KEY")):
            self.provider  = "custom"
            self.base_url  = _get("CUSTOM_BASE_URL")
            self.api_key   = _get("CUSTOM_API_KEY")
            self.model     = _get("CUSTOM_MODEL") or "gpt-4o"

        elif requested == "anthropic" or (not requested and _get("ANTHROPIC_API_KEY")):
            self.provider  = "anthropic"
            self.base_url  = _get("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
            self.api_key   = _get("ANTHROPIC_API_KEY")
            self.model     = _get("ANTHROPIC_MODEL", "claude-sonnet-4-5")

        elif requested == "azure" or (not requested and _get("AZURE_OPENAI_API_KEY") and _get("AZURE_OPENAI_ENDPOINT")):
            self.provider     = "azure"
            self.base_url     = _get("AZURE_OPENAI_ENDPOINT")              # e.g. https://xxx.openai.azure.com/
            self.api_key      = _get("AZURE_OPENAI_API_KEY")
            self.model        = _get("AZURE_OPENAI_DEPLOYMENT")            # deployment name
            self.api_version  = _get("AZURE_OPENAI_API_VERSION", "2024-12-01-preview")

        elif requested == "openai" or (not requested and _get("OPENAI_API_KEY")):
            self.provider  = "openai"
            self.base_url  = _get("OPENAI_BASE_URL", "https://api.openai.com/v1")
            self.api_key   = _get("OPENAI_API_KEY")
            self.model     = _get("OPENAI_MODEL", "gpt-4o")

        else:
            # 兜底：本地 Ollama
            self.provider  = "ollama"
            self.base_url  = _get("OLLAMA_BASE_URL", "http://localhost:11434/v1")
            self.api_key   = "ollama"
            self.model     = _get("OLLAMA_MODEL", "llama3.1:8b")

        if not hasattr(self, 'api_version'):
            self.api_version = ""
        self.timeout       = int(_get("LLM_TIMEOUT", "120"))
        self.pdf_backend   = _get("PDF_BACKEND") or None
        self.pdf_workers   = int(_get("PDF_WORKERS", "4"))
        self.pdf_max_chars = int(_get("PDF_MAX_CHARS", "24000"))

    # ── 命令行参数覆盖（优先级最高）────────────────────────────────────────
    def apply_cli_overrides(
        self,
        *,
        use_ollama: bool = False,
        model: Optional[str] = None,
        pdf_backend: Optional[str] = None,
        workers: Optional[int] = None,
    ) -> "LLMConfig":
        """将命令行参数覆盖到当前配置（返回 self，方便链式调用）"""
        if use_ollama:
            self.provider  = "ollama"
            self.base_url  = _get("OLLAMA_BASE_URL", "http://localhost:11434/v1")
            self.api_key   = "ollama"
            self.model     = _get("OLLAMA_MODEL", "llama3.1:8b")
        if model:
            self.model = model
        if pdf_backend:
            self.pdf_backend = pdf_backend
        if workers is not None:
            self.pdf_workers = workers
        return self

    def summary(self) -> str:
        """返回适合打印的配置摘要"""
        key_hint = f"...{self.api_key[-6:]}" if len(self.api_key) > 6 else "(本地/无需Key)"
        lines = [
            f"Provider : {self.provider}",
            f"Model    : {self.model}",
            f"Base URL : {self.base_url}",
            f"API Key  : {key_hint}",
        ]
        if self.pdf_backend:
            lines.append(f"PDF 引擎 : {self.pdf_backend}")
        return "\n".join(lines)


# ── LLM 客户端工厂 ────────────────────────────────────────────────────────
def make_client(cfg: LLMConfig):
    """
    根据配置创建 LLM 客户端，返回 (client, client_type) 元组。
    client_type 为 'openai' 或 'anthropic'，调用方用来选择不同的调用方式。
    """
    if cfg.provider == "anthropic":
        try:
            import anthropic
        except ImportError:
            print("请安装 anthropic SDK: pip install anthropic")
            sys.exit(1)

        kwargs: dict = {"api_key": cfg.api_key}
        # 只在自定义 base_url 时才传入，用 rstrip("/") 消除末尾斜杠的差异
        _DEFAULT_ANTHROPIC = "https://api.anthropic.com"
        if cfg.base_url and cfg.base_url.rstrip("/") != _DEFAULT_ANTHROPIC:
            kwargs["base_url"] = cfg.base_url
        client = anthropic.Anthropic(**kwargs)
        return client, "anthropic"

    elif cfg.provider == "azure":
        try:
            from openai import AzureOpenAI
        except ImportError:
            print("请安装 openai SDK (>=1.0): pip install openai")
            sys.exit(1)

        client = AzureOpenAI(
            api_key=cfg.api_key,
            api_version=cfg.api_version,
            azure_endpoint=cfg.base_url,
            timeout=cfg.timeout,
        )
        return client, "openai"   # Azure 使用 openai 兼容的调用方式

    else:
        # openai / ollama / custom 均使用 openai SDK
        try:
            from openai import OpenAI
        except ImportError:
            print("请安装 openai SDK: pip install openai")
            sys.exit(1)

        kwargs: dict = {"api_key": cfg.api_key, "timeout": cfg.timeout}
        # 只在自定义 base_url 时才传入，同样消除末尾斜杠差异
        _DEFAULT_OPENAI = "https://api.openai.com/v1"
        if cfg.base_url and cfg.base_url.rstrip("/") != _DEFAULT_OPENAI:
            kwargs["base_url"] = cfg.base_url
        client = OpenAI(**kwargs)
        return client, "openai"


def call_llm(client, client_type: str, cfg: LLMConfig,
             system_prompt: str, user_prompt: str,
             max_tokens: int = 4096) -> str:
    """
    统一的 LLM 调用接口，自动适配 OpenAI / Anthropic SDK 差异。
    """
    if client_type == "anthropic":
        response = client.messages.create(
            model=cfg.model,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        return response.content[0].text

    else:  # openai-compatible
        response = client.chat.completions.create(
            model=cfg.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt},
            ],
            temperature=0.3,
            max_tokens=max_tokens,
        )
        return response.choices[0].message.content


# ── 便捷函数：一行初始化 ──────────────────────────────────────────────────
def setup(
    *,
    use_ollama: bool = False,
    model: Optional[str] = None,
    pdf_backend: Optional[str] = None,
    workers: Optional[int] = None,
) -> tuple:
    """
    一行完成：读取 .env → 应用 CLI 覆盖 → 创建客户端。
    返回 (client, client_type, cfg)。

    用法示例（在各脚本中）：
        from config import setup, call_llm
        client, client_type, cfg = setup(use_ollama=args.ollama, model=args.model)
        answer = call_llm(client, client_type, cfg, SYSTEM_PROMPT, user_prompt)
    """
    cfg = LLMConfig()
    cfg.apply_cli_overrides(use_ollama=use_ollama, model=model,
                             pdf_backend=pdf_backend, workers=workers)
    client, client_type = make_client(cfg)
    return client, client_type, cfg


# ── 调试入口 ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    cfg = LLMConfig()
    print("当前配置：")
    print(cfg.summary())
