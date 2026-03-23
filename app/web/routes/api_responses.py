from __future__ import annotations

from flask import jsonify


def ok(data=None, message: str | None = None, status_code: int = 200):
    payload = {"ok": True}
    if message is not None:
        payload["message"] = message
    if data is not None:
        payload["data"] = data
    return jsonify(payload), status_code


def error(message: str, status_code: int = 400, code: str | None = None, data=None):
    payload = {"ok": False, "message": message}
    if code is not None:
        payload["code"] = code
    if data is not None:
        payload["data"] = data
    return jsonify(payload), status_code

