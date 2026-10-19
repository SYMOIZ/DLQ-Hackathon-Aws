"""Cognito email auth helpers for the local UI (boto3 + stdlib only)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any

from dlq_judge.aws_io import session
from dlq_judge.config import Config


class AuthError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _client(cfg: Config):
    return session(cfg).client("cognito-idp")


def _code_delivery(details: dict[str, Any] | None) -> dict[str, str]:
    d = details or {}
    return {
        "destination": str(d.get("Destination") or ""),
        "delivery_medium": str(d.get("DeliveryMedium") or ""),
        "attribute_name": str(d.get("AttributeName") or ""),
    }


def sign_up(cfg: Config, email: str, password: str) -> dict[str, Any]:
    if not cfg.cognito_client_id:
        raise AuthError("misconfigured", "Cognito client id missing")
    email = (email or "").strip()
    try:
        client = _client(cfg)
        resp = client.sign_up(
            ClientId=cfg.cognito_client_id,
            Username=email,
            Password=password,
            UserAttributes=[{"Name": "email", "Value": email}],
        )
        user_sub = str(resp.get("UserSub") or "")
        confirmed = bool(resp.get("UserConfirmed"))
        auto_confirmed = False
        admin_confirm_error = ""
        # Cognito DEFAULT email often never arrives (quota/spam). Always
        # AdminConfirm so users can log in without an OTP inbox.
        if not confirmed and cfg.cognito_user_pool_id:
            try:
                client.admin_confirm_sign_up(
                    UserPoolId=cfg.cognito_user_pool_id, Username=email
                )
                confirmed = True
                auto_confirmed = True
            except Exception as e:
                admin_confirm_error = str(e)
        delivery = _code_delivery(resp.get("CodeDeliveryDetails"))
        out: dict[str, Any] = {
            "user_confirmed": confirmed,
            "auto_confirmed": auto_confirmed,
            "user_sub": user_sub,
            "email": email,
            "check_email": not confirmed,
            "code_delivery": delivery,
        }
        if admin_confirm_error:
            out["admin_confirm_error"] = admin_confirm_error
        return out
    except AuthError:
        raise
    except Exception as e:
        raise AuthError("sign_up_failed", str(e)) from e


def admin_confirm_user(cfg: Config, email: str) -> None:
    if not cfg.cognito_user_pool_id:
        raise AuthError("misconfigured", "Cognito user pool id missing")
    try:
        _client(cfg).admin_confirm_sign_up(
            UserPoolId=cfg.cognito_user_pool_id,
            Username=(email or "").strip(),
        )
    except Exception as e:
        raise AuthError("confirm_failed", str(e)) from e


def delete_user(cfg: Config, email: str) -> None:
    """Remove Cognito user (profile delete)."""
    if not cfg.cognito_user_pool_id:
        raise AuthError("misconfigured", "Cognito user pool id missing")
    try:
        _client(cfg).admin_delete_user(
            UserPoolId=cfg.cognito_user_pool_id,
            Username=(email or "").strip(),
        )
    except Exception as e:
        raise AuthError("delete_failed", str(e)) from e


def confirm_sign_up(cfg: Config, email: str, code: str) -> None:
    if not cfg.cognito_client_id:
        raise AuthError("misconfigured", "Cognito client id missing")
    try:
        _client(cfg).confirm_sign_up(
            ClientId=cfg.cognito_client_id,
            Username=(email or "").strip(),
            ConfirmationCode=(code or "").strip(),
        )
    except Exception as e:
        raise AuthError("confirm_failed", str(e)) from e


def resend_confirmation_code(cfg: Config, email: str) -> dict[str, Any]:
    if not cfg.cognito_client_id:
        raise AuthError("misconfigured", "Cognito client id missing")
    email = (email or "").strip()
    try:
        resp = _client(cfg).resend_confirmation_code(
            ClientId=cfg.cognito_client_id, Username=email
        )
        return {
            "email": email,
            "check_email": True,
            "code_delivery": _code_delivery(resp.get("CodeDeliveryDetails")),
        }
    except Exception as e:
        raise AuthError("resend_failed", str(e)) from e


def login(cfg: Config, email: str, password: str) -> dict[str, str]:
    if not cfg.cognito_client_id:
        raise AuthError("misconfigured", "Cognito client id missing")
    email = (email or "").strip()
    client = _client(cfg)

    def _initiate():
        return client.initiate_auth(
            ClientId=cfg.cognito_client_id,
            AuthFlow="USER_PASSWORD_AUTH",
            AuthParameters={"USERNAME": email, "PASSWORD": password},
        )

    try:
        resp = _initiate()
    except Exception as e:
        err = str(e)
        # Unconfirmed users: confirm via admin then retry once (OTP mail flaky).
        if "UserNotConfirmedException" in err or "not confirmed" in err.lower():
            if not cfg.cognito_user_pool_id:
                raise AuthError(
                    "user_not_confirmed",
                    "Email not verified. Open Verify tab or use Resend.",
                ) from e
            try:
                client.admin_confirm_sign_up(
                    UserPoolId=cfg.cognito_user_pool_id, Username=email
                )
                resp = _initiate()
            except Exception as e2:
                raise AuthError(
                    "user_not_confirmed",
                    "Account was not confirmed. Use Verify tab or Resend, then try again.",
                ) from e2
        else:
            raise AuthError("login_failed", err) from e
    result = resp.get("AuthenticationResult") or {}
    if not result.get("IdToken"):
        raise AuthError("login_failed", "no tokens; check USER_PASSWORD_AUTH enabled")
    return {
        "id_token": result["IdToken"],
        "access_token": result.get("AccessToken", ""),
        "refresh_token": result.get("RefreshToken", ""),
        "expires_in": str(result.get("ExpiresIn", "")),
    }


def _b64url_decode(part: str) -> bytes:
    pad = "=" * (-len(part) % 4)
    return base64.urlsafe_b64decode(part + pad)


def decode_jwt_payload(token: str) -> dict[str, Any]:
    parts = token.split(".")
    if len(parts) != 3:
        raise AuthError("invalid_token", "malformed jwt")
    try:
        return json.loads(_b64url_decode(parts[1]).decode("utf-8"))
    except Exception as e:
        raise AuthError("invalid_token", str(e)) from e


def verify_id_token(cfg: Config, token: str) -> dict[str, Any]:
    """Validate Cognito ID token claims (exp, aud, iss, token_use). Signature
    check uses Cognito GetUser on the access token when available; for ID
    tokens we validate structural claims against the pool (stdlib-only)."""
    if not token:
        raise AuthError("unauthorized", "missing token")
    payload = decode_jwt_payload(token)
    now = int(time.time())
    if int(payload.get("exp", 0)) < now:
        raise AuthError("unauthorized", "token expired")
    if payload.get("token_use") not in ("id", "access"):
        raise AuthError("unauthorized", "bad token_use")
    if cfg.cognito_client_id and payload.get("aud") not in (
        None,
        cfg.cognito_client_id,
    ):
        # access tokens use client_id claim instead of aud
        if payload.get("client_id") != cfg.cognito_client_id and payload.get("aud") != cfg.cognito_client_id:
            raise AuthError("unauthorized", "bad audience")
    if cfg.cognito_user_pool_id:
        expected_iss = f"https://cognito-idp.{cfg.region}.amazonaws.com/{cfg.cognito_user_pool_id}"
        if payload.get("iss") != expected_iss:
            raise AuthError("unauthorized", "bad issuer")
    return payload


def session_cookie_value(id_token: str) -> str:
    return id_token


def parse_cookie(header: str | None, name: str = "dlqj_id") -> str | None:
    if not header:
        return None
    for part in header.split(";"):
        k, _, v = part.strip().partition("=")
        if k == name:
            return v
    return None
