"""The office generation prompts, one markdown file per format.

These are not loaded by the application. Unlike the enrichment prompts, which
a pass reads and fills in, each of these is read by a person or an agent that
writes the files by hand with document-authoring tools — three files of one
format per run. They live under version control for the same reason every
other prompt does: the prompt is the explanation of how the corpus came to
look the way it does, and a corpus that cannot be explained is worth less
than one that cannot be reproduced.

Each prompt names its own three documents. What all nine are, who wrote them,
and how they relate to the meeting transcripts is settled in
``data/office_files_guidance.md``, so that the three prompts cannot drift
apart from each other.
"""
