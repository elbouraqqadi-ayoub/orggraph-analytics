# Data sources and evaluation boundaries

`data/samples` is synthetic: the organizations and claims are demonstration data.

`data/reference` contains two short historical excerpts from primary corporate
sources, with original URLs and publication dates in adjacent `.meta` files:

- [Microsoft, 26 October 2018](https://blogs.microsoft.com/blog/2018/10/26/microsoft-completes-github-acquisition/).
- [IBM, 9 July 2019](https://uk.newsroom.ibm.com/2019-07-09-IBM-Closes-Landmark-Acquisition-of-Red-Hat-for-34-Billion-Defines-Open-Hybrid-Cloud-Future).

The excerpts were selected and their expected triples manually specified independently
of the extractor output. They are historical acquisition events, not assertions of
present ownership. They are a small held-out integration example, not a representative
benchmark of companies or free-text extraction. The rules baseline intentionally
supports these explicit acquisition phrasings; a high score on this set does not
demonstrate broad natural-language extraction accuracy.

Use `evaluation/reference_questions.json` with the separately ingested reference
corpus. Do not mix its metrics with the synthetic regression set. Source verification
date: 1 November 2026. No personal networks or non-public records are included.
