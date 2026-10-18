# GitHub Codespaces workspace

## Status and safety

This configuration is introduced on the isolated branch `chore/codespaces-workspace-bootstrap`. It does not change `main`, merge code, trigger a deployment by itself, or configure production secrets.

The Codespaces environment uses the Microsoft universal development container image and installs editor extensions for Python, YAML, Docker, and GitHub pull-request review. The post-create command only prints installed tool versions; it does not install project dependencies or run migrations.

## Create the Codespace

1. Open the repository: https://github.com/cirvannaco-png/Cirvanna-demo
2. Select branch `chore/codespaces-workspace-bootstrap`.
3. Select **Code → Codespaces → Create codespace on chore/codespaces-workspace-bootstrap**.
4. Review the machine type and the displayed payer/billing notice before confirming creation. Stop the Codespace when not using it.
5. In the terminal, verify the checkout before editing:

   ```bash
   git status --short --branch
   git branch --show-current
   git log -1 --oneline
   ```

6. Confirm the current branch is `chore/codespaces-workspace-bootstrap`. Keep changes on a task-specific branch and open a pull request for review.

## Initial repository reconnaissance

From the Codespaces terminal:

```bash
git status --short --branch
git branch -a
find . -maxdepth 3 -type f \\( -name 'pyproject.toml' -o -name 'requirements.txt' -o -name 'package.json' -o -name 'pytest.ini' -o -name 'tox.ini' \\) -print
```

Read the repository README and each relevant service's dependency/test instructions before installing dependencies or running tests. Start with non-destructive checks. Do not run database migrations against any non-test database, add credentials to files, merge pull requests, or deploy without explicit review and verified checks.

## Engineering workflow

- Treat `main` as the release baseline; create a new branch for each bounded task.
- Inspect diffs before committing: `git diff --check`, `git diff`, and `git status`.
- Run the checks relevant to the changed component and record the exact commands/results.
- Open a pull request; do not bypass failing checks or promote staged source candidates into canonical runtime paths without audit.
- Never place API tokens, production URLs containing credentials, customer images, or real secrets in the repository or Codespaces logs.
- This configuration is a starter environment, not proof that the application builds or is production-ready.
