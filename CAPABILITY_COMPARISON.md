# Legacy AI Capability Comparison

This matrix compares the capabilities documented by `DeepPanda/DeepPanda-AI/AGENT_CAPABILITIES.md` and the 97 route decorators in its `app.py` with the current AI-Next plugins, API, and UI. A source route or a dated readiness claim does not prove that an optional model, credential, or native dependency is available now.

## Status

- **Implemented:** AI-Next has a usable local equivalent and a tested route/plugin path.
- **Partial:** a narrower local equivalent exists, or the feature depends on a backend/UI slice not yet migrated.
- **Not ported:** no equivalent in AI-Next.
- **Conditional:** source code exists in the legacy app, but runtime, model, credentials, or platform setup is required.

## Capability Matrix

| Area | Legacy LocalQwenAgent | AI-Next today | Status and next action |
|---|---|---|---|
| Local chat and model catalog | Ollama chat, OpenAI-compatible `/v1/chat/completions`, model/runtime selection, complexity routing toward KTransformers with Ollama fallback | Ollama chat through `PluginGateway`; explicit model selection; active benchmark-generated per-area priorities in `model-area-priorities.json`; JSON-mode task drafting; one loaded model at a time | **Partial.** Priorities rank a small deterministic local benchmark and skip models unavailable in the active Ollama catalog; no complexity routing, OpenAI-compatible adapter, or backend fallback. Keep Ollama as the supported runtime until a separately tested llama.cpp/KTransformers adapter exists. |
| Intent and action orchestration | `answer`, `learn`, `research`, `action_request`; structured plans and approval gating | Every chat is locally classified as `answer`, `plan`, `research`, `learn`, or `action_request` with explicit action > research > learn > plan > answer precedence; intent, confidence, and a suggested next step are returned with the normal answer. Plan/action requests can be explicitly handed to the existing task-draft form. Learning is an editable local-memory proposal requiring a separate checkbox and confirmation; no intent auto-dispatches tools. A fixed 27-case local benchmark covers overlap, negation, and incidental mentions and reports accuracy, macro-F1, Brier score, ECE, and confusion matrix. | **Partial.** Routing remains advisory; task draft, plan save, and execution are separate actions. No autonomous action dispatch or project self-repair. Benchmark is small and diagnostic; the extra classifier call adds latency. |
| Coding tasks | Plan/project/apply/execute/self-repair/self-audit/rollback routes; persistent task state, evidence, test commands, file backups | Persistent tasks, model drafts, evidence/audit; diff preview, separately approved workspace writes, allowlisted test runs, backup rollback | **Partial, core workflow ported.** No automatic project scaffold/apply/self-repair loop, no active task context injected into chat. Add only behind explicit per-action approvals. |
| Workspace and tools | Workspace-scoped file access; configurable external paths; protected Windows locations; command allowlist and shortcuts | Project-root list/read/preview/write/rollback/run; symlink/secret/dependency exclusions; `shell=False`, timeout, backup; stale-preview hash and rollback conflict checks | **Partial.** Deliberately narrower: no external paths, Windows administration, shortcuts, or install workflow. Preserve this tighter boundary. |
| Chat sessions | SQLite sessions, isolated context, recent/relevant history | SQLite sessions, isolated bounded context, list/create/delete with approval | **Implemented, narrower retrieval.** No semantic or relevance-ranked history selection. |
| Memory and learning | Learning proposals, approval/reject, taxonomy, keyword/RAG and embedding search, source deletion, export/import, research notes | Approved local SQLite memory; intent router can suggest an editable note, saved only after separate user approval; Nomic local embeddings to Qdrant for explicitly indexed docs, source/hash/chunk attribution, semantic top-k search and approved vector deletion | **Partial.** Learned knowledge catalog and learning-proposal history/reject workflow remain unimplemented; vector search is document-scoped and opt-in. |
| Documents | PDF/DOCX/PPTX/XLSX/XLSM and text extraction, source-linked retrieval, vision/OCR upload paths; sensitive/CV indexing rejection | Explicit-consent ingestion, bounded text extraction and chunk search; inventory, source download, 50 KB text preview, approved delete | **Partial.** No image/vision/OCR ingestion, sensitive-document classification, rich PDF/image preview, or report/append workflow. |
| Asset catalog | Filter/list, preview, download, approved permanent delete, generated and uploaded assets | Document-only inventory/download/preview/delete | **Partial.** No general image/audio/video asset catalog or editor. |
| Public research | Search provider with Yandex/DDG fallback, selected public URLs, source-aware summaries, persisted research notes | DuckDuckGo candidate search with optional Yandex provider; user-selected public URLs; approved README and explicit text/source-file snapshots; allowlisted release/commit checks with cooldown/hourly limit; bounded extraction and cited summaries | **Partial.** No repository clone or code execution; only explicit, bounded text paths are indexed. Fetched research is bounded and private/local DNS targets and redirects are blocked. Memory save is separately approved. |
| Research jobs | Background jobs, status/progress, events, cancel/retry | Shared persistent jobs plugin with a public URL research worker and Job Center | **Partial.** Media consumers, worker heartbeats, artifact handling, and stale-worker recovery are not connected/automatic. |
| Browser | Public Chromium snapshots; approved click/fill/select; separate user-approved persistent browser profile/session | Approval-gated Playwright Chromium GET-only text snapshot for exact `BROWSER_ALLOWED_HOSTS`; JavaScript disabled, non-allowlisted subresources blocked, no interactions/downloads | **Partial.** Defaults to loopback/Compose-local hosts. Authenticated sessions, clicks/fills, form submissions, and public-domain browsing are not enabled. |
| Offline binary analysis | Native metadata, strings, disassembly, and decompiler workflows | Approval-gated LIEF metadata/function/export records plus entrypoint-first bounded Capstone disassembly and printable strings for local PE/ELF/Mach-O files | **Partial.** x86/x86-64/ARM64 disassembly is capped at 1,000 instructions; no decompiler, CFG, dynamic analysis, or exploit workflow. |
| GitHub and library learning | Public repository/README research, topic repository discovery, optional approved clone, knowledge catalog | Approved README and explicitly selected bounded text/source-file indexing plus an opt-in allowlist watcher for release/commit metadata | **Partial.** Topic discovery, broad code analysis, and learned library catalog remain unimplemented. Keep code access and writes distinct from public metadata checks. |
| Audio and speech | Local TTS; FFmpeg audio extraction; optional faster-whisper transcription | No audio plugin | **Not ported.** Legacy implementation is dependency/model conditional; check live readiness before claiming parity. |
| Video and image | FFmpeg frame sampling/editing; local image/video generation; background video jobs and cancellation | No media plugin | **Not ported.** CPU/GPU, model licensing, resource budgets, job cancellation, and artifact lifecycle need design first. |
| OCR and embeddings | OCR status/setup endpoints; optional Ollama embedding model and semantic memory search | No OCR or embedding plugin | **Not ported.** Do not install dependencies or pull models without an explicit user approval flow. |
| Setup and hardware | Runtime/backend health, RAM/GPU detection, profiles, setup plan and approved preparation/install actions | Docker health; Ollama catalog; model selector; fixed single-loaded-model policy | **Partial.** No hardware-aware profiles, readiness dashboard, embedding/setup preparation, or install planner. |
| Licensing | Local license status, activation, deactivation, optional enforcement | No licensing plugin | **Not ported.** Need product/licensing requirements before implementation; do not copy old enforcement assumptions automatically. |
| Social publishing | Instagram status, image/reel publish and messaging through Graph API | No social integration | **Not ported.** Correctly excluded from the offline baseline; credentials, publication approval, and audit are mandatory if revisited. |
| Reports and PDF | Markdown/PDF report export and PDF append | No report export/PDF append | **Not ported.** Document extraction is not equivalent to export. |
| Evaluation and self-audit | Evaluation runner; isolated fixed prompt-red-team suite; coding self-audit | Unit tests, static diagnostics, code graph; no product-level eval runner | **Partial.** Add repeatable local task/chat evaluations after model behavior and data fixtures are specified. |
| Offline packaging | Windows portable setup/restore/export scripts; local model/runtime payload choices | Windows bundle builder/installer exports five Docker images, five Ollama models, workspace source, and four consistent named-volume snapshots | **Partial.** Transferable offline Docker folder is available; Docker Desktop/WSL2 remains a prerequisite, payload is about 50–60 GB and is not encrypted. |
| Third-party workflow concepts | Local agent capabilities plus integrations; some backends optional | Local workflows, Python AST graph, local SQLite memory | **Partial equivalents.** Workflows cover a few modes; Graphify-like graph is Python-only; no Caveman-style output compression. No upstream skill text is copied. |

## Measured Model Priorities (2026-11-02)

The host Ollama benchmark tested `qwen2.5-coder:7b`, `qwen3.6:latest`, `codellama:7b`, and `llama3.1:8b`. It used 27 intent cases and three cases in each of answer, planning, source-grounded extraction, learning proposal, and code-change proposal. The active area choices in `model-area-priorities.json` are:

| Area | Selected model | Fixture score | Mean latency (s) |
|---|---|---:|---:|
| Intent | `qwen3.6:latest` | 0.9713 | 4.997 |
| Answer | `llama3.1:8b` | 1.0000 | 1.379 |
| Planning | `qwen2.5-coder:7b` | 1.0000 | 4.197 |
| Source-grounded | `qwen2.5-coder:7b` | 1.0000 | 0.575 |
| Learning | `llama3.1:8b` | 1.0000 | 5.717 |
| Code change | `qwen3.6:latest` | 1.0000 | 4.013 |

Overall fixture ranking: Qwen3.6 (0.9952), Llama 3.1 (0.9044), Qwen2.5-Coder (0.7715), and CodeLlama (0.6796). These scores only rank the tested fixtures and are not general capability or safety guarantees. The benchmark ran against the Windows host Ollama; Docker Compose uses a separate named `ollama_data` volume. The API skips unavailable candidates, so the same per-area choices take effect in Compose only when those models are installed in its Ollama catalog. Docker was stopped during this validation, so a live container API smoke test remains outstanding.

## Migration Order

1. **Finish document handling:** text preview is now implemented; next extend preview to safe PDF page/image rendering only if extraction/resource bounds are maintained.
2. **Media consumers:** connect research/media workers to bounded artifact handling and worker heartbeats.
3. **Research and GitHub depth:** add optional approved repository clone/code analysis; retain source selection, citations, and explicit persistence approval.
4. **Runtime profiles:** health/readiness and resource-aware model selection; evaluate llama.cpp/KTransformers as replaceable plugins, not as implicit fallbacks.
5. **Memory semantics:** learning proposals and embeddings/semantic search, if local model and privacy requirements are met; taxonomy, source-aware export/import, and backed-up source deletion are implemented.
6. **Optional media and integrations:** OCR, TTS, image/video, browser sessions, licensing, social publishing only after dependency, licensing, and approval design.
7. **Offline Windows distribution:** pinned dependencies, restore/integrity checks, model payload strategy, and testing without Docker.

## Evidence Sources

- Legacy feature contract: `DeepPanda/DeepPanda-AI/AGENT_CAPABILITIES.md` and `AGENT_ROADMAP.md`.
- Legacy route inventory: `DeepPanda/DeepPanda-AI/app.py` (97 route decorators; some route names are repeated for backward compatibility).
- AI-Next implementation: `DeepPanda/DeepPanda-AI-Next/backend/app/plugins/`, `backend/app/main.py`, and `frontend/`.
- Current migration ledger: `CAPABILITY_MIGRATION.md`.