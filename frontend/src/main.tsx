import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import App from "./App.tsx";
import "./index.css";
import Review from "./review/Review.tsx";

const root = document.getElementById("root");
if (!root) {
  throw new Error("index.html has no #root to mount into");
}

// One bundle serves two pages, told apart by the path the browser asked for.
// The review queue is for someone reading what the system got wrong, not for
// the people asking it questions, so it has its own address and the question
// page does not link to it. Matching the end of the path rather than the
// whole of it keeps this working behind a prefix, the same as the relative
// asset URLs in the build do.
const page = /\/review\/?$/.test(window.location.pathname) ? (
  <Review />
) : (
  <App />
);

createRoot(root).render(<StrictMode>{page}</StrictMode>);
