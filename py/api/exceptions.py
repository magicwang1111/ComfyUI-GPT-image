class GPTImageAPIError(Exception):
    def __init__(self, status_code, error_type, message, param=None, code=None, response_body=None):
        self.status_code = status_code
        self.error_type = error_type
        self.message = message or "Unknown API error"
        self.param = param
        self.code = code
        self.response_body = response_body
        super().__init__(self._format_message())

    def _format_message(self):
        type_label = f" {self.error_type}" if self.error_type else ""
        return f"API request failed ({self.status_code}{type_label}): {self.message}"

    @classmethod
    def from_response(cls, response):
        try:
            payload = response.json()
        except Exception:
            payload = {}

        error_payload = payload.get("error", {}) if isinstance(payload, dict) else {}
        return cls(
            status_code=response.status_code,
            error_type=error_payload.get("type"),
            message=error_payload.get("message") or response.text,
            param=error_payload.get("param"),
            code=error_payload.get("code"),
            response_body=payload,
        )
