import json
from dataclasses import dataclass
from typing import Any, Dict, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse, parse_qsl, urlunparse
from urllib.request import Request, urlopen

from .constants import DEFAULT_API_BASE_URL


@dataclass
class ApiResponse:
    ok: bool
    status: int
    data: Dict[str, Any]
    error: Optional[str] = None


class RenderBobClient:
    def __init__(self, base_url: str = DEFAULT_API_BASE_URL, api_token: str = ""):
        self.base_url = base_url.rstrip("/")
        self.api_token = self.normalize_api_token(api_token)

    def set_api_token(self, token: str) -> None:
        self.api_token = self.normalize_api_token(token)

    def get(self, path: str, query: Optional[Dict[str, Any]] = None) -> ApiResponse:
        query = query or {}
        suffix = f"?{urlencode(query)}" if query else ""
        return self._request("GET", f"{path}{suffix}")

    def post(self, path: str, payload: Optional[Dict[str, Any]] = None) -> ApiResponse:
        return self._request("POST", path, payload)

    def put(self, path: str, payload: Optional[Dict[str, Any]] = None) -> ApiResponse:
        return self._request("PUT", path, payload)

    def delete(self, path: str, payload: Optional[Dict[str, Any]] = None) -> ApiResponse:
        return self._request("DELETE", path, payload)

    def _request(
        self,
        method: str,
        path: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> ApiResponse:
        body = None
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        token_type = self._token_type(self.api_token)
        if token_type == "api":
            headers["x-api-token"] = self.api_token
            headers["Authorization"] = f"Bearer {self.api_token}"
        elif self.api_token:
            # Support direct bearer/JWT usage when users paste auth tokens.
            headers["Authorization"] = f"Bearer {self.api_token}"

        last_error = ApiResponse(False, 0, {}, "Request failed")
        for candidate_path in self._candidate_paths(path):
            request_url = f"{self.base_url}{candidate_path}"
            if token_type == "api":
                request_url = self._append_query_param(
                    request_url,
                    "api_token",
                    self.api_token,
                )

            result = self._request_once(method, request_url, headers, body)
            if result.ok:
                return result
            last_error = result

            # Stop early on non-auth path issues.
            if result.status not in (401, 403, 404):
                break

        return last_error

    @staticmethod
    def _safe_json(value: str) -> Dict[str, Any]:
        try:
            return json.loads(value) if value else {}
        except Exception:
            return {}

    @staticmethod
    def normalize_api_token(token: str) -> str:
        cleaned = (token or "").strip()
        if not cleaned:
            return ""

        if cleaned.lower().startswith("bearer "):
            cleaned = cleaned[7:].strip()

        # Handle pasted quoted values such as "RB2-..."
        if (
            len(cleaned) >= 2
            and cleaned[0] == cleaned[-1]
            and cleaned[0] in {"'", '"'}
        ):
            cleaned = cleaned[1:-1].strip()

        # Some UIs expose raw token value without the RB2- prefix.
        if not cleaned.startswith("RB2-") and len(cleaned) == 64:
            if all(char in "0123456789abcdefABCDEF" for char in cleaned):
                cleaned = f"RB2-{cleaned}"

        return cleaned

    @staticmethod
    def _token_type(token: str) -> str:
        if token.startswith("RB2-"):
            return "api"
        return "bearer"

    @staticmethod
    def _append_query_param(url: str, key: str, value: str) -> str:
        parsed = urlparse(url)
        query_pairs = dict(parse_qsl(parsed.query, keep_blank_values=True))
        query_pairs[key] = value
        updated_query = urlencode(query_pairs)
        return urlunparse(
            (
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                parsed.params,
                updated_query,
                parsed.fragment,
            )
        )

    def _candidate_paths(self, path: str) -> list[str]:
        normalized = path if path.startswith("/") else f"/{path}"
        if normalized.startswith("/api/"):
            return [normalized]
        return [normalized, f"/api{normalized}"]

    def _request_once(
        self,
        method: str,
        request_url: str,
        headers: Dict[str, str],
        body: Optional[bytes],
    ) -> ApiResponse:
        request = Request(
            request_url,
            data=body,
            headers=headers,
            method=method,
        )
        try:
            with urlopen(request, timeout=60) as response:
                raw = response.read().decode("utf-8")
                parsed = json.loads(raw) if raw else {}
                return ApiResponse(True, response.status, parsed)
        except HTTPError as error:
            raw = error.read().decode("utf-8") if hasattr(error, "read") else ""
            parsed = self._safe_json(raw)
            message = parsed.get("message") or parsed.get("error") or str(error)
            return ApiResponse(False, error.code, parsed, message)
        except URLError as error:
            return ApiResponse(False, 0, {}, f"Network error: {error}")
        except Exception as error:
            return ApiResponse(False, 0, {}, f"Request failed: {error}")
