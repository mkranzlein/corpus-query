import { useEffect, useState } from "react";

/** What `GET /health` answers with, narrowed to what is shown here. */
interface Health {
  status: string;
  database: { readable: boolean; chunks: number | null };
  index: { loaded: boolean; vectors: number | null };
}

/**
 * The application shell.
 *
 * There is no question box and no answer view yet — those are separate pieces
 * of work. What this does is prove the whole path end to end: the bundle is
 * served, React mounts, and a request from the page reaches the API, whether
 * the page came from FastAPI or from the Vite development server proxying to
 * it.
 */
export default function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    fetch("/health", { signal: controller.signal })
      .then((response) => response.json() as Promise<Health>)
      .then(setHealth)
      .catch((error: unknown) => {
        if (!(error instanceof DOMException && error.name === "AbortError")) {
          setFailed(true);
        }
      });
    return () => controller.abort();
  }, []);

  return (
    <main>
      <h1>corpus-query</h1>
      <p>
        Ask a corpus of meeting transcripts and documents a question in plain
        English. The interface for doing that is still being built; for now the
        endpoints answer directly.
      </p>
      <section>
        <h2>Service</h2>
        {failed && <p role="status">The API did not answer.</p>}
        {!failed && !health && <p role="status">Checking…</p>}
        {health && (
          <ul>
            <li>Status: {health.status}</li>
            <li>Chunks: {health.database.chunks ?? "unreadable"}</li>
            <li>Vectors: {health.index.vectors ?? "not loaded"}</li>
          </ul>
        )}
      </section>
    </main>
  );
}
