"""``mcp-graph-admin-doctor`` - proves auth actually works, not just that the
command resolves on PATH.
"""

from __future__ import annotations

import base64
import json
import os
import sys

from mcp_ms_core import GraphError

from .client import ALLOW_WRITES_ENV, build_auth, get_client


def _decode_jwt_claims(token: str) -> dict:
    try:
        payload_b64 = token.split(".")[1]
        padded = payload_b64 + "=" * (-len(payload_b64) % 4)
        return json.loads(base64.urlsafe_b64decode(padded))
    except Exception:  # noqa: BLE001 - best-effort display only
        return {}


def main() -> int:
    try:
        auth = build_auth()
        token = auth.get_token()
    except Exception as exc:  # noqa: BLE001 - report, don't traceback, for a CLI tool
        print(f"AUTH FAILED: {exc}", file=sys.stderr)
        return 1

    claims = _decode_jwt_claims(token)
    print("mcp-graph-admin doctor")
    print(f"  tenant (from env): {auth.tenant_id}")
    print(f"  tenant (from token, tid claim): {claims.get('tid', '<not present>')}")
    print(f"  app id (appid/azp claim): {claims.get('appid') or claims.get('azp', '<not present>')}")
    print(f"  app display name: {claims.get('app_displayname', '<not present>')}")
    print(f"  app roles granted: {claims.get('roles', [])}")
    writes_on = os.environ.get(ALLOW_WRITES_ENV, "").strip().lower() in ("1", "true", "yes")
    print(f"  write tools enabled ({ALLOW_WRITES_ENV}): {'yes' if writes_on else 'no'}")

    print("  probing organization ...")
    try:
        result = get_client().get("organization")
        names = [org.get("displayName") for org in result.get("value", [])]
        print(f"  OK - read call succeeded. Tenant display name(s): {names}")
    except GraphError as exc:
        print(f"  READ FAILED: {exc}", file=sys.stderr)
        print(
            "  A valid token but a failed read usually means the app registration "
            "is missing Organization.Read.All (or broader) with admin consent granted.",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
