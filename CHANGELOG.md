# CHANGELOG

<!-- version list -->

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
