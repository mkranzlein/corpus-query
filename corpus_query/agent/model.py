"""The one place the agent's chat model is named.

The graph asks for a chat model and gets LangChain's
:class:`~langchain_core.language_models.chat_models.BaseChatModel` back. No
node names a provider, imports a client, or knows what is answering it, which
is what lets a second backend arrive as a change to this module and nothing
else.

Today there is one backend: ``granite4.1:8b`` served locally by Ollama, which
costs nothing to run and calls nothing hosted. It was chosen to fit a 16GB
machine — Apache 2.0, about 5.3GB quantized, trained for function calling —
and a model that size chooses its tools less reliably than a large hosted one
does. That is expected here rather than tuned away.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from langchain_core.language_models.chat_models import BaseChatModel

#: The local model the agent answers from, as Ollama names it. Pull it with
#: ``ollama pull granite4.1:8b``.
DEFAULT_MODEL = "granite4.1:8b"

#: Answering from retrieved passages is not a creative task, and a small
#: model left free to wander is a small model inventing a date.
DEFAULT_TEMPERATURE = 0.0

#: How large a context window to ask Ollama for.
#:
#: This has to be set, and it has to be set here. Ollama defaults to a 4096
#: token window regardless of what the model supports, and it makes room by
#: dropping tokens from the front — which is where the system prompt is. Five
#: retrieved passages are enough to go over, so the instructions that say to
#: abstain are the first thing evicted, precisely when they matter most. What
#: that looks like from outside is an agent that follows its prompt on short
#: questions and summarizes whatever retrieval returned on long ones.
#:
#: The size is measured rather than guessed. Ollama reports what it actually
#: evaluated, and the longest realistic turns come in at about 4k tokens for a
#: two-part question that searched twice, and about 5.5k for one search over
#: dense spreadsheet rows — so the default window was missing by a few hundred
#: tokens, which is why the failure looked so arbitrary. 16k is three times
#: the worst turn measured and still leaves room for a conversation to grow on
#: one thread, while costing meaningfully less KV cache than 32k on a machine
#: that has to hold the weights too: 8.2GB resident rather than 10GB.
#:
#: What it does not cover is a turn that runs all the way to
#: :data:`corpus_query.agent.graph.MAX_SEARCHES`. Six searches over passages
#: as dense as the spreadsheet rows would come to roughly 27k tokens, and
#: Ollama would start dropping the front of them again. Real questions take
#: one or two searches and the ceiling exists to stop a loop rather than to be
#: reached, so this is a bound worth knowing rather than one worth sizing the
#: window for.
DEFAULT_CONTEXT_WINDOW = 16384


def load_chat_model(
    model: str = DEFAULT_MODEL,
    temperature: float = DEFAULT_TEMPERATURE,
    context_window: int = DEFAULT_CONTEXT_WINDOW,
) -> BaseChatModel:
    """Build the chat model the agent runs on.

    Args:
        model: Which local model to answer from, as Ollama names it.
        temperature: How much the model is allowed to wander.
        context_window: How many tokens to give the model to work in.

    Returns:
        The chat model, as LangChain's interface to it.
    """
    from langchain_ollama import ChatOllama

    return ChatOllama(model=model, temperature=temperature, num_ctx=context_window)
