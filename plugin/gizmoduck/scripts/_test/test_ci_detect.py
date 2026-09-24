"""ci_detect.py - endpoint and staging-URL autodetection, the Decision-needed
blocks setup prints, the owner-confirmed setup writes, and the per-run merge.

Every repository here is written into tmp_path by the test that uses it, so
the fixtures are next to their assertions and no dot-directory (`.crew`,
`.github`, `.env.example`) is committed inside the plugin. Nothing contacts a
network: the one live-OpenAPI path uses a fake fetcher.
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import ci_detect as cd
import gizmoduck_ci as ci
import pytest

_CLI = Path(__file__).resolve().parent.parent / "gizmoduck_ci.py"


def make_repo(root, files):
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
    return root


def endpoints(det, detector=None):
    """{(method, path): finding} for one detector."""
    return {(f.method, f.value): f for f in det.of("endpoint") if detector in (None, f.detector)}


def line_of(root, rel, needle):
    for n, line in enumerate((root / rel).read_text(encoding="utf-8").splitlines(), 1):
        if needle in line:
            return n
    raise AssertionError(f"{needle!r} not in {rel}")


# --- fixtures ------------------------------------------------------------------

CONTROLLER = """\
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace Acme.Api.Controllers;

[ApiController]
[Route("api/[controller]")]
[Authorize]
public class UsersController : ControllerBase
{
    public UsersController(IUserService users) { }

    [HttpGet]
    public IActionResult List() => Ok();

    [HttpGet("{id:int}")]
    public IActionResult Get(int id) => Ok();

    [HttpPost]
    public IActionResult Create(UserDto dto) => Ok();

    [AllowAnonymous]
    [HttpGet("public")]
    public IActionResult Public() => Ok();

    [HttpGet("/health")]
    public IActionResult Health() => Ok();
}
"""

PROGRAM = """\
var builder = WebApplication.CreateBuilder(args);
builder.Services.AddSwaggerGen();
builder.Services.AddOpenApi();
builder.Services.AddAuthentication().AddJwtBearer();
var app = builder.Build();
app.MapOpenApi();
var api = app.MapGroup("/api/v2").RequireAuthorization();
api.MapGet("/orders", () => Results.Ok());
app.MapPost("/login", (Login l) => Results.Ok());
app.MapGet("/status", () => "ok")
   .RequireAuthorization();
app.Run();
"""

ANGULAR_ROOT = """\
import { Routes } from '@angular/router';
import { authGuard } from './auth.guard';

export const routes: Routes = [
  { path: '', component: HomeComponent },
  { path: 'login', component: LoginComponent },
  { path: 'old', redirectTo: 'login' },
  {
    path: 'admin',
    canActivate: [authGuard],
    children: [
      { path: 'users', component: UsersComponent },
      { path: 'users/:id', component: UserComponent },
    ],
  },
  { path: '**', component: NotFoundComponent },
];
"""

ANGULAR_CHILD = """\
import { Routes } from '@angular/router';

export const REPORT_ROUTES: Routes = [
  { path: 'monthly', component: MonthlyComponent },
];
"""

FASTAPI_MAIN = """\
from fastapi import APIRouter, Depends, FastAPI

app = FastAPI(title="acme")
router = APIRouter(
    prefix="/items",
    tags=["items"],
)


@router.get("/{item_id}")
async def read_item(item_id: int, user=Depends(get_current_user)):
    return {}


@app.get("/health")
def health():
    return "ok"


app.include_router(router, prefix="/api")
"""

FASTAPI_USERS = """\
from fastapi import APIRouter

router = APIRouter()


@router.post("/users")
def create_user():
    return {}
"""

FLASK_APP = """\
from flask import Blueprint, Flask
from flask_login import login_required

app = Flask(__name__)
bp = Blueprint("admin", __name__, url_prefix="/admin")


@bp.route("/panel", methods=["GET", "POST"])
@login_required
def panel():
    return "x"


@app.route("/")
def index():
    return "hi"


app.register_blueprint(bp)
"""

EXPRESS = """\
const express = require('express');
const http = require('./client');
const app = express();
const router = express.Router();

router.get('/users/:id', requireAuth, (req, res) => res.json({}));
app.post('/login', (req, res) => res.send('ok'));
app.get('env');
http.get('/not-a-route');
app.use('/api', router);
"""

OPENAPI_YAML = """\
openapi: 3.0.3
info: {title: acme, version: '1'}
servers:
  - url: https://staging.acme.test/v1
security:
  - bearer: []
paths:
  /pets:
    get:
      summary: list
    post:
      summary: create
      security: []
"""

OBJ_OPENAPI = json.dumps({"openapi": "3.0.1", "info": {"title": "Api", "version": "v1"},
                          "paths": {"/weather": {"get": {}}}}, indent=2)


# --- 3a. ASP.NET ----------------------------------------------------------------

def test_aspnet_controller_routes_with_class_prefix_tokens_and_auth(tmp_path):
    root = make_repo(tmp_path, {"src/Api/Controllers/UsersController.cs": CONTROLLER})
    got = endpoints(cd.detect(str(root)), "aspnet-controller")
    rel = "src/Api/Controllers/UsersController.cs"
    assert set(got) == {("GET", "/api/Users"), ("GET", "/api/Users/{id}"), ("POST", "/api/Users"),
                        ("GET", "/api/Users/public"), ("GET", "/health")}
    assert got[("GET", "/api/Users")].protected and got[("POST", "/api/Users")].protected
    assert not got[("GET", "/api/Users/public")].protected
    assert all(f.confidence == cd.HIGH for f in got.values())
    assert got[("GET", "/api/Users/{id}")].source == f"{rel}:{line_of(root, rel, 'Get(int id)')}"


def test_aspnet_minimal_api_groups_auth_and_openapi_routes(tmp_path):
    root = make_repo(tmp_path, {"src/Api/Program.cs": PROGRAM})
    det = cd.detect(str(root))
    got = endpoints(det, "aspnet-minimal-api")
    assert set(got) == {("GET", "/api/v2/orders"), ("POST", "/login"), ("GET", "/status")}
    assert got[("GET", "/api/v2/orders")].protected and got[("GET", "/status")].protected
    assert not got[("POST", "/login")].protected
    assert all(f.confidence == cd.HIGH for f in got.values())
    live = {f.value: f for f in det.of("openapi_url")}
    assert set(live) == {"/swagger/v1/swagger.json", "/openapi/v1.json"}
    assert all(f.confidence == cd.MEDIUM for f in live.values())
    assert det.of("auth")


def test_minimal_api_on_an_unknown_receiver_is_medium(tmp_path):
    root = make_repo(tmp_path, {"Ext.cs": 'static class E { static void M(RouteGroupBuilder g) '
                                          '{ g.MapGet("/x", () => 1); } }\n'})
    (f,) = cd.detect(str(root)).of("endpoint")
    assert (f.value, f.confidence) == ("/x", cd.MEDIUM) and "prefix may be missing" in f.note


# --- 3b. Angular ----------------------------------------------------------------

def test_angular_root_routes_children_guards_and_skips(tmp_path):
    root = make_repo(tmp_path, {"web/src/app/app.routes.ts": ANGULAR_ROOT,
                                "web/src/app/reports/report.routes.ts": ANGULAR_CHILD})
    got = {f.value: f for f in cd.detect(str(root)).of("endpoint")}
    assert set(got) == {"/", "/login", "/admin", "/admin/users", "/admin/users/{id}", "/monthly"}
    assert got["/admin"].protected and got["/admin/users/{id}"].protected and not got["/login"].protected
    assert got["/login"].confidence == cd.MEDIUM
    assert got["/monthly"].confidence == cd.LOW, "a child config's parent prefix is unknown"


# --- 3c. FastAPI / Flask / Express ---------------------------------------------

def test_fastapi_router_prefix_mount_and_dependency_auth(tmp_path):
    root = make_repo(tmp_path, {"app/main.py": FASTAPI_MAIN, "app/users.py": FASTAPI_USERS})
    det = cd.detect(str(root))
    got = endpoints(det, "fastapi")
    assert got[("GET", "/api/items/{item_id}")].confidence == cd.HIGH
    assert got[("GET", "/api/items/{item_id}")].protected
    assert got[("GET", "/health")].confidence == cd.HIGH and not got[("GET", "/health")].protected
    assert got[("POST", "/users")].confidence == cd.MEDIUM, "router mounted in another file"
    assert [f.value for f in det.of("openapi_url")] == ["/openapi.json"]


def test_flask_blueprint_registered_in_file_is_high(tmp_path):
    root = make_repo(tmp_path, {"app.py": FLASK_APP})
    got = endpoints(cd.detect(str(root)), "flask")
    assert set(got) == {("GET", "/admin/panel"), ("POST", "/admin/panel"), ("GET", "/")}
    assert got[("POST", "/admin/panel")].protected and not got[("GET", "/")].protected
    assert all(f.confidence == cd.HIGH for f in got.values())


def test_express_routes_mounts_and_middleware_auth(tmp_path):
    root = make_repo(tmp_path, {"server.js": EXPRESS})
    got = endpoints(cd.detect(str(root)), "express")
    assert set(got) == {("GET", "/api/users/{id}"), ("POST", "/login")}
    assert got[("GET", "/api/users/{id}")].protected and got[("GET", "/api/users/{id}")].confidence == cd.HIGH
    assert got[("GET", "/api/users/{id}")].source == f"server.js:{line_of(root, 'server.js', 'router.get')}"


# --- 2. OpenAPI documents --------------------------------------------------------

def test_openapi_yaml_and_build_output_json_in_obj(tmp_path):
    root = make_repo(tmp_path, {"docs/openapi.yaml": OPENAPI_YAML, "src/Api/obj/Api.json": OBJ_OPENAPI,
                                "src/Api/obj/project.assets.json": '{"version": 3}'})
    det = cd.detect(str(root))
    got = endpoints(det, "openapi")
    assert set(got) == {("GET", "/v1/pets"), ("POST", "/v1/pets"), ("GET", "/weather")}
    assert got[("GET", "/v1/pets")].protected and not got[("POST", "/v1/pets")].protected
    assert all(f.confidence == cd.HIGH for f in got.values())
    assert got[("GET", "/weather")].source.startswith("src/Api/obj/Api.json:")
    assert [(f.value, f.confidence) for f in det.of("staging_url")] == [("https://staging.acme.test/v1", cd.MEDIUM)]


# --- 1. crew ledger ------------------------------------------------------------------

def test_crew_ledger_declared_is_high_and_closed_is_skipped(tmp_path):
    ledger = {"nextSeq": 3, "records": [
        {"id": "ep-0001", "endpoint": "/api/orders", "source": "declared", "status": "open"},
        {"id": "ep-0002", "endpoint": "/api/old", "source": "declared", "status": "closed"},
        {"id": "ep-0003", "endpoint": "the new orders API", "source": "declared", "status": "open"}]}
    root = make_repo(tmp_path, {".crew/endpoints.json": json.dumps(ledger, indent=2)})
    det = cd.detect(str(root))
    assert det.crew_present
    assert [(f.value, f.confidence, f.detector) for f in det.of("endpoint")] == \
        [("/api/orders", cd.HIGH, "crew-ledger")]


# --- 4. staging URL sources -----------------------------------------------------------

def test_staging_url_sources_and_their_confidence(tmp_path):
    root = make_repo(tmp_path, {
        "src/Api/appsettings.Staging.json": '{\n  "PublicBaseUrl": "https://api.staging.acme.test"\n}\n',
        "src/Api/appsettings.json": '{\n  "PublicBaseUrl": "https://api.acme.test"\n}\n',
        "web/src/environments/environment.staging.ts": "export const environment = "
                                                        "{ apiUrl: 'https://web.staging.acme.test/api' };\n",
        "infra/envs/staging/outputs.tf": 'output "staging_url" {\n  value = "https://app.staging.acme.test"\n}\n'
                                         'output "api_endpoint" {\n  value = aws_lb.api.dns_name\n}\n',
        ".env.example": "STAGING_BASE_URL=https://env.staging.acme.test\nAPI_URL=https://api.example.com\n"
                        "LOCAL_URL=http://localhost:8080\n",
        ".env": "STAGING_BASE_URL=https://secret.staging.acme.test\n",
        ".github/workflows/deploy.yml": "on: push\njobs:\n  deploy:\n    runs-on: ubuntu-24.04\n"
                                        "    environment:\n      name: staging\n"
                                        "      url: https://gh.staging.acme.test\n    steps: [{run: echo}]\n"
                                        "  eu:\n    runs-on: ubuntu-24.04\n    environment:\n"
                                        "      name: staging-eu\n      url: ${{ steps.d.outputs.url }}\n"
                                        "    steps: [{run: echo}]\n",
        "bitbucket-pipelines.yml": "pipelines:\n  branches:\n    main:\n      - step:\n          deployment: staging\n"
                                   "          script:\n            - curl -f https://bb.staging.acme.test/health\n"
                                   "      - step:\n          deployment: Staging-West\n          script:\n"
                                   "            - ./deploy.sh\n",
    })
    got = {(f.detector, f.value): f for f in cd.detect(str(root)).of("staging_url")}
    assert got[("appsettings", "https://api.staging.acme.test")].confidence == cd.MEDIUM
    assert got[("appsettings", "https://api.staging.acme.test")].source == "src/Api/appsettings.Staging.json:2"
    assert got[("angular-environment", "https://web.staging.acme.test/api")].confidence == cd.MEDIUM
    assert got[("terraform-output", "https://app.staging.acme.test")].confidence == cd.MEDIUM
    assert got[("terraform-output", "")].confidence == cd.LOW
    assert "aws_lb.api.dns_name" in got[("terraform-output", "")].note
    assert got[("env-template", "https://env.staging.acme.test")].confidence == cd.MEDIUM
    assert got[("github-environment", "https://gh.staging.acme.test")].confidence == cd.MEDIUM
    assert got[("github-environment", "")].confidence == cd.LOW
    assert got[("bitbucket-deployment", "https://bb.staging.acme.test/health")].confidence == cd.MEDIUM
    assert "Repository settings -> Deployments" in got[("bitbucket-deployment", "")].note
    values = {v for _, v in got}
    assert "https://api.acme.test" not in values, "a non-staging URL in a non-staging file is not a candidate"
    assert "https://secret.staging.acme.test" not in values, "a real .env is never read"
    assert not any("localhost" in v or "example.com" in v for v in values)


# --- nothing found ----------------------------------------------------------------------

def test_nothing_found_is_unverified_never_pass(tmp_path):
    root = make_repo(tmp_path, {"README.md": "# nothing here\n"})
    det = cd.detect(str(root))
    assert det.of("endpoint") == []
    assert "**UNVERIFIED:**" in cd.render_findings(det)
    run = cd.merge_for_run(None, None, det)
    assert run["status"] == "UNVERIFIED" and cd.DETECT_HINT in run["reason"]


def test_endpoints_cli_fails_on_an_empty_repo(tmp_path):
    root = make_repo(tmp_path / "repo", {"README.md": "x\n"})
    p = subprocess.run([sys.executable, str(_CLI), "endpoints", "--repo", str(root), "--out", str(tmp_path / "o"),
                        "--no-live"], capture_output=True, text=True, check=False)
    assert p.returncode == 2
    assert "GIZMODUCK_ENDPOINTS_UNVERIFIED" in p.stderr and "run /gizmoduck:ci --detect" in p.stderr
    assert json.loads((tmp_path / "o" / "endpoints-run.json").read_text())["status"] == "UNVERIFIED"
    assert "UNVERIFIED" in (tmp_path / "o" / "endpoints-run.md").read_text()


# --- Decision needed ------------------------------------------------------------------

_URL = re.compile(r"https?://")


def _shape_ok(block):
    lines = block.splitlines()
    assert lines[0].startswith("**Decision needed:** ")
    opts = [ln for ln in lines if re.match(r"^\d\. ", ln)]
    assert 2 <= len(opts) <= 4, block
    assert "(Recommended)" in opts[0] and all("(Recommended)" not in o for o in opts[1:])
    assert all(" - " in o for o in opts), "every option states its cost"
    assert any(ln.startswith("**What I already checked:** ") for ln in lines)
    assert any(ln.startswith("**What I could not settle:** ") for ln in lines)
    assert not any("other" in o.lower().split(" - ")[0] for o in opts)


def test_unknown_staging_url_asks_and_never_guesses(tmp_path):
    root = make_repo(tmp_path, {"server.js": EXPRESS})
    decs = {d.key: d for d in cd.decisions(cd.detect(str(root)))}
    block = decs["staging_url"].render()
    _shape_ok(block)
    assert not _URL.search(block), "no URL may appear when none was found"
    assert "I will not guess" in block


def test_staging_candidates_are_offered_highest_confidence_first(tmp_path):
    root = make_repo(tmp_path, {
        "appsettings.Staging.json": '{"Url": "https://a.staging.acme.test"}\n',
        "appsettings.json": '{"Url": "https://b.staging.acme.test"}\n'})
    block = {d.key: d for d in cd.decisions(cd.detect(str(root)))}["staging_url"].render()
    _shape_ok(block)
    first = [ln for ln in block.splitlines() if ln.startswith("1. ")][0]
    assert "https://a.staging.acme.test" in first


def test_every_decision_block_has_the_pm_shape_and_settled_ones_are_not_asked(tmp_path):
    root = make_repo(tmp_path, {"src/Api/Program.cs": PROGRAM})
    det = cd.detect(str(root))
    decs = cd.decisions(det)
    assert {d.key for d in decs} == {"staging_url", "auth", "scope", "accept", "openapi"}
    for d in decs:
        _shape_ok(d.render())
    cfg, _ = cd.build_config(det, "https://s.acme.test", "none", "medium", scope_all=True, openapi_path="none")
    assert cd.decisions(det, cfg) == [], "an answered question - 'none' included - is not asked again"
    del cfg["staging"]["openapi_path"]
    assert [d.key for d in cd.decisions(det, cfg)] == ["openapi"]


# --- setup: owner-confirmed writes only ----------------------------------------------------

def setup(root, *extra):
    return subprocess.run([sys.executable, str(_CLI), "setup", "--repo", str(root), *extra],
                          capture_output=True, text=True, check=False)


def snapshot(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def test_detect_writes_nothing(tmp_path):
    root = make_repo(tmp_path, {"server.js": EXPRESS, ".crew/endpoints.json": '{"records": [], "nextSeq": 0}\n'})
    before = snapshot(root)
    p = subprocess.run([sys.executable, str(_CLI), "detect", "--repo", str(root)], capture_output=True, text=True,
                       check=False)
    assert p.returncode == 0 and "**Decision needed:**" in p.stdout
    assert snapshot(root) == before


@pytest.mark.parametrize("extra,needle", [
    (["--auth", "none", "--accept", "medium", "--scope", "all"], "--staging-url is required"),
    (["--staging-url", "none", "--accept", "medium", "--scope", "all"], "--auth must be one of"),
    (["--staging-url", "none", "--auth", "none", "--scope", "all"], "--accept must be"),
    (["--staging-url", "none", "--auth", "none", "--accept", "high"], "scope is not decided"),
    (["--staging-url", "staging.acme.test", "--auth", "none", "--accept", "high", "--scope", "all"],
     "not an http(s) URL"),
])
def test_setup_refuses_an_undecided_question(tmp_path, extra, needle):
    root = make_repo(tmp_path, {"server.js": EXPRESS})
    before = snapshot(root)
    p = setup(root, *extra, "--apply")
    assert p.returncode == 2 and needle in p.stderr, p.stderr
    assert snapshot(root) == before


def test_setup_dry_run_then_apply_is_deterministic(tmp_path):
    root = make_repo(tmp_path, {"server.js": EXPRESS, "app/main.py": FASTAPI_MAIN})
    args = ["--staging-url", "https://staging.acme.test", "--auth", "exclude-protected", "--accept", "high",
            "--exclude", "*health*"]
    before = snapshot(root)
    assert setup(root, *args).returncode == 0 and snapshot(root) == before
    assert setup(root, *args, "--apply").returncode == 0
    first = (root / "gizmoduck-ci.json").read_bytes()
    assert setup(root, *args, "--apply").returncode == 0
    assert (root / "gizmoduck-ci.json").read_bytes() == first, "a pure function of the repo and the answers"
    cfg = json.loads(first)
    assert cfg["staging"]["base_url"] == "https://staging.acme.test"
    assert cfg["endpoints_store"] == "gizmoduck-ci.json"
    assert [e["path"] for e in cfg["endpoints"]] == ["/api/items/{item_id}", "/api/users/{id}", "/health",
                                                      "/login"]
    assert b"\r" not in first and not re.search(rb"20\d\d-\d\d-\d\d", first)


def test_setup_with_crew_appends_declared_records_only_on_apply(tmp_path):
    ledger = {"records": [{"id": "ep-0004", "endpoint": "/login", "source": "declared", "status": "open",
                           "location": "x", "ticket": None, "createdAt": "2026-01-01T00:00:00Z"}], "nextSeq": 4}
    root = make_repo(tmp_path, {"server.js": EXPRESS, ".crew/endpoints.json": json.dumps(ledger)})
    args = ["--staging-url", "none", "--auth", "none", "--accept", "high", "--scope", "all"]
    p = setup(root, *args)
    assert p.returncode == 0 and "+ /api/users/{id}" in p.stdout and "+ /login" not in p.stdout
    assert json.loads((root / ".crew/endpoints.json").read_text()) == ledger, "dry run wrote the ledger"
    assert setup(root, *args, "--apply").returncode == 0
    doc = json.loads((root / ".crew/endpoints.json").read_text())
    assert doc["nextSeq"] == 5
    assert doc["records"][1] == {"id": "ep-0005", "endpoint": "/api/users/{id}", "source": "declared",
                                 "status": "open", "location": "server.js:6", "ticket": None,
                                 "createdAt": doc["records"][1]["createdAt"]}
    cfg = json.loads((root / "gizmoduck-ci.json").read_text())
    assert cfg["endpoints_store"] == ".crew/endpoints.json" and cfg["endpoints"] == []
    assert not (root / ".crew/endpoints.json.lock").exists()


# --- per-run merge ------------------------------------------------------------------------

def _cfg(**over):
    base = {"schema": cd.CONFIG_SCHEMA, "staging": {"base_url": "https://staging.acme.test", "openapi_path": None},
            "auth": {"mode": "none"}, "scope": {"include": [], "exclude": []}, "accept": "high",
            "endpoints_store": "gizmoduck-ci.json",
            "endpoints": [{"path": "/login", "methods": ["POST"], "confidence": "high", "source": "server.js:7",
                           "protected": False}]}
    base.update(over)
    return base


def test_new_endpoints_are_scanned_and_reported(tmp_path):
    root = make_repo(tmp_path, {"server.js": EXPRESS})
    run = cd.merge_for_run(_cfg(), None, cd.detect(str(root)), [("GET", "/v2/live", False)])
    by = {e["path"]: e for e in run["endpoints"]}
    assert run["status"] == "OK"
    assert not by["/login"]["new"]
    assert by["/api/users/{id}"]["new"] and by["/api/users/{id}"]["endpoint"] == "/api/users"
    assert by["/v2/live"]["new"] and by["/v2/live"]["origins"] == ["live-openapi"]
    report = cd.render_run_report(run)
    assert "`GET /api/users/{id}`" in report and report.count("new, confirm at next setup") >= 2


def test_scope_and_exclude_protected_filter_and_can_empty_the_run(tmp_path):
    root = make_repo(tmp_path, {"server.js": EXPRESS})
    det = cd.detect(str(root))
    run = cd.merge_for_run(_cfg(auth={"mode": "exclude-protected"}), None, det)
    assert [e["path"] for e in run["endpoints"]] == ["/login"]
    run = cd.merge_for_run(_cfg(scope={"include": ["/nope/*"], "exclude": []}), None, det)
    assert run["status"] == "UNVERIFIED" and "excluded" in run["reason"]


def test_ledger_records_count_as_committed(tmp_path):
    ledger = {"records": [{"id": "ep-0001", "endpoint": "/api/users/:id", "status": "open"}]}
    root = make_repo(tmp_path, {"server.js": EXPRESS})
    run = cd.merge_for_run(_cfg(endpoints=[]), ledger, cd.detect(str(root)))
    by = {e["path"]: e for e in run["endpoints"]}
    assert not by["/api/users/{id}"]["new"], "the ledger's :id spelling is the same route"


# --- the endpoints command with a live OpenAPI document --------------------------------

ENV = {"GIZMODUCK_STAGING_URLS": "https://staging.acme.test", "GIZMODUCK_AUTHORIZED_BY": "Jane Doe"}


def _endpoints_args(root, out, **over):
    base = {"repo": str(root), "config": str(root / "gizmoduck-ci.json"), "out": str(out), "summary": None,
            "no_live": False}
    base.update(over)
    return SimpleNamespace(**base)


def test_live_openapi_is_fetched_through_the_guard(tmp_path):
    root = make_repo(tmp_path / "r", {"gizmoduck-ci.json": json.dumps(_cfg(staging={
        "base_url": "https://staging.acme.test", "openapi_path": "/swagger/v1/swagger.json"}))})
    seen = []

    def fetch_doc(url):
        seen.append(url)
        return 200, json.dumps({"openapi": "3.0.1", "paths": {"/api/new": {"get": {}}}}).encode()

    rc = ci.cmd_endpoints(_endpoints_args(root, tmp_path / "o"), env=ENV, fetch=lambda u: (200, None),
                          fetch_doc=fetch_doc)
    assert rc == 0 and seen == ["https://staging.acme.test/swagger/v1/swagger.json"]
    run = json.loads((tmp_path / "o" / "endpoints-run.json").read_text())
    assert [e["path"] for e in run["new"]] == ["/api/new"]


def test_live_openapi_redirect_off_staging_is_refused_and_not_fetched(tmp_path):
    root = make_repo(tmp_path / "r", {"gizmoduck-ci.json": json.dumps(_cfg(staging={
        "base_url": "https://staging.acme.test", "openapi_path": "/openapi.json"}))})

    def fetch_doc(url):
        raise AssertionError(f"fetched {url} after the guard refused it")

    rc = ci.cmd_endpoints(_endpoints_args(root, tmp_path / "o"), env=ENV,
                          fetch=lambda u: (302, "https://prod.acme.test/openapi.json"), fetch_doc=fetch_doc)
    run = json.loads((tmp_path / "o" / "endpoints-run.json").read_text())
    assert rc == 0, "the committed list still stands"
    assert "refused by the guard" in run["live_openapi"] and run["new"] == []


def test_normalise_and_scan_path():
    assert cd.normalise_path("api//users/:id/") == "/api/users/{id}"
    assert cd.normalise_path("/u/<int:uid>/x/{id:int?}") == "/u/{uid}/x/{id}"
    assert cd.scan_path("/api/users/{id}/orders") == "/api/users"
    assert cd.scan_path("/{tenant}") == "/"


def test_detect_on_a_subdirectory_keeps_repo_relative_paths(tmp_path):
    root = make_repo(tmp_path, {"services/api/server.js": EXPRESS, "services/web/server.js": EXPRESS})
    det = cd.detect(str(root), os.path.join("services", "api"))
    assert {f.source.split(":")[0] for f in det.of("endpoint")} == {"services/api/server.js"}
