"""The agent that answers a question out of the corpus.

Retrieval ranks passages. This package turns them into an answer, with
retrieval as a tool the model chooses to call rather than a step that always
runs first: a question the conversation already answered needs no search, an
out-of-scope question needs no search, and a question with two halves needs
two.

LangGraph is a library here, not a service. The graph is compiled once when
the application starts and awaited per request inside the handler. There is
no agent process, no queue, and no daemon.
"""
