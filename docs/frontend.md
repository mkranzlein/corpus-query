# The committed frontend

The browser application lives in `frontend/`: React and TypeScript, compiled
by Vite. Its build output is committed, at
`corpus_query/api/static/`, and FastAPI serves that directory at `/`.

Committing a build is unusual enough to say why. Node is a build-time
dependency and nothing more — no part of running this system calls it — so
shipping the build means a clone needs Python and nothing else to get a
working page. The alternative is telling everyone who wants to run the project
to install a second toolchain to produce a file that was identical for
everyone who produced it. The bundle is a couple of hundred kilobytes, which
is a small thing to keep in a repository in exchange for deleting the largest
setup obstacle it had.

The consequence is that **a frontend change is not finished until the build is
rebuilt and committed with it**. The source and the bundle are one change.

```bash
npm --prefix frontend ci       # once
npm --prefix frontend run dev  # http://localhost:5173, against a live API
```

`npm run dev` serves the application itself with hot module replacement and
proxies `/search`, `/answer`, `/chunks`, `/health`, `/feedback`,
`/corrections`, `/gaps`, `/openapi.json`, and `/docs` through to
`scripts/serve.py` on port 8000, so run that in another terminal. Requests
stay same-origin that way, which is why the API carries no CORS configuration
for the sake of development.

```bash
npm --prefix frontend run lint       # eslint
npm --prefix frontend run typecheck  # tsc
npm --prefix frontend test           # vitest, against a stubbed API
npm --prefix frontend run build      # writes corpus_query/api/static/
```

If `corpus_query/api/static/` is ever missing, the API still starts and the
endpoints still answer; `/` says what to run instead. The page is the one
thing that needs it.
