"""A Tailscale API on a loopback port, for `deploy tailnet-setup`: nothing leaves this machine.

Serves the calls the command makes, with the answers https://tailscale.com/api
documents: policy validate / read / replace (ETag and If-Match), device read and
tags, the device list, key creation (keyType client) and the OAuth token exchange.
Every request is kept in .requests; the knobs are plain attributes a test sets.
"""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

API_TOKEN = "tskey-api-kADMIN123CNTRL-ApiAccessTokenThatMustNotLeak01"
CLIENT_ID = "kCLIENT11CNTRL"
CLIENT_SECRET = "tskey-client-kCLIENT11CNTRL-OAuthSecretThatMustNotLeak0123"
OAUTH_ACCESS_TOKEN = "tskey-api-kOAUTH-AccessTokenFromTheExchange0123456789"
NODE_ID = "nFAKENODE11CNTRL"
AUTH_KEY_MINTED = "tskey-auth-kMINTED1CNTRL-JoinKeyThatMustNotLeak0123456789"
DEFAULT_POLICY = '// the tailnet as it was\n{\n\t"acls": [{"action": "accept", "src": ["*"], "dst": ["*:*"]}],\n}\n'


def device(node_id: str, hostname: str, ip: str, tags: list | None = None, *, expiry_disabled: bool = False,
           last_seen: str = "2026-10-11T23:00:00Z") -> dict:
    """A device as GET /tailnet/-/devices lists it."""
    return {"nodeId": node_id, "id": node_id.removeprefix("n")[:8], "hostname": hostname,
            "name": f"{hostname}.tail1234.ts.net", "addresses": [ip, "fd7a:115c:a1e0::1"], "tags": list(tags or []),
            "keyExpiryDisabled": expiry_disabled, "expires": "" if expiry_disabled else "2027-04-09T23:00:00Z",
            "lastSeen": last_seen, "authorized": True, "os": "linux"}


class FakeTailscaleAPI:
    def __init__(self):
        self.policy = DEFAULT_POLICY
        self.version = 1
        # Only fields the API's default field set has (DeviceDefaultFields): there is no "ephemeral" one
        self.devices = {NODE_ID: device(NODE_ID, "hub", "100.64.0.1")}
        self.clients = {}  # id -> secret
        self.requests = []
        self.validate_message = None  # a string: the policy is refused with it
        self.keys_status = 200  # 403: this token may not create an OAuth client
        self.race = False  # the policy changes between the read and the write
        self.send_etag = True  # False: the policy is served without an ETag
        self.validate_raw = None  # a string: the validation answers 200 with exactly this body
        self.issued = set()  # OAuth access tokens handed out by the exchange
        self.auth_keys = []  # the device-create capabilities of every auth key minted
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):  # pylint: disable=arguments-differ
                pass

            def do_GET(self):  # pylint: disable=invalid-name
                owner.handle(self, "GET")

            def do_POST(self):  # pylint: disable=invalid-name
                owner.handle(self, "POST")

            def do_DELETE(self):  # pylint: disable=invalid-name
                owner.handle(self, "DELETE")

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}/api/v2"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(10)

    @property
    def etag(self) -> str:
        return f'"v{self.version}"'

    def made(self, method: str, suffix: str) -> list[dict]:
        return [r for r in self.requests if r["method"] == method and r["path"].endswith(suffix)]

    def writes(self) -> list[dict]:
        """Every request that changed the tailnet (validate and the token exchange change nothing)."""
        return [r for r in self.requests if r["method"] in ("POST", "DELETE")
                and not r["path"].endswith(("/acl/validate", "/oauth/token"))]

    def handle(self, req, method: str) -> None:
        body = req.rfile.read(int(req.headers.get("Content-Length") or 0)).decode("utf-8")
        path = req.path.split("?")[0].removeprefix("/api/v2")
        self.requests.append({"method": method, "path": path, "body": body,
                              "authorization": req.headers.get("Authorization", ""),
                              "content_type": req.headers.get("Content-Type", ""),
                              "if_match": req.headers.get("If-Match")})
        status, payload, headers = self.answer(method, path, body, req.headers)
        raw = payload.encode("utf-8") if isinstance(payload, str) else json.dumps(payload).encode("utf-8")
        if payload == "":
            raw = b""
        req.send_response(status)
        for key, value in headers.items():
            req.send_header(key, value)
        req.send_header("Content-Length", str(len(raw)))
        req.end_headers()
        req.wfile.write(raw)

    def answer(self, method: str, path: str, body: str, headers) -> tuple[int, object, dict]:
        if (method, path) == ("POST", "/oauth/token"):
            form = parse_qs(body)
            cid, secret = form.get("client_id", [""])[0], form.get("client_secret", [""])[0]
            if self.clients.get(cid) == secret and secret:
                self.issued.add(OAUTH_ACCESS_TOKEN)
                return 200, {"access_token": OAUTH_ACCESS_TOKEN, "token_type": "Bearer"}, {}
            return 401, {"message": "invalid client credentials"}, {}
        bearer = headers.get("Authorization")
        oauth = bearer == f"Bearer {OAUTH_ACCESS_TOKEN}" and OAUTH_ACCESS_TOKEN in self.issued
        if bearer != f"Bearer {API_TOKEN}" and not oauth:
            return 401, {"message": "API token invalid"}, {}
        if oauth and "/acl" in path:  # the OAuth client has auth_keys and devices:core, not policy_file
            return 403, {"message": "calling actor does not have enough permissions"}, {}
        if (method, path) == ("POST", "/tailnet/-/keys") and oauth:
            create = json.loads(body).get("capabilities", {}).get("devices", {}).get("create", {})
            self.auth_keys.append(create)
            return 200, {"id": f"kAUTH{len(self.auth_keys)}", "key": AUTH_KEY_MINTED,
                         "expires": "2026-10-12T00:00:00Z"}, {}
        if (method, path) == ("POST", "/tailnet/-/acl/validate"):
            if self.validate_raw is not None:
                return 200, self.validate_raw, {"Content-Type": "text/html"}
            if self.validate_message:
                return 200, {"message": self.validate_message, "data": [{"user": "tag:ai-peer", "errors": ["x"]}]}, {}
            return 200, "", {}
        if (method, path) == ("GET", "/tailnet/-/acl"):
            answer = 200, self.policy, {"Content-Type": "application/hujson",
                                        **({"ETag": self.etag} if self.send_etag else {})}
            if self.race:
                self.version += 1
            return answer
        if (method, path) == ("POST", "/tailnet/-/acl"):
            if headers.get("If-Match") != self.etag:
                return 412, {"message": "precondition failed, invalid old hash"}, {}
            self.policy, self.version = body, self.version + 1
            return 200, body, {"ETag": self.etag}
        if (method, path) == ("GET", "/tailnet/-/devices"):
            return 200, {"devices": list(self.devices.values())}, {}
        if (method, path) == ("POST", "/tailnet/-/keys"):
            if self.keys_status != 200:
                return self.keys_status, {"message": "calling actor does not have enough permissions"}, {}
            self.clients[CLIENT_ID] = CLIENT_SECRET
            return 200, {"id": CLIENT_ID, "key": CLIENT_SECRET, "keyType": "client"}, {}
        if method == "DELETE" and path.startswith("/tailnet/-/keys/"):
            known = self.clients.pop(path.rsplit("/", 1)[-1], None)
            return (200, "", {}) if known else (404, {"message": "no key"}, {})
        if path.startswith("/device/"):
            node, _, verb = path.removeprefix("/device/").partition("/")
            device = self.devices.get(node)
            if device is None:
                return 404, {"message": "device not found"}, {}
            if method == "GET" and not verb:
                return 200, device, {}
            if method == "DELETE" and not verb:
                del self.devices[node]
                return 200, "", {}
            if method == "POST" and verb == "key":
                device["keyExpiryDisabled"] = bool(json.loads(body).get("keyExpiryDisabled"))
                return 200, "", {}
            if method == "POST" and verb == "tags":
                tags = json.loads(body)["tags"]
                if "tag:bridge" in tags and "tag:bridge" not in self.policy:
                    return 400, {"message": "requested tags [tag:bridge] are invalid or not permitted"}, {}
                device["tags"] = tags
                return 200, "", {}
        return 404, {"message": f"no route for {method} {path}"}, {}
