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
DEFAULT_POLICY = '// the tailnet as it was\n{\n\t"acls": [{"action": "accept", "src": ["*"], "dst": ["*:*"]}],\n}\n'


class FakeTailscaleAPI:
    def __init__(self):
        self.policy = DEFAULT_POLICY
        self.version = 1
        self.devices = {NODE_ID: {"nodeId": NODE_ID, "id": "1001", "hostname": "hub",
                                  "name": "hub.tail1234.ts.net", "tags": []}}
        self.clients = {}  # id -> secret
        self.requests = []
        self.validate_message = None  # a string: the policy is refused with it
        self.keys_status = 200  # 403: this token may not create an OAuth client
        self.race = False  # the policy changes between the read and the write
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):  # pylint: disable=arguments-differ
                pass

            def do_GET(self):  # pylint: disable=invalid-name
                owner.handle(self, "GET")

            def do_POST(self):  # pylint: disable=invalid-name
                owner.handle(self, "POST")

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
        return [r for r in self.requests if r["method"] == "POST"
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
                return 200, {"access_token": OAUTH_ACCESS_TOKEN, "token_type": "Bearer"}, {}
            return 401, {"message": "invalid client credentials"}, {}
        if headers.get("Authorization") != f"Bearer {API_TOKEN}":
            return 401, {"message": "API token invalid"}, {}
        if (method, path) == ("POST", "/tailnet/-/acl/validate"):
            if self.validate_message:
                return 200, {"message": self.validate_message, "data": [{"user": "tag:ai-peer", "errors": ["x"]}]}, {}
            return 200, "", {}
        if (method, path) == ("GET", "/tailnet/-/acl"):
            answer = 200, self.policy, {"ETag": self.etag, "Content-Type": "application/hujson"}
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
        if path.startswith("/device/"):
            node, _, verb = path.removeprefix("/device/").partition("/")
            device = self.devices.get(node)
            if device is None:
                return 404, {"message": "device not found"}, {}
            if method == "GET" and not verb:
                return 200, device, {}
            if method == "POST" and verb == "tags":
                tags = json.loads(body)["tags"]
                if "tag:bridge" in tags and "tag:bridge" not in self.policy:
                    return 400, {"message": "requested tags [tag:bridge] are invalid or not permitted"}, {}
                device["tags"] = tags
                return 200, "", {}
        return 404, {"message": f"no route for {method} {path}"}, {}
