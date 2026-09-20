# corpus-query

## Python

- Package and environment management is [uv](https://docs.astral.sh/uv/).
  Use `uv add`, `uv run`, and `uv sync` — not pip, not a hand-managed venv.
  Dependencies live in `pyproject.toml` and are locked in `uv.lock`.
- Linted and formatted with [ruff](https://docs.astral.sh/ruff/). Ruff's rules
  are authoritative.
- Follow the [Google Python style
  guide](https://google.github.io/styleguide/pyguide.html) wherever it doesn't
  conflict with a ruff rule. Where they disagree, ruff wins.

## Commits and releases

- [pre-commit](https://pre-commit.com/) runs ruff, gitleaks, and a commit
  message check locally. Install the hooks with `pre-commit install` and
  `pre-commit install --hook-type commit-msg`. CI runs the same config, so
  anything that passes locally passes there.
- Commit messages use [Conventional
  Commits](https://www.conventionalcommits.org/). This is enforced by a hook,
  and the release tooling parses it — a non-conforming message is rejected.
- Versioning is handled by
  [python-semantic-release](https://python-semantic-release.readthedocs.io/),
  which derives the version, CHANGELOG, and tags from commit history. Don't
  edit the version by hand.
- Pull requests are squash merged. The squash commit message is what ends up
  in history and in the CHANGELOG, so it has to be a valid conventional
  commit — the individual commits on the branch don't.

## Scripts

- `scripts/bedrock_smoke_test.py` makes a real, billed call to the Bedrock
  Responses API. Ask before running it.

## Starting new work

Before creating a feature branch, get back to a clean main:

```bash
git switch main
git pull --prune
gh pr list --state merged --json headRefName -q '.[].headRefName' \
  | xargs -r -n1 git branch -D 2>/dev/null
```

The last step is needed because `git branch --merged` does not detect
squash-merged branches — the squash commit is a new commit with no ancestry
link back to the branch, so git cannot tell it was merged. GitHub can, so ask
it. Force-delete is safe here for exactly that reason: the PR is confirmed
merged.
