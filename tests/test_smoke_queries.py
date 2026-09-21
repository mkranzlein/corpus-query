"""Smoke queries: the two behaviors most worth not losing.

A question the corpus answers must come back with citations, and a question
it does not must abstain and suggest who to ask. Each goes through the whole
service — ``/answer``, the graph, the retrieval tool posting to ``/search``,
and the answer row it writes — and the row is checked as well as the
response, since the row is where a change in either shows up first.

Retrieval runs two ways. **Stubbed**, it hands back a canned passage, which
keeps both queries in every run of the suite, CI included. **Real**, it ranks
the committed corpus with the project's own embedder and cross-encoder, which
is the version that notices retrieval itself getting worse: the answerable
question has to find the meeting that answers it. That needs the models
extra and the weights already downloaded (``uv run scripts/fetch_models.py``),
and is skipped without them, as the other tests that load a model are.

The chat model is scripted either way. What a model decides is not something
a test can assert on; what the service does with each decision is, and that
is what these pin down. Nothing here reaches Ollama or anything hosted.
"""

from __future__ import annotations

import dataclasses
import shutil
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from test_agent_answer import (
    ScriptedModel,
    answered,
    answering_app,
    recorded,
    says,
    searches,
    verified,
)
from test_api import StubSearch, a_confidence, a_result, request

from corpus_query.agent.graph import Agent, build_graph
from corpus_query.agent.retrieval import in_process_client, search_tool
from corpus_query.agent.runtime import correction_recorder
from corpus_query.api.app import Resources, create_app
from corpus_query.retrieval.search import SearchResult
from corpus_query.store import capture
from corpus_query.store.db import connect
from corpus_query.transcripts.roster import (
    DEFAULT_ROSTER_FILE,
    first_names,
    read_roster,
)

REPO_ROOT = Path(__file__).resolve().parents[1]

#: The committed corpus. Copied before it is opened, so nothing a run does
#: can touch the file under version control.
CORPUS = REPO_ROOT / "data" / "corpus.db"

#: A question one meeting in the committed corpus answers outright.
ANSWERABLE = "What is the fully loaded cost of hiring a firmware engineer?"

#: The meeting that answers it.
ANSWERING_DOCUMENT = "hiring-plan-firmware-engineer-headcount"

#: What the scripted model answers it with: the meeting's own figures.
ANSWER = (
    "In the firmware engineer headcount meeting, Marcus put the fully loaded "
    "cost at a hundred and sixty to a hundred and eighty thousand per head."
)

#: A question the corpus never discusses, asked in the same register as the
#: ones it does, so retrieval still comes back with passages that look
#: relevant and are not.
UNANSWERABLE = "What did we decide about the lease on the Singapore office?"

ABSTENTION = "The record does not say anything about a Singapore office lease."


def answering_script() -> list:
    """Script a turn that searches, answers from the passage, and settles it."""
    return [
        searches("fully loaded cost of a firmware engineer hire"),
        says(ANSWER),
        verified(),
        answered(),
    ]


def abstaining_script() -> list:
    """Script a turn that searches, finds nothing on point, and says so."""
    return [
        searches("Singapore office lease decision"),
        says(ABSTENTION),
        verified(),
        says(
            "CONTEXT: I was looking for what was decided about the Singapore "
            "office lease, and the record does not mention one.\n"
            "QUESTION: Was a decision made on the Singapore office lease?"
        ),
    ]


def stubbed_passage() -> SearchResult:
    """Return the passage stubbed retrieval hands back for both questions.

    The meeting's own line, so the answerable question is answered from what
    real retrieval finds for it. For the unanswerable one it is a passage
    that does not answer it, which is what real retrieval returns there too.
    """
    result = dataclasses.replace(
        a_result(
            document_slug=ANSWERING_DOCUMENT,
            title="Hiring Plan – Firmware Engineer Headcount",
            attendees=["Priya", "Marcus", "Sofia", "Renata"],
            location="turns 8-8",
        ),
        text=(
            "[Marcus]: For a mid-level engineer with three to five years of "
            "embedded systems experience, I'd expect a base salary in the "
            "range of a hundred and fifteen to a hundred and thirty thousand. "
            "Fully loaded with benefits and overhead, call it a hundred and "
            "sixty to a hundred and eighty thousand per head."
        ),
    )
    return SearchResult(results=[result], confidence=a_confidence())


def scripted_agent(model: ScriptedModel):
    """Open the agent on a scripted model, as the answering tests do."""

    @asynccontextmanager
    async def open_scripted(app):
        client = in_process_client(app)
        try:
            yield Agent(
                graph=build_graph(
                    model,
                    [search_tool(client)],
                    checkpointer=InMemorySaver(),
                    record_correction=correction_recorder(),
                )
            )
        finally:
            await client.aclose()

    return open_scripted


@pytest.fixture(scope="module")
def real_corpus(tmp_path_factory):
    """Copy the committed corpus, and build its vector index, once.

    Skipped when the models extra is not installed or the weights are not
    already downloaded. Nothing is fetched: the weights are looked for in
    the local cache only.

    Yields:
        The copied store's path and the index directory beside it.
    """
    # The project's model modules are imported before anything else that
    # would pull in huggingface_hub, sentence-transformers included: they
    # point the weights cache inside the project, and huggingface_hub reads
    # where its cache is once, when it is first imported.
    try:
        from corpus_query.models.embedder import EMBEDDING_MODEL_ID, load_embedder
        from corpus_query.models.reranker import RERANKER_MODEL_ID, load_reranker
    except ImportError:
        pytest.skip("the models extra is not installed")
    from huggingface_hub import constants, snapshot_download
    from huggingface_hub.errors import LocalEntryNotFoundError

    from corpus_query.retrieval.index import build_index

    try:
        for model_id in (EMBEDDING_MODEL_ID, RERANKER_MODEL_ID):
            snapshot_download(model_id, local_files_only=True)
    except LocalEntryNotFoundError:
        pytest.skip("the embedding and reranking weights are not downloaded")

    # Offline for as long as the models are in use, so loading them reads
    # the cache and never the network. huggingface_hub reads the variable
    # once, on import, which has already happened, so its constant is set
    # as well.
    offline = pytest.MonkeyPatch()
    offline.setenv("HF_HUB_OFFLINE", "1")
    offline.setattr(constants, "HF_HUB_OFFLINE", True)
    try:
        load_embedder()
        load_reranker()

        directory = tmp_path_factory.mktemp("corpus")
        store = directory / "corpus.db"
        shutil.copyfile(CORPUS, store)
        connection = connect(store)
        try:
            build_index(connection, directory / "chroma")
        finally:
            connection.close()
        yield store, directory / "chroma"
    finally:
        offline.undo()
        load_embedder.cache_clear()
        load_reranker.cache_clear()


@pytest.fixture(params=["stubbed", pytest.param("real", marks=pytest.mark.slow)])
def serve(request):
    """Return a factory for the service answering on a scripted model.

    Args:
        request: Which retrieval to serve with.

    Returns:
        A function from a scripted model to the application.
    """
    if request.param == "stubbed":
        return lambda model: answering_app(model, StubSearch(result=stubbed_passage()))

    store, index_dir = request.getfixturevalue("real_corpus")
    from corpus_query.retrieval.index import open_index

    def resources() -> Resources:
        connection = connect(store)
        return Resources(
            connection=connection,
            collection=open_index(connection, index_dir),
            captured=capture.connect(),
        )

    return lambda model: create_app(resources=resources, agent=scripted_agent(model))


def test_an_answerable_question_comes_back_with_citations(serve) -> None:
    """The meeting that answers it is cited, and the row says it was answered."""
    body = request(
        serve(ScriptedModel(answering_script())),
        "POST",
        "/answer",
        json={"question": ANSWERABLE},
    ).json()

    assert body["answer"] == ANSWER
    assert ANSWERING_DOCUMENT in {row["document_slug"] for row in body["citations"]}
    assert body["routing"] is None

    written = recorded()
    [row] = written["answers"]
    assert row["id"] == body["answer_id"]
    assert row["abstained"] == 0
    assert row["searches"] == 1
    assert row["top_score"] is not None
    # Every word of the answer that carries a claim is in one passage, which
    # is only true when the passage that answers the question came back.
    assert row["citation_coverage"] == 1.0
    assert written["gaps"] == []


def test_an_unanswerable_question_abstains_and_routes(serve) -> None:
    """Nothing on point comes back, so it abstains and names who to ask."""
    body = request(
        serve(ScriptedModel(abstaining_script())),
        "POST",
        "/answer",
        json={"question": UNANSWERABLE},
    ).json()

    assert body["answer"] == ABSTENTION
    routing = body["routing"]
    assert routing is not None
    assert routing["question"].endswith(
        "Was a decision made on the Singapore office lease?"
    )
    suggested = {person["name"] for person in routing["candidates"]}
    assert suggested
    assert suggested <= set(first_names(read_roster(REPO_ROOT / DEFAULT_ROSTER_FILE)))

    written = recorded()
    [row] = written["answers"]
    [gap] = written["gaps"]
    assert row["abstained"] == 1
    assert row["searches"] == 1
    assert gap["answer_id"] == body["answer_id"]
    assert gap["routing"] == routing
