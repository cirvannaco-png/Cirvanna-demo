# Cirvanna Codespaces

This is a development workspace for repository work. It is not a production
runtime and does not provision production credentials, provider accounts,
managed databases, or deployed services.

## Create a Codespace

1. Open the Cirvanna GitHub repository.
2. Select the branch you intend to work on.
3. Choose **Code → Codespaces → Create codespace on branch**.
4. Wait for the dev container to finish creating the workspace.

The container configures Python 3.12 and Docker tooling. The bootstrap script
creates a repository-local `.venv`; it deliberately does not install every
microservice's dependencies because that would be slow, wasteful, and could
create conflicting dependency sets.

## Run a service's tests

From the repository root, run the targeted helper with the service path:

```bash
bash .devcontainer/scripts/test-service.sh services/decision-service
bash .devcontainer/scripts/test-service.sh services/api-gateway
bash .devcontainer/scripts/test-service.sh services/identity-learning-service
```

The helper always installs dependencies and runs pytest through the repository
root `.venv`, creating it if needed. It checks that this environment uses
Python 3.12. It installs that directory's `requirements.txt` and
`requirements-dev.txt`, when present, then runs its `tests/` suite. For
packages or services with a different test layout, follow that component's
README and invoke its documented test command directly.

Activate the same workspace environment before manual Python work:

```bash
source .venv/bin/activate
```

The shared `.venv` is convenient for one service at a time, not dependency
isolation. If services require incompatible dependency versions, create a
separate environment for that service and run its documented commands there;
do not install both incompatible dependency sets into the shared environment.

## Start disposable PostgreSQL

When a local integration test needs PostgreSQL:

```bash
bash .devcontainer/scripts/start-postgres.sh
```

The helper starts PostgreSQL 16 in a Docker container and persists its data
only in a Codespaces Docker volume. Its local-only connection details are:

- Host: `localhost`
- Port: `5432`
- Database: `cirvanna_dev`
- User: `cirvanna_dev`
- Password: `cirvanna_dev_only`

Use these credentials only for disposable local development. Never reuse them
in staging or production. Configure a service's documented database URL
explicitly in the Codespace environment when running integration tests. Do
not put secrets in source files, shell scripts, commits, or pull requests.

Stop the database when finished:

```bash
bash .devcontainer/scripts/stop-postgres.sh
```

Stopping the container retains its local Docker volume. Deleting the Codespace
or its Docker volume can destroy this disposable database; it is not a backup.

## Docker image checks

Use the repository's existing Dockerfiles and CI workflows as the authoritative
build definition. For an individual service, from its Docker build context:

```bash
docker build -t cirvanna-local:dev .
```

Do not push images from a development Codespace to a production registry.

## Security and evidence boundaries

- Never place Yoti API keys, HMAC keys, internal service tokens, database
  credentials, or production environment files in Git.
- Use mock provider responses for adapter and lifecycle tests unless an
  explicitly approved staging credential is provisioned through a secret
  manager.
- A passing local test proves only the tested local behaviour. It does not
  prove live Yoti verification, deployed CAL enforcement, Click It masking,
  CDN/cache deletion propagation, or production readiness.
- Do not run production migrations, modify live data, or deploy from this
  Codespace without the required review and explicit authorization.
