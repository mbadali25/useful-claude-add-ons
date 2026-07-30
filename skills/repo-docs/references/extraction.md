# Extraction guide

How to find the things the docs need — entry points, routes, public functions, jobs, and
configuration — across common stacks. Read the section for the stack in front of you.

Contents:
- [General strategy](#general-strategy)
- [Python](#python)
- [JavaScript / TypeScript](#javascript--typescript)
- [Go](#go)
- [Java / Kotlin](#java--kotlin)
- [Ruby](#ruby)
- [C# / .NET](#c--net)
- [Rust](#rust)
- [PHP](#php)
- [Shell / CLI tools](#shell--cli-tools)
- [Infrastructure and CI](#infrastructure-and-ci)
- [Prefer the generator](#prefer-the-generator)
- [Grep recipes](#grep-recipes)

## General strategy

Work outside-in, in this order:

1. **Dependency manifest** — tells you the frameworks, which tells you where to look.
2. **Entry point** — `main`, `app`, `index`, `server`, `cmd/`, or the `scripts`/`console_scripts`
   declaration in the manifest.
3. **Route/command registration** — usually one or a few files, often imported by the entry point.
4. **Config surface** — every read of an environment variable or config key.
5. **Data models / schema** — ORM models, migrations, protobuf, OpenAPI, SQL DDL.
6. **Tests** — the best available spec for intent. Integration tests reveal the real
   request/response shapes better than reading handlers.
7. **CI config** — the authoritative list of commands that must work.

Record `file:line` as you go; retrofitting them later is miserable.

## Python

Manifests: `pyproject.toml`, `requirements*.txt`, `setup.py`, `Pipfile`, `environment.yml`.
Entry points: `main.py`, `app.py`, `__main__.py`, `manage.py`, `wsgi.py`/`asgi.py`, and
`[project.scripts]` in `pyproject.toml`.

| Framework | Where routes live |
|---|---|
| FastAPI | `@app.<method>` / `@router.<method>` decorators; `APIRouter` includes; Pydantic models are your request/response schema |
| Flask | `@app.route` / `@bp.route`, `add_url_rule`, blueprint registration |
| Django | `urls.py` `urlpatterns`; views in `views.py`; DRF `ViewSet`s + `routers.register`; `models.py` for schema; `settings.py` for config |
| Starlette | `Route(...)` lists passed to the app |
| Celery | `@shared_task` / `@app.task`; beat schedule in settings |
| Click/Typer/argparse | `@click.command`, `@app.command`, `add_argument` calls |

Public functions: names not prefixed with `_`, plus anything listed in `__all__`.
Config: `os.environ` / `os.getenv` / `env(...)` / `BaseSettings` subclasses.
Type hints and docstrings are free documentation — copy signatures verbatim, do not retype.

## JavaScript / TypeScript

Manifest: `package.json` (`scripts` is your command list; `exports`/`main`/`types` is your
public surface). Also check `tsconfig.json` paths and any monorepo config
(`pnpm-workspace.yaml`, `turbo.json`, `nx.json`, `lerna.json`) — a monorepo means multiple
apps, each needing its own treatment.

| Framework | Where routes live |
|---|---|
| Express/Koa | `app.get/post/...`, `router.<method>`, `app.use('/prefix', router)` |
| Next.js | `pages/api/**` or `app/**/route.ts`; server actions marked `'use server'` |
| NestJS | `@Controller` + `@Get/@Post` decorators; `@Injectable` providers |
| Fastify | `fastify.route(...)`, `fastify.register(plugin, {prefix})` |
| Remix/SvelteKit | file-based routes: `routes/**`, `loader`/`action`/`+server.ts` |
| tRPC | router definitions, `publicProcedure`/`protectedProcedure` chains |

Public API: `export` statements, `index.ts` barrels, the `exports` map in package.json.
Config: `process.env.*`, `import.meta.env.*`, `.env*` files, `zod`/`envalid` schemas.
Prefer `.d.ts` or source types over inventing parameter descriptions.

## Go

`go.mod` for module path and deps. Entry points: `main()` in `cmd/*/main.go`.

Routes: `http.HandleFunc`, `mux.HandleFunc`, `r.Get/Post` (chi), `e.GET` (echo),
`router.GET` (gin), gRPC service registration (`pb.Register*Server`) with the `.proto`
files as the real interface definition.
Public API: exported (capitalized) identifiers. `go doc ./...` is a fast inventory.
Config: `os.Getenv`, `flag.*`, viper.

## Java / Kotlin

`pom.xml` / `build.gradle(.kts)`. Entry: `@SpringBootApplication`, `public static void main`.

Routes: `@RestController` + `@GetMapping`/`@PostMapping`/`@RequestMapping`; JAX-RS `@Path`.
Jobs: `@Scheduled`, `@KafkaListener`, `@RabbitListener`.
Config: `application.yml`/`.properties`, `@Value`, `@ConfigurationProperties`.
Schema: JPA `@Entity` classes, Flyway/Liquibase migrations.

## Ruby

`Gemfile`, `*.gemspec`. Rails: `config/routes.rb` is the definitive route list
(`bin/rails routes` if you can run it), controllers in `app/controllers`, models in
`app/models`, jobs in `app/jobs`, `config/` for environment config, `db/schema.rb` for schema.
Sinatra: `get '/path' do` blocks. Config: `ENV[...]`, `Rails.application.credentials`.

## C# / .NET

`*.csproj`, `*.sln`. Entry: `Program.cs`. Routes: `[ApiController]` + `[HttpGet]`
attributes, or minimal API `app.MapGet(...)`. Config: `appsettings*.json`, `IOptions<T>`.
Schema: EF Core `DbContext` and `Migrations/`.

## Rust

`Cargo.toml` (`[[bin]]`, `[lib]`, features). Entry: `src/main.rs`, `src/lib.rs`.
Routes: axum `Router::new().route(...)`, actix `web::resource`/`#[get(...)]`, rocket
`#[get("/path")]`. Public API: `pub` items re-exported from `lib.rs`.
Config: `std::env::var`, `clap` derives, `config` crate.

## PHP

`composer.json`. Laravel: `routes/web.php` and `routes/api.php`, controllers in
`app/Http/Controllers`, models in `app/Models`, `.env` + `config/*.php`, migrations in
`database/migrations`. Symfony: `config/routes.yaml` or `#[Route]` attributes.

## Shell / CLI tools

`Makefile` targets, `justfile` recipes, `bin/` and `scripts/` contents, `Taskfile.yml`.
These are the commands to put in CLAUDE.md and the README — they are verified by existing.

## Infrastructure and CI

`Dockerfile` (base image, exposed ports, entrypoint, build stages), `docker-compose.yml`
(the dependent services — this is often the fastest route to an accurate architecture
diagram), `.github/workflows/*`, `.gitlab-ci.yml`, `Jenkinsfile` (the real command list),
`terraform/`, `k8s/`, `helm/` (deployment topology), `.env.example` (the config surface,
already redacted for you — an excellent source).

## Prefer the generator

If the project already produces reference docs, link to them rather than hand-maintaining
a copy that will silently rot:

| Signal | Generator |
|---|---|
| `openapi.yaml`, `/docs` on a FastAPI app, `swagger.json` | OpenAPI — link the spec and the UI route |
| `docs/conf.py` | Sphinx |
| `typedoc.json`, `.d.ts` output | TypeDoc |
| `mkdocs.yml` | MkDocs |
| Doc comments + `go doc` | godoc |
| `javadoc` in the build config | Javadoc |

Say in `docs/API.md` where the generator config lives and how to regenerate. Hand-write
only the parts the generator cannot express: conventions, auth flow, worked examples,
migration notes.

## Grep recipes

Fast first passes. Always confirm hits by reading the surrounding code — regexes find
strings, not semantics.

```bash
# HTTP routes across common frameworks
grep -rnE "@(app|router|bp)\.(get|post|put|patch|delete)|app\.(get|post|put|patch|delete)\(|@(Get|Post|Put|Patch|Delete)Mapping|@(Get|Post|Put|Patch|Delete)\(|\.(HandleFunc|MapGet|MapPost)\(" --include='*.py' --include='*.js' --include='*.ts' --include='*.go' --include='*.java' --include='*.cs' .

# Environment variable reads
grep -rnE "os\.(getenv|environ)|process\.env\.|ENV\[|System\.getenv|std::env::var|Environment\.GetEnvironmentVariable" .

# Work markers
grep -rnE "\b(TODO|FIXME|HACK|XXX|BUG|DEPRECATED)\b" .

# Unimplemented stubs
grep -rnE "NotImplementedError|not implemented|todo!\(|unimplemented!\(|panic\(\"TODO" .

# Skipped tests
grep -rnE "@(skip|pytest\.mark\.skip|Ignore)|\.(skip|todo)\(|xit\(|t\.Skip\(" .
```

`scripts/repo_survey.py` already collects work markers, env var reads, and entry-point
candidates — run it first and use grep for follow-up on what it surfaces.
