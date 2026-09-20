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

## Commits and pull requests

- [pre-commit](https://pre-commit.com/) runs ruff, gitleaks, a commit message
  check, and a guard against committing on `main`. Install the hooks with
  `pre-commit install` and `pre-commit install --hook-type commit-msg`. CI runs
  the same config in `.github/workflows/ci.yml`, so anything that passes
  locally passes there.
- Commit messages use [Conventional
  Commits](https://www.conventionalcommits.org/). This is enforced by a hook,
  and the release tooling parses it — a non-conforming message is rejected.
- All work lands through a pull request. The `no-commit-to-branch` hook fails
  any commit made while `main` is checked out. It is a local seatbelt rather
  than enforcement: it applies only where the hooks are installed, and
  `--no-verify` skips it.
- Pull requests are squash merged. The squash commit message is what ends up
  in history and in the CHANGELOG, so it has to be a valid conventional
  commit — the individual commits on the branch don't.

## Versioning and releases

[python-semantic-release](https://python-semantic-release.readthedocs.io/) owns
the version. It is configured under `[tool.semantic_release]` in
`pyproject.toml` and run by `.github/workflows/release.yml` on every push to
`main`. When the commits since the last tag warrant a release, it:

1. computes the next version and writes it to `project.version`
2. writes the new section of `CHANGELOG.md`
3. commits, tags `vX.Y.Z`, and pushes
4. publishes a GitHub Release carrying those notes

Don't edit the version or the CHANGELOG by hand — the next run will overwrite
either one.

Two details worth knowing:

- Releases carry notes only. This is an application rather than a published
  package, so no build runs and no artifacts are attached.
- The release commit is pushed with `GITHUB_TOKEN`. Pushes made with that token
  do not trigger workflows, so the release commit does not re-run CI. That is
  intended.

## Scripts

- `scripts/bedrock_smoke_test.py` makes a real, billed call to the Bedrock
  Responses API. Ask before running it.
- `scripts/generate_transcripts.py` generates a batch of meeting transcripts,
  which is also a real, billed call. Ask before running it. `--dry-run` prints
  the assembled prompt and calls nothing.

## Starting new work

Before creating a feature branch, get back to a clean main:

```bash
git switch main
git pull --prune

merged=$(gh pr list --state merged --json headRefName -q '.[].headRefName')

while IFS= read -r branch; do
  [ -n "$branch" ] || continue
  worktree=$(git worktree list --porcelain \
    | awk -v b="branch refs/heads/$branch" '/^worktree /{w=$2} $0==b{print w}')
  [ -n "$worktree" ] && git worktree remove --force "$worktree"
  git branch -D "$branch" 2>/dev/null
done <<< "$merged"

git worktree prune
git branch --list 'worktree-agent-*' --format='%(refname:short) %(worktreepath)' \
  | awk 'NF == 1 {print $1}' \
  | xargs -r -n1 git branch -d
```

A branch's worktree has to go before the branch does: git refuses to delete a
branch that is checked out in a worktree, so if a background agent's worktree
for a merged branch is still around, `git branch -D` fails for that branch and
`2>/dev/null` swallows the error, leaving it behind with no indication anything
was skipped. Handling both in one pass per branch keeps that order.

The loop reads `$merged` line by line rather than iterating `for branch in
$merged`, because the two shells disagree about the latter. Bash splits an
unquoted expansion on `IFS`, newline included, and iterates once per branch;
zsh does not word-split unquoted expansions at all, so the loop body ran once
with every name and the newlines between them in `$branch`. `awk -v` cannot
take a value containing a newline, so it exited with `newline in string` and
printed nothing, `$worktree` came back empty, and no worktree was ever
removed. `read` behaves the same in both shells. The deletion is inside the
loop for the same reason: as `printf '%s\n' $merged | xargs -r -n1 git branch
-D`, it worked in zsh only because `xargs` did the splitting the shell had
not, which hid the broken loop above it.

`2>/dev/null` stays on the deletion because `gh` reports every merged pull
request's head branch, most of which are long gone locally, and a branch that
does not exist is not a problem worth printing.

`--force` is needed on the removal because an agent's worktree is rarely
pristine — a stray `__pycache__` is enough for `git worktree remove` to
refuse. Discarding it is safe for the same reason force-deleting the branch
is: the pull request is merged, so anything still sitting there is either
already in `main` or was never wanted.

The last step exists because a background agent's worktree starts on an
auto-generated `worktree-agent-<id>` branch, which the agent then switches
away from to its real `feat/…` branch. That placeholder is never a pull
request's head, so GitHub never reports it as merged and the sweep above
never sees it. Left alone they accumulate, one per dispatch.

Two details keep this safe. `%(worktreepath)` is empty only for a branch no
worktree has checked out, so a live agent's placeholder is filtered out rather
than deleted underneath it. And the delete is `-d`, not `-D`: a placeholder
points at the commit the worktree branched from and has nothing unique on it,
so `-d` removes it, while anything carrying real work is refused and kept.

GitHub is asked which branches were merged because `git branch --merged`
cannot tell: the squash commit is a new commit with no ancestry link back to
the branch. GitHub knows, so ask it.
