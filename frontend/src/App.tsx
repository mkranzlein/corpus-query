import Ask from "./ask/Ask.tsx";

/**
 * The application: the question page.
 *
 * The review queue is served from the same bundle at its own address; see
 * `main.tsx` for how the two are told apart.
 */
export default function App() {
  return <Ask />;
}
