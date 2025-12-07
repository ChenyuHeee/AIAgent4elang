import asyncio
import json
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import httpx
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential


@dataclass
class DeepSeekConfig:
    api_key: str
    base_url: str
    model: str
    temperature: float = 0.2
    max_tokens: int = 1024


class DeepSeekClient:
    def __init__(self, cfg: DeepSeekConfig) -> None:
        self.cfg = cfg
        self._client = httpx.AsyncClient(base_url=cfg.base_url, timeout=30)

    async def close(self) -> None:
        await self._client.aclose()

    async def chat(self, messages: List[Dict[str, str]]) -> str:
        headers = {"Authorization": f"Bearer {self.cfg.api_key}"}
        payload = {
            "model": self.cfg.model,
            "messages": messages,
            "temperature": self.cfg.temperature,
            "max_tokens": self.cfg.max_tokens,
        }
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=1, max=6),
            retry=retry_if_exception_type(httpx.HTTPError),
            reraise=True,
        ):
            with attempt:
                resp = await self._client.post("/v1/chat/completions", headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()
                return data["choices"][0]["message"]["content"]
        raise RuntimeError("DeepSeek chat retries exhausted")


def build_prompt(question: str, options: List[str], q_type: str) -> List[Dict[str, str]]:
    sys_msg = (
        "You are an exam assistant. Given a question, options, and type, respond strictly with JSON "
        "{\"type\": <single|multi|fill>, \"answer\": [...] or string}."
    )
    user_payload = {"question": question, "options": options, "type": q_type}
    return [
        {"role": "system", "content": sys_msg},
        {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
    ]


def parse_answer(raw: str) -> Dict[str, Any]:
    try:
        parsed = json.loads(raw)
        if "type" in parsed and "answer" in parsed:
            return parsed
    except json.JSONDecodeError:
        pass
    return {"type": "unknown", "answer": raw.strip()}


def load_config(config: Dict[str, Any]) -> DeepSeekConfig:
    key = config["deepseek"].get("api_key", "")
    if key.startswith("env:"):
        env_var = key.split(":", 1)[1]
        key = os.getenv(env_var, "")
    if not key:
        raise ValueError("DeepSeek API key is missing; set env or config")
    return DeepSeekConfig(
        api_key=key,
        base_url=config["deepseek"].get("base_url", "https://api.deepseek.com"),
        model=config["deepseek"].get("model", "deepseek-chat"),
        temperature=float(config["deepseek"].get("temperature", 0.2)),
        max_tokens=int(config["deepseek"].get("max_tokens", 1024)),
    )


async def answer_question(client: DeepSeekClient, question: str, options: List[str], q_type: str) -> Dict[str, Any]:
    messages = build_prompt(question, options, q_type)
    content = await client.chat(messages)
    return parse_answer(content)


async def main_demo() -> None:
    # Minimal demo; replace question/options with real DOM/OCR output.
    import yaml

    with open("config.yaml", "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    ds_cfg = load_config(cfg)
    client = DeepSeekClient(ds_cfg)
    try:
        ans = await answer_question(client, "2+2=?", ["A.3", "B.4"], "single")
        print(ans)
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main_demo())
