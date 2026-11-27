import json
from typing import Any

import httpx


class JevCrateJudge:
    def __init__(self, api_key: str) -> None:
        self._key = api_key

    def evaluate(self, request: dict[str, Any]) -> dict[str, Any]:
        if not self._key:
            raise ValueError("Autofile requires MCM_TYPESAFE_API_KEY")
        response = httpx.post(
            "https://api.typesafe.ai/v1/systemone",
            headers={"Authorization": f"Bearer {self._key}"},
            json=request,
            timeout=30,
        )
        response.raise_for_status()
        result: dict[str, Any] = response.json()
        if not isinstance(result, dict):
            raise ValueError("Jev returned an invalid response object")
        # JSON audit columns must remain writable even if the provider emits non-finite values.
        json.dumps(result, allow_nan=False)
        return result
