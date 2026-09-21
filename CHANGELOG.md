# CHANGELOG

<!-- version list -->

## v2.9.0 (2026-09-21)

### Bug Fixes

- Keep the system prompt inside the model's context window
  ([#103](https://github.com/mkranzlein/corpus-query/pull/103),
  [`951be5d`](https://github.com/mkranzlein/corpus-query/commit/951be5dd070e22f5b7ed88d2a5186c230f45f0ca))

### Chores

- Rebuild the committed corpus over all four formats
  ([#83](https://github.com/mkranzlein/corpus-query/pull/83),
  [`7fb3d49`](https://github.com/mkranzlein/corpus-query/commit/7fb3d499a015850ce093013240db5a3d81d29ff3))

### Continuous Integration

- Skip the test job on documentation-only pull requests
  ([#85](https://github.com/mkranzlein/corpus-query/pull/85),
  [`fac97aa`](https://github.com/mkranzlein/corpus-query/commit/fac97aae09b67ff540989e45c08840d7246cb7a9))

### Documentation

- Add CI status badge to README ([#82](https://github.com/mkranzlein/corpus-query/pull/82),
  [`4f555e4`](https://github.com/mkranzlein/corpus-query/commit/4f555e40badf6cccf6db0b03b4c12f883a80db05))

- Document /answer and what it takes to run it
  ([#103](https://github.com/mkranzlein/corpus-query/pull/103),
  [`951be5d`](https://github.com/mkranzlein/corpus-query/commit/951be5dd070e22f5b7ed88d2a5186c230f45f0ca))

### Features

- Answer questions with a LangGraph agent at POST /answer
  ([#103](https://github.com/mkranzlein/corpus-query/pull/103),
  [`951be5d`](https://github.com/mkranzlein/corpus-query/commit/951be5dd070e22f5b7ed88d2a5186c230f45f0ca))

### Performance Improvements

- Size the context window from measurement, not from a round number
  ([#103](https://github.com/mkranzlein/corpus-query/pull/103),
  [`951be5d`](https://github.com/mkranzlein/corpus-query/commit/951be5dd070e22f5b7ed88d2a5186c230f45f0ca))

### Refactoring

- Consolidate build_client into one shared module
  ([#90](https://github.com/mkranzlein/corpus-query/pull/90),
  [`a52ba2e`](https://github.com/mkranzlein/corpus-query/commit/a52ba2e3407be7b29138096848f866108b402eda))

- Fold the three author-on-roster checks into one helper
  ([#86](https://github.com/mkranzlein/corpus-query/pull/86),
  [`ec3f023`](https://github.com/mkranzlein/corpus-query/commit/ec3f0234509e413b03564b8b8c5db0354d943f95))

- Keep runtime state in its own database, not the corpus
  ([#103](https://github.com/mkranzlein/corpus-query/pull/103),
  [`951be5d`](https://github.com/mkranzlein/corpus-query/commit/951be5dd070e22f5b7ed88d2a5186c230f45f0ca))

### Testing

- Cover the agent's lifespan, its model seam, and the prompt loader
  ([#103](https://github.com/mkranzlein/corpus-query/pull/103),
  [`951be5d`](https://github.com/mkranzlein/corpus-query/commit/951be5dd070e22f5b7ed88d2a5186c230f45f0ca))


## v2.8.0 (2026-09-21)

### Documentation

- Say how a workbook is chunked in the ingestion note
  ([#78](https://github.com/mkranzlein/corpus-query/pull/78),
  [`3fd2005`](https://github.com/mkranzlein/corpus-query/commit/3fd2005eaab69b0e5848c2e33fce16509d213576))

### Features

- Read Excel workbooks into per-sheet row windows
  ([#78](https://github.com/mkranzlein/corpus-query/pull/78),
  [`3fd2005`](https://github.com/mkranzlein/corpus-query/commit/3fd2005eaab69b0e5848c2e33fce16509d213576))

### Testing

- Count blocks rather than lines when checking for repeats
  ([#78](https://github.com/mkranzlein/corpus-query/pull/78),
  [`3fd2005`](https://github.com/mkranzlein/corpus-query/commit/3fd2005eaab69b0e5848c2e33fce16509d213576))

- Cover workbook reading, windowing, and enrichment
  ([#78](https://github.com/mkranzlein/corpus-query/pull/78),
  [`3fd2005`](https://github.com/mkranzlein/corpus-query/commit/3fd2005eaab69b0e5848c2e33fce16509d213576))


## v2.7.0 (2026-09-21)

### Features

- Read PowerPoint decks into one chunk per slide
  ([#76](https://github.com/mkranzlein/corpus-query/pull/76),
  [`831a160`](https://github.com/mkranzlein/corpus-query/commit/831a1600c1ab8719fc308714e480550ff5042fcb))

### Testing

- Cover reading, ingesting, and enriching PowerPoint decks
  ([#76](https://github.com/mkranzlein/corpus-query/pull/76),
  [`831a160`](https://github.com/mkranzlein/corpus-query/commit/831a1600c1ab8719fc308714e480550ff5042fcb))


## v2.6.0 (2026-09-21)

### Build System

- Add python-docx for reading Word documents
  ([#77](https://github.com/mkranzlein/corpus-query/pull/77),
  [`4d19bb8`](https://github.com/mkranzlein/corpus-query/commit/4d19bb8a3d1d41139cf68d5df04d1c67681d229a))

### Chores

- Track the document-skills plugin as enabled
  ([#72](https://github.com/mkranzlein/corpus-query/pull/72),
  [`e1e5826`](https://github.com/mkranzlein/corpus-query/commit/e1e582647be875899433629b8184fc4ec7400103))

### Documentation

- Commit the generated office documents and note how they were made
  ([#75](https://github.com/mkranzlein/corpus-query/pull/75),
  [`be79e2c`](https://github.com/mkranzlein/corpus-query/commit/be79e2c7fbe8056cc4d9f5098f289e9808673325))

- Record what the transcript corpus actually planted
  ([#70](https://github.com/mkranzlein/corpus-query/pull/70),
  [`bdc3722`](https://github.com/mkranzlein/corpus-query/commit/bdc37224a825a7c44223f4e21ebe4990a8f927d7))

### Features

- Read Word documents into heading-section chunks
  ([#77](https://github.com/mkranzlein/corpus-query/pull/77),
  [`4d19bb8`](https://github.com/mkranzlein/corpus-query/commit/4d19bb8a3d1d41139cf68d5df04d1c67681d229a))

### Testing

- Cover enriching and searching a Word document
  ([#77](https://github.com/mkranzlein/corpus-query/pull/77),
  [`4d19bb8`](https://github.com/mkranzlein/corpus-query/commit/4d19bb8a3d1d41139cf68d5df04d1c67681d229a))

- Cover reading Word documents and their heading sections
  ([#77](https://github.com/mkranzlein/corpus-query/pull/77),
  [`4d19bb8`](https://github.com/mkranzlein/corpus-query/commit/4d19bb8a3d1d41139cf68d5df04d1c67681d229a))


## v2.5.0 (2026-09-20)

### Documentation

- Move provisioning to its own page and shorten the README
  ([#66](https://github.com/mkranzlein/corpus-query/pull/66),
  [`4933fed`](https://github.com/mkranzlein/corpus-query/commit/4933fedd00337dc32b6bbd11c28a6cd4b62e0938))

### Features

- Add the office document generation inputs
  ([#68](https://github.com/mkranzlein/corpus-query/pull/68),
  [`91d750b`](https://github.com/mkranzlein/corpus-query/commit/91d750bc8b5d4b9954a2a56739bc3708ad06a475))


## v2.4.0 (2026-09-20)

### Documentation

- Allow Ollama-backed runs without asking first
  ([#64](https://github.com/mkranzlein/corpus-query/pull/64),
  [`eb15b56`](https://github.com/mkranzlein/corpus-query/commit/eb15b56a0ad779adb3b6a08ccd7e67c06fc00b16))

### Features

- Commit the generated corpus so a clone can query without generating one
  ([#63](https://github.com/mkranzlein/corpus-query/pull/63),
  [`519d5b9`](https://github.com/mkranzlein/corpus-query/commit/519d5b9e7229a958eb7b77a44419519270d07bd8))


## v2.3.0 (2026-09-20)

### Documentation

- Describe the generalized search response and ingestion
  ([#62](https://github.com/mkranzlein/corpus-query/pull/62),
  [`806c632`](https://github.com/mkranzlein/corpus-query/commit/806c63217ab997667bef02a8fb411f6ff4d3bef0))

### Features

- Generalize the document store and search beyond transcripts
  ([#62](https://github.com/mkranzlein/corpus-query/pull/62),
  [`806c632`](https://github.com/mkranzlein/corpus-query/commit/806c63217ab997667bef02a8fb411f6ff4d3bef0))

### Testing

- Refuse a version 1 database rather than half-migrating it
  ([#62](https://github.com/mkranzlein/corpus-query/pull/62),
  [`806c632`](https://github.com/mkranzlein/corpus-query/commit/806c63217ab997667bef02a8fb411f6ff4d3bef0))


## v2.2.1 (2026-09-20)

### Bug Fixes

- Probe the weights file when deciding a model is cached
  ([#53](https://github.com/mkranzlein/corpus-query/pull/53),
  [`2b159cb`](https://github.com/mkranzlein/corpus-query/commit/2b159cb39a19f17a091001de9ca593c26c2ff9e6))


## v2.2.0 (2026-09-20)

### Features

- Add scripts/fetch_models.py to pre-fetch model weights
  ([#52](https://github.com/mkranzlein/corpus-query/pull/52),
  [`df3fb47`](https://github.com/mkranzlein/corpus-query/commit/df3fb479f54807e5c6bf0b6b42b11681a76aef41))


## v2.1.0 (2026-09-20)

### Features

- **infra**: Deny Bedrock access once spend reaches the budget
  ([#50](https://github.com/mkranzlein/corpus-query/pull/50),
  [`cc56e5d`](https://github.com/mkranzlein/corpus-query/commit/cc56e5d3b4b71c2e91e4fae95b9adf0281f63302))


## v2.0.0 (2026-09-20)

### Bug Fixes

- **infra**: Scope the policy to one model and keep it replaceable
  ([#49](https://github.com/mkranzlein/corpus-query/pull/49),
  [`b1a1065`](https://github.com/mkranzlein/corpus-query/commit/b1a1065be6b6c3753fd259d6f71e24dc24ac2309))

### Chores

- Retire the Bedrock project provisioning
  ([#49](https://github.com/mkranzlein/corpus-query/pull/49),
  [`b1a1065`](https://github.com/mkranzlein/corpus-query/commit/b1a1065be6b6c3753fd259d6f71e24dc24ac2309))

### Features

- Call Claude Sonnet 4.6 on bedrock-runtime
  ([#49](https://github.com/mkranzlein/corpus-query/pull/49),
  [`b1a1065`](https://github.com/mkranzlein/corpus-query/commit/b1a1065be6b6c3753fd259d6f71e24dc24ac2309))


## v1.7.1 (2026-09-20)

### Bug Fixes

- **infra**: Allow the API key to present itself
  ([#47](https://github.com/mkranzlein/corpus-query/pull/47),
  [`facbbd4`](https://github.com/mkranzlein/corpus-query/commit/facbbd4b1111a87765c2b10e13ab87d815b2fe7a))

### Documentation

- Invoke scripts by path rather than as modules
  ([#46](https://github.com/mkranzlein/corpus-query/pull/46),
  [`785ced2`](https://github.com/mkranzlein/corpus-query/commit/785ced2b464609a7685e362d0cf08b25df53b449))


## v1.7.0 (2026-09-20)

### Bug Fixes

- Close the store when the API refuses to start
  ([#43](https://github.com/mkranzlein/corpus-query/pull/43),
  [`22036f8`](https://github.com/mkranzlein/corpus-query/commit/22036f8af39b0e1c50aa3b4644fb5f0a5a093429))

### Documentation

- Rewrite the README for someone querying the corpus
  ([#43](https://github.com/mkranzlein/corpus-query/pull/43),
  [`22036f8`](https://github.com/mkranzlein/corpus-query/commit/22036f8af39b0e1c50aa3b4644fb5f0a5a093429))

- Say the database is not committed before the start command
  ([#43](https://github.com/mkranzlein/corpus-query/pull/43),
  [`22036f8`](https://github.com/mkranzlein/corpus-query/commit/22036f8af39b0e1c50aa3b4644fb5f0a5a093429))

### Features

- Add a serve entry point for the query API
  ([#43](https://github.com/mkranzlein/corpus-query/pull/43),
  [`22036f8`](https://github.com/mkranzlein/corpus-query/commit/22036f8af39b0e1c50aa3b4644fb5f0a5a093429))

- Add the /search API over hybrid retrieval
  ([#43](https://github.com/mkranzlein/corpus-query/pull/43),
  [`22036f8`](https://github.com/mkranzlein/corpus-query/commit/22036f8af39b0e1c50aa3b4644fb5f0a5a093429))


## v1.6.0 (2026-09-20)

### Features

- Add hybrid retrieval with RRF fusion and reranking
  ([#41](https://github.com/mkranzlein/corpus-query/pull/41),
  [`14dc0e5`](https://github.com/mkranzlein/corpus-query/commit/14dc0e564ab26585eb6fa5881f21b2ccaa1faff0))

### Testing

- Cover the default embedder and reranker wiring
  ([#41](https://github.com/mkranzlein/corpus-query/pull/41),
  [`14dc0e5`](https://github.com/mkranzlein/corpus-query/commit/14dc0e564ab26585eb6fa5881f21b2ccaa1faff0))


## v1.5.0 (2026-09-20)

### Bug Fixes

- Keep a dry run read-only rather than seeding categories
  ([#40](https://github.com/mkranzlein/corpus-query/pull/40),
  [`6985422`](https://github.com/mkranzlein/corpus-query/commit/6985422ee06765a0bf229037f647dc8ff0c4d739))

- Leave the dedupe prompt out of a dry run that skips the pass
  ([#40](https://github.com/mkranzlein/corpus-query/pull/40),
  [`6985422`](https://github.com/mkranzlein/corpus-query/commit/6985422ee06765a0bf229037f647dc8ff0c4d739))

### Documentation

- Note that enrichment is billed and needs the models extra
  ([#40](https://github.com/mkranzlein/corpus-query/pull/40),
  [`6985422`](https://github.com/mkranzlein/corpus-query/commit/6985422ee06765a0bf229037f647dc8ff0c4d739))

### Features

- Add the enrichment passes and their prompts
  ([#40](https://github.com/mkranzlein/corpus-query/pull/40),
  [`6985422`](https://github.com/mkranzlein/corpus-query/commit/6985422ee06765a0bf229037f647dc8ff0c4d739))

- Enrich ingested documents with summaries, topics, priority, and embeddings
  ([#40](https://github.com/mkranzlein/corpus-query/pull/40),
  [`6985422`](https://github.com/mkranzlein/corpus-query/commit/6985422ee06765a0bf229037f647dc8ff0c4d739))

### Testing

- Cover the enrichment pipeline and entry point
  ([#40](https://github.com/mkranzlein/corpus-query/pull/40),
  [`6985422`](https://github.com/mkranzlein/corpus-query/commit/6985422ee06765a0bf229037f647dc8ff0c4d739))

- Cover the enrichment schema, prompts, topics, dedupe, and embedding
  ([#40](https://github.com/mkranzlein/corpus-query/pull/40),
  [`6985422`](https://github.com/mkranzlein/corpus-query/commit/6985422ee06765a0bf229037f647dc8ff0c4d739))


## v1.4.0 (2026-09-20)

### Continuous Integration

- Keep torch out of CI runs ([#39](https://github.com/mkranzlein/corpus-query/pull/39),
  [`118b2aa`](https://github.com/mkranzlein/corpus-query/commit/118b2aa5b2d92b6978a2af0bb81bd0832dcd5983))

- Make the model stack an optional extra ([#39](https://github.com/mkranzlein/corpus-query/pull/39),
  [`118b2aa`](https://github.com/mkranzlein/corpus-query/commit/118b2aa5b2d92b6978a2af0bb81bd0832dcd5983))

### Features

- Add embedding, reranking models and the vector index
  ([#39](https://github.com/mkranzlein/corpus-query/pull/39),
  [`118b2aa`](https://github.com/mkranzlein/corpus-query/commit/118b2aa5b2d92b6978a2af0bb81bd0832dcd5983))


## v1.3.1 (2026-09-20)

### Bug Fixes

- Read prior-meeting summaries through the store's real schema
  ([#38](https://github.com/mkranzlein/corpus-query/pull/38),
  [`687d3b7`](https://github.com/mkranzlein/corpus-query/commit/687d3b7694da6430c0a3a50aa7e82311ed3c923e))

### Continuous Integration

- Measure coverage and upload it to Codecov
  ([#37](https://github.com/mkranzlein/corpus-query/pull/37),
  [`4f3610d`](https://github.com/mkranzlein/corpus-query/commit/4f3610d87fcbfa59fd6509c710d861d0ae46da96))

- Pin setup-uv to v10.1.0, which has no floating major tag
  ([#35](https://github.com/mkranzlein/corpus-query/pull/35),
  [`aa14c50`](https://github.com/mkranzlein/corpus-query/commit/aa14c504450dc75a4e8fc20d84dd6c9c72bf1dd0))

- Relock for 1.3.0, the version the release just published
  ([#35](https://github.com/mkranzlein/corpus-query/pull/35),
  [`aa14c50`](https://github.com/mkranzlein/corpus-query/commit/aa14c504450dc75a4e8fc20d84dd6c9c72bf1dd0))

- Relock on release so CI can install with --locked
  ([#35](https://github.com/mkranzlein/corpus-query/pull/35),
  [`aa14c50`](https://github.com/mkranzlein/corpus-query/commit/aa14c504450dc75a4e8fc20d84dd6c9c72bf1dd0))

- Run pytest in CI and as a pre-commit hook
  ([#35](https://github.com/mkranzlein/corpus-query/pull/35),
  [`aa14c50`](https://github.com/mkranzlein/corpus-query/commit/aa14c504450dc75a4e8fc20d84dd6c9c72bf1dd0))

### Documentation

- Add the Codecov badge to the README ([#37](https://github.com/mkranzlein/corpus-query/pull/37),
  [`4f3610d`](https://github.com/mkranzlein/corpus-query/commit/4f3610d87fcbfa59fd6509c710d861d0ae46da96))

- Read merged branches line by line in the cleanup sweep
  ([#36](https://github.com/mkranzlein/corpus-query/pull/36),
  [`b85dd28`](https://github.com/mkranzlein/corpus-query/commit/b85dd289ff08aba9be1695d2cbb5509c7af80a87))


## v1.3.0 (2026-09-20)

### Documentation

- Sweep leftover agent placeholder branches
  ([#32](https://github.com/mkranzlein/corpus-query/pull/32),
  [`ffb728d`](https://github.com/mkranzlein/corpus-query/commit/ffb728d8d08e4afa326a81842d6dd345eae5f7f9))

- **transcripts**: Mention the parser in the package docstring
  ([#33](https://github.com/mkranzlein/corpus-query/pull/33),
  [`a7ca76c`](https://github.com/mkranzlein/corpus-query/commit/a7ca76c087a52f2a04e105c74e9db306f20144ed))

### Features

- Parse and chunk transcripts into the document store
  ([#33](https://github.com/mkranzlein/corpus-query/pull/33),
  [`a7ca76c`](https://github.com/mkranzlein/corpus-query/commit/a7ca76c087a52f2a04e105c74e9db306f20144ed))

- **ingest**: Chunk a transcript into overlapping turn windows
  ([#33](https://github.com/mkranzlein/corpus-query/pull/33),
  [`a7ca76c`](https://github.com/mkranzlein/corpus-query/commit/a7ca76c087a52f2a04e105c74e9db306f20144ed))

- **ingest**: Write parsed transcripts into the document store
  ([#33](https://github.com/mkranzlein/corpus-query/pull/33),
  [`a7ca76c`](https://github.com/mkranzlein/corpus-query/commit/a7ca76c087a52f2a04e105c74e9db306f20144ed))

- **transcripts**: Move the transcript parser into the package
  ([#33](https://github.com/mkranzlein/corpus-query/pull/33),
  [`a7ca76c`](https://github.com/mkranzlein/corpus-query/commit/a7ca76c087a52f2a04e105c74e9db306f20144ed))


## v1.2.0 (2026-09-20)

### Bug Fixes

- **store**: Let summary chunks omit a turn range and record embedding provenance
  ([#27](https://github.com/mkranzlein/corpus-query/pull/27),
  [`d0a46f8`](https://github.com/mkranzlein/corpus-query/commit/d0a46f8261f2c75475f77488df35e509062a7944))

### Documentation

- Record the planted imperfections and keep the corpus out of git
  ([#28](https://github.com/mkranzlein/corpus-query/pull/28),
  [`145f5ad`](https://github.com/mkranzlein/corpus-query/commit/145f5ade272a359921ff93f8025b724fce64bcaf))

### Features

- Add the batched transcript generator and its prompt
  ([#28](https://github.com/mkranzlein/corpus-query/pull/28),
  [`145f5ad`](https://github.com/mkranzlein/corpus-query/commit/145f5ade272a359921ff93f8025b724fce64bcaf))

- **scripts**: Add the batched transcript generator
  ([#28](https://github.com/mkranzlein/corpus-query/pull/28),
  [`145f5ad`](https://github.com/mkranzlein/corpus-query/commit/145f5ade272a359921ff93f8025b724fce64bcaf))

- **store**: Add the SQLite document store schema
  ([#27](https://github.com/mkranzlein/corpus-query/pull/27),
  [`d0a46f8`](https://github.com/mkranzlein/corpus-query/commit/d0a46f8261f2c75475f77488df35e509062a7944))

- **transcripts**: Add the generation prompt, slugs, and the summary read
  ([#28](https://github.com/mkranzlein/corpus-query/pull/28),
  [`145f5ad`](https://github.com/mkranzlein/corpus-query/commit/145f5ade272a359921ff93f8025b724fce64bcaf))

- **transcripts**: Give a meeting a length and count its transcript words
  ([#28](https://github.com/mkranzlein/corpus-query/pull/28),
  [`145f5ad`](https://github.com/mkranzlein/corpus-query/commit/145f5ade272a359921ff93f8025b724fce64bcaf))

### Refactoring

- **transcripts**: Drop the meeting length field
  ([#28](https://github.com/mkranzlein/corpus-query/pull/28),
  [`145f5ad`](https://github.com/mkranzlein/corpus-query/commit/145f5ade272a359921ff93f8025b724fce64bcaf))


## v1.1.0 (2026-09-20)

### Documentation

- Confirm signing service verification and fix worktree cleanup order
  ([#22](https://github.com/mkranzlein/corpus-query/pull/22),
  [`2fb254e`](https://github.com/mkranzlein/corpus-query/commit/2fb254e9d0173cbe2bed02447afcb2e9999740b4))

- Fix README provisioning note and branch-cleanup convention
  ([#22](https://github.com/mkranzlein/corpus-query/pull/22),
  [`2fb254e`](https://github.com/mkranzlein/corpus-query/commit/2fb254e9d0173cbe2bed02447afcb2e9999740b4))

- Force worktree removal and tighten the cleanup snippet
  ([#22](https://github.com/mkranzlein/corpus-query/pull/22),
  [`2fb254e`](https://github.com/mkranzlein/corpus-query/commit/2fb254e9d0173cbe2bed02447afcb2e9999740b4))

### Features

- Reject a meeting that names someone who was not there
  ([#23](https://github.com/mkranzlein/corpus-query/pull/23),
  [`3bb3972`](https://github.com/mkranzlein/corpus-query/commit/3bb397206576cab7d4d3bd9452fd6c4d96683889))

- **transcripts**: Add meeting schema, markdown renderer, and roster loader
  ([#23](https://github.com/mkranzlein/corpus-query/pull/23),
  [`3bb3972`](https://github.com/mkranzlein/corpus-query/commit/3bb397206576cab7d4d3bd9452fd6c4d96683889))

### Testing

- **transcripts**: Cover the schema, the renderer, and the roster loader
  ([#23](https://github.com/mkranzlein/corpus-query/pull/23),
  [`3bb3972`](https://github.com/mkranzlein/corpus-query/commit/3bb397206576cab7d4d3bd9452fd6c4d96683889))


## v1.0.1 (2026-09-20)

### Bug Fixes

- **ci**: Skip the branch guard and drop the deprecated action
  ([#21](https://github.com/mkranzlein/corpus-query/pull/21),
  [`e158df4`](https://github.com/mkranzlein/corpus-query/commit/e158df4867bc4c9ce2ec202ae045b087375241a0))

### Chores

- Block commits made directly on main ([#16](https://github.com/mkranzlein/corpus-query/pull/16),
  [`51d8aad`](https://github.com/mkranzlein/corpus-query/commit/51d8aad1ddb2faa79121cfe056648012794cdbfd))

- Have implementers commit and push as they go
  ([#20](https://github.com/mkranzlein/corpus-query/pull/20),
  [`832e14e`](https://github.com/mkranzlein/corpus-query/commit/832e14e13f6892a57d36feb59f187a54286cea3b))

### Documentation

- Describe the release pipeline and the main-branch guard
  ([#17](https://github.com/mkranzlein/corpus-query/pull/17),
  [`8a2cf34`](https://github.com/mkranzlein/corpus-query/commit/8a2cf346d79c942c35a556a7af0e54bf1f0822d2))


## v1.0.0 (2026-09-20)

- Initial Release
