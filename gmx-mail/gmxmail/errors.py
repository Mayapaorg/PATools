"""Errors raised by the GMX client, CLI, and HTTP bridge."""


class GmxError(Exception):
    def __init__(self, message: str, code: str = "gmx") -> None:
        super().__init__(message)
        self.code = code


STATUS_FOR_CODE = {
    "bad_request": 400,
    "auth": 401,
    "not_found": 404,
    "unavailable": 503,
    "gmx": 502,
}
