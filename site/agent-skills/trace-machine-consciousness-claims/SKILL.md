---
name: trace-machine-consciousness-claims
description: Check where a statement about Joscha Bach and Hikari Sorensen's Machine Consciousness Hypothesis comes from, using the public claims ledger and citations on the-mind.xyz. Use when someone asks whether Bach or the paper really said something, wants a citation, page or timestamp for an idea, or needs to separate the primary paper from supporting talks, the site's own synthesis and open questions.
compatibility: Needs HTTPS access to the-mind.xyz. No account, API key or script execution.
---

# Trace a claim about the Machine Consciousness Hypothesis

the-mind.xyz keeps a public claims ledger and cites its explanations with source locators. Use them to tell the user where a statement comes from and how strong its basis is. The site is an independent project, not affiliated with or endorsed by Joscha Bach.

## Public resources

Everything here is a static, public, read-only file. No login, key or form is involved.

- Claims ledger: https://the-mind.xyz/claims/index.md
- Sources and their roles: https://the-mind.xyz/sources/index.md
- Glossary definitions with locators: https://the-mind.xyz/glossary/index.md
- All pages: https://the-mind.xyz/llms.txt. Add `index.md` to any page URL for its Markdown version, or request the page with `Accept: text/markdown`.

## How the ledger is written

Each claim has this shape:

```markdown
## [CLM-0002](https://the-mind.xyz/claims/#clm-0002)

**Consciousness is not synonymous with self, mind, or intellect.**

Basis: **Primary paper**.

Supports:

- [Primary paper: Machine Consciousness Hypothesis](https://cimc.ai/cimcHypothesis.pdf#page=13) @ p12
```

- `Basis` uses the ledger's evidence legend:
  - **Primary paper:** a claim, definition, model or argument drawn from *The Machine Consciousness Hypothesis*.
  - **Supporting source:** a talk or interview used to clarify or extend a formulation.
  - **Project synthesis:** the site's own source-grounded bridge across passages. It is not a direct statement by Bach or Sorensen.
  - **Open question:** the sources and current evidence do not settle the matter.
- Keep any qualifier after the label, such as "this is explicitly a hypothesis" or "this is an argument, not a validation result". Some entries add `Open question:` or `Clarification:` lines. Report them too.
- "Supports" shows provenance and argumentative support. It does not mean independent replication, empirical validation or scientific consensus.
- Link a claim with its anchor, for example https://the-mind.xyz/claims/#clm-0002.

## Locators

- `@ p12` or `p. 12` is the printed page number. In links to the two PDFs on cimc.ai (the primary paper and the CIMC whitepaper), `#page=13` is the physical PDF page: these PDFs have one unnumbered page before page 1, so the link is one higher. This is expected; do not change it.
- `@ 00:32:16` or `32:16` is a time in a recording. The link (`?t=1936` or `&t=1936s`) opens the recording at that time.
- `00:00` or `@ 00:00:00` on an essay or web page, and `whole transcript`, mean the whole source, not a position in it. Do not invent a finer locator.

## Steps

1. Restate the statement to check in one sentence and note its key terms.
2. Fetch the claims ledger. Look for a claim with the same meaning, not only the same words.
3. If a claim matches, report its ID and link, its basis label with any qualifier, and its supports with locators.
4. If no claim matches, find the most relevant page through `llms.txt` and read the citations next to the matching passage. Use the glossary for definitions.
5. Where you can, open the original source at the locator and check that it says what the site says. State exactly what you checked. If you could not open or check the source, for example a video, say that the attribution rests on the site's citation.
6. Give a verdict. Combine two when needed, for example "contradicted by the site, which cites the primary paper, p. 12":
   - **In the primary paper**, with the page.
   - **In a supporting source**, with the talk, interview or essay and its time or page.
   - **The site's synthesis**, not a direct statement by Bach or Sorensen.
   - **Open question** on the site.
   - **Not found on the site.** This does not show that Bach never said it, only that this site does not cite it.
   - **Contradicted by the site**, when a page says the opposite. Quote the page briefly and link it.

## Source roles

The Sources page and the "Source details" list at the end of each page give each source's role (Primary source, Supporting source or Program context), type, author or channel and publication date. Under "New reading and listening", the Sources page says how far each item has been reviewed. Do not treat an item there as support for a claim unless the ledger or a page cites it for that claim.

## Archived V1 reader

The archived reader (https://the-mind.xyz/reader/) labels passages `[BACH]`, `[SYNTH]`, `[NOTE]` or `[OPEN]`. Prefer the current pages and the ledger. Do not quote a `[BACH]` passage as Bach's own words unless its cited source confirms the wording.

## Limits

- Report what the site and its sources say. Do not add new attributions.
- Keep quotations short and attributed. Quoted and linked third-party material keeps its owners' terms. The site's `robots.txt` declares the Content Signals `search=yes, ai-input=yes` and sets no training preference.
- If the user finds an error, they can use the "Suggest a clarification" link at the end of each page. Let the user decide whether to report it.
- Fetch only what the task needs. If a request is blocked, rate-limited or challenged, stop and tell the user. Do not work around it.
