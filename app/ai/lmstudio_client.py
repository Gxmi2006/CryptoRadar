from __future__ import annotations

import logging
from typing import Any


log = logging.getLogger(__name__)


class LMStudioClient:
    """Local LM Studio client using the OpenAI-compatible API."""

    def __init__(self, config: dict[str, Any]):
        ai_cfg = config.get("ai", {})
        self.base_url = ai_cfg.get("base_url", "http://localhost:1234/v1")
        self.model = ai_cfg.get("model", "qwen2.5-7b-instruct")
        self.temperature = float(ai_cfg.get("temperature", 0.2))
        self.max_tokens = int(ai_cfg.get("max_tokens", 500))
        self.timeout = float(ai_cfg.get("timeout_seconds", 20))
        self.reasoning_effort = ai_cfg.get("reasoning_effort", "none")
        self._client: Any | None = None
        self._client_error: str | None = None

    def is_available(self) -> bool:
        client = self._get_client()
        if client is None:
            return False
        try:
            client.models.list()
            return True
        except Exception as exc:
            log.warning("LM Studio unavailable: %s", exc)
            return False

    def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int | None = None,
        reasoning_effort: str | None = None,
        timeout: float | None = None,
    ) -> str | None:
        client = self._get_client()
        if client is None:
            return None
        try:
            effort = self.reasoning_effort if reasoning_effort is None else reasoning_effort
            kwargs: dict[str, Any] = {}
            if effort:
                kwargs["extra_body"] = {"reasoning_effort": effort}
            request_timeout = self.timeout if timeout is None else timeout
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=self.temperature,
                max_tokens=max_tokens or self.max_tokens,
                timeout=request_timeout,
                **kwargs,
            )
            content = response.choices[0].message.content
            return content.strip() if content else None
        except Exception as exc:
            log.warning("LM Studio chat failed: %s", exc)
            return None

    def _get_client(self) -> Any | None:
        if self._client is not None:
            return self._client
        if self._client_error is not None:
            return None
        try:
            from openai import OpenAI

            self._client = OpenAI(base_url=self.base_url, api_key="not-needed", timeout=self.timeout, max_retries=0)
            return self._client
        except Exception as exc:
            self._client_error = str(exc)
            log.warning("OpenAI client unavailable for LM Studio: %s", exc)
            return None
