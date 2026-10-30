# ADR-0001 — AI Provider: OpenAI (not Gemini)

Back to [docs index](../README.md). Related: [01-architecture](../01-architecture.md#5-openai-resources), [ADR-0002](0002-chunking-and-citation.md).

- **Status:** Accepted (2026-10-30)
- **Deciders:** project owner

## 1. Context

The assignment lets us pick OpenAI or Google Gemini, but it fixes three things for either one:

1. Upload the Markdown files to the provider's vector store **via API** ("no UI drag-and-drop").
2. "Create the Assistant – Use OpenAI Playground UI or Google AI Studio".
3. Run the sanity check **in that UI** and take a screenshot of the answer with citations.

So the provider must let a store created through the API be attached and queried **inside its own web UI**. The API alone is not enough.

## 2. Evidence

| Fact | Label | Source |
|---|---|---|
| Gemini File Search exists, but only as an API tool (`fileSearchStores`, `file_search` tool) | DOCUMENTED | ai.google.dev/gemini-api/docs/file-search |
| The AI Studio Playground tools panel has no File Search. It has Structured outputs, Code execution, Function calling, Google Search, Google Maps, and URL context. | VERIFIED (browser check) | AI Studio UI, 2026-10-30 |
| The AI Studio Agents playground lists Google Search, URL Context, Code Execution, and Filesystem. No File Search. | DOCUMENTED | ai.google.dev/gemini-api/docs/aistudio-agents (updated 2026-08-18) |
| The Gemini whitespace chunker caps chunks at 512 words, so long articles split and lose the `Article URL:` header | DOCUMENTED | Gemini v1beta discovery document, `WhiteSpaceConfig` |
| OpenAI Playground Chat → Hosted tools → **File search** → **Attach existing vector store** → picker by name or ID | VERIFIED (manual UI check) | Owner's screenshots, 2026-10-30 |
| The OpenAI dashboard has Storage → Vector stores | VERIFIED (browser check) | Dashboard, 2026-10-30 |
| Assistants API shut down 2026-08-26; replacement is Responses + Conversations | DOCUMENTED | developers.openai.com/api/docs/deprecations |
| Reusable prompt objects (dashboard "prompts", `v1/prompts`) deprecated 2026-06-03, **shutdown 2026-11-30** | DOCUMENTED | same page |
| Static chunking `max_chunk_size_tokens` 100–4096, overlap ≤ max/2; file attributes ≤ 16 keys | DOCUMENTED | developers.openai.com/api/docs/guides/retrieval |
| No chunk count is exposed by either provider | DOCUMENTED / VERIFIED (discovery) | Provider docs and API discovery documents |
| An API-created store attaches in the picker end to end | **UNKNOWN** | Gate G1 |

## 3. Decision

Use **OpenAI**:

- A managed **Vector Store**, created and filled only by `main.py` through the API.
- The **Playground Chat** is the assistant: the verbatim system prompt plus File search, using the existing store.
- Any optional programmatic query uses the **Responses API** with `file_search`. The Assistants API is not used.

## 4. Alternatives considered

| Option | Why rejected |
|---|---|
| Gemini File Search + AI Studio | Cannot meet "set up and test in AI Studio" with an API-uploaded store (VERIFIED). |
| Gemini + an app built in AI Studio Build mode | UNKNOWN whether it can call File Search, extra hours, and it bends the assignment wording. |
| Gemini + a custom CLI or web chat for the screenshot | Breaks the Playground / AI Studio requirement. |
| OpenAI Assistants API | Shut down 2026-08-26. |

## 5. Consequences

- **Project-local stores:** the author's API key must be scoped to the same OpenAI project the Playground uses, or its picker cannot see that store (G1, [04 §1](../04-operations.md#1-configuration)). The grader's key is in a **different project**, so default sync resolves or creates a new marked store **there**, not the author's store. Neither project ID nor store ID is embedded in the image.
- **Stable marked store resolution:** `VECTOR_STORE_ID` set → retrieve it, require vector store `metadata.managed_by = "rillmark-optibot-v1"`, else fail closed. Unset → list stores in the key's project (all pages), filter by the store marker: 0 → create (named `rillmark-optibot`, with marker, no `expires_after`); 1 → reuse; >1 → fail closed. Display name is never used for matching. Listing/auth failures also fail closed; no fallback to another store. The file-attribute marker stays `managed_by = "rillmark-optibot-v1"` and is distinct from store metadata. `--init-store` is removed: sync creates when the key's project has no marked store. Reuse keeps daily delta sync and the author's Playground attachment stable; ambiguous matches stop instead of selecting a wrong store.
- **Saved prompt risk (G4):** if the Playground "New prompt" draft is saved, it is a reusable prompt object and may disappear after 2026-11-30, possibly while the reviewer is still grading. The deliverable is the **screenshot**. The README records the model, a pointer to the verbatim prompt, and the `vector_store_id`, so anyone can recreate the assistant in about 1 minute.
- **Single-turn screenshot:** a community report says file search fails on follow-up turns in the Playground ("item not found", ASSUMPTION). The YouTube check is the first turn of a fresh chat.
- **Cost (G0):** no API or Playground call can run until API credits are added. The validation cost estimate (< $0.10) is an ASSUMPTION to re-check against current pricing.
- **Lock-in:** acceptable for a take-home. `vector_store.py` is the only module that touches the SDK.
