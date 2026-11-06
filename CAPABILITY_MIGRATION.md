# AI-Next Capability Migration

This ledger tracks the capabilities documented in `DeepPanda/DeepPanda-AI/AGENT_CAPABILITIES.md` and the routes in its `app.py`. AI-Next remains the single AI product; every capability is reached through `PluginGateway`.

## Implemented

- Local Ollama chat, model catalog, and model selection.
- Docker Compose services for Ollama, FastAPI, web, Qdrant, and Redis; persistent model/application volumes plus a Windows offline Docker bundle builder, checksum-verified installer, and data-preserving remover. Docker Desktop remains an external prerequisite.
- Read-only bounded diagnostics: Python AST/Ruff and JSON/TOML/YAML syntax.
- Local SQLite memory with explicit approval for writes, imports, exports, and source deletion; project/category/source-filtered search, timeline, taxonomy, deduplicating bounded JSON import/export, source preview, and import-compatible backups before deletion. Embedding search and learning proposals remain unimplemented.
- Python AST code graph with build, symbol search, and static paths.
- Standard, plan, debug, review, audit, and minimal workflows.
- Persistent chat sessions with per-session message history, bounded model context, and approval-gated deletion.
- Workspace tools for bounded reads, write previews, approved writes with backups, rollback, and allowlisted shell-free commands.
- Coding task plans: editable local-model drafts, persistent local plans, explicit plan approval, per-step approval, validated progress transitions, evidence, audit history, a local-model numbered line-range proposal for one selected file with up to three explicit context files (30,000-character aggregate source cap, 4,096-token output cap, exact source-range validation, proposal-only), task-linked diff previews, separately approved writes, approval-gated rollback by recorded backup ID, bounded allowlisted test runs with explicit confirmation and recorded output, and a read-only verifier that requires completed steps plus passing tests after the latest workspace write or rollback.
- Documents: explicit-consent ingestion (20 MB upload cap), bounded PDF/DOCX/PPTX/XLSX and text extraction, local chunk search, inventory, indexed-ID source downloads, 50 KB text-only preview, and explicit-confirmation deletion of files plus index entries.
- Shared jobs: persistent SQLite state/events, worker claim ownership, monotonic progress, cooperative cancellation, approval-gated retry and stale-worker recovery, and Job Center UI. It is worker-neutral; public URL research is the first consumer, while media consumers are not connected.
- Public research: opt-in DuckDuckGo candidate search with optional Yandex Search API provider, user selection of 1–5 URLs, separate approved GitHub README research (up to 3 repositories), public DNS/IP and redirect checks, bounded extraction, untrusted-source prompting, source-cited local summaries, shared-job progress/results, and separately approved idempotent save to local memory. Repository cloning/code analysis and automatic memory persistence are not implemented.
- Public repository watcher: user-approved `owner/repository` allowlist, manual GitHub latest-release and latest-commit metadata checks, separate approval for a single README or up to five explicitly selected UTF-8 text/source files (1 MB/file, 3 MB total, blob-SHA dedupe, source attribution through the documents plugin), persistent cooldown/hourly local limit, and explicit removal approval. No clone, automatic path discovery, code execution, or polling.
- LangGraph static analysis: approval-gated inspect/analyze/report nodes read only an indexed text/source document, require an installed local Ollama model, treat document text as untrusted input, and return source/line-attributed bounded findings without executing code or saving reports automatically.
- Local vector knowledge: explicit document indexing with the local `nomic-embed-text:latest` 768-dimensional embedding model, bounded chunks with source/document/hash/offset metadata in Qdrant, read-only top-k semantic search, idempotent reindex, and approval-gated vector deletion.
- Offline static binary analysis: explicit approval for local PE/ELF/Mach-O files up to 10 MB; LIEF headers/sections/imports plus bounded function/export records, entrypoint-first Capstone disassembly capped at 256 KB/1,000 instructions, and ASCII/UTF-16 strings capped at 500 results. x86/x86-64/ARM64 disassembly is supported; other architectures retain metadata and strings. Binaries are never executed; decompilation, CFG, dynamic analysis, exploit output, and target scanning are not implemented.
- Browser snapshots: explicit approval, exact host allowlist, GET-only, JavaScript disabled, blocked external subresources/downloads, 10,000-character text cap, no browser interactions or persistent authenticated sessions.
- Loopback-only UI/API ports; analyzers are report-only while workspace writes remain explicitly approved.

## Port Next

1. **Documents and assets:** rich media preview is not implemented; text preview is bounded to 50 KB and source download is restricted to indexed document IDs.
2. **Media consumers:** connect FFmpeg/Whisper workers to the shared jobs core; add worker heartbeats, bounded artifacts, and consumer-specific progress reporting.
3. **Research discovery:** add optional approval-gated repository clone/code analysis; retain user source selection, citations, URL validation, and private/local target blocking.
4. **Runtime routing:** health-aware Ollama model profiles now; separately evaluate a Windows/WSL KTransformers runtime without importing its source tree.
5. **Offline packaging:** the Docker offline bundle, model payload, integrity checks, and restore path are implemented; a Docker-Desktop-free native Windows installer remains unimplemented.
6. **Memory semantics:** add learning proposals and local embedding search only after model, privacy, and resource requirements are specified. Taxonomy, filtered lookup, import/export, and backed-up source deletion are implemented.
7. **Optional integrations:** OCR, image/video generation, VS Code bridge, and publishing remain opt-in and approval-gated.

## Compatibility Policy

- Superpowers/Ponytail concepts are represented by locally authored workflow modes; upstream skill text is not copied.
- Graphify's role is implemented by the local Python AST graph; current support is Python-only.
- Claude-Mem's role is implemented by the local SQLite memory plugin, not its Claude-specific hook/worker stack.
- Caveman-style local output compression is not implemented yet; hosted routing/telemetry are excluded from the offline baseline.
- Keep third-party additions separate, pinned, license-attributed, and replaceable behind the gateway.

## Acceptance Rules

- Run the existing suite after each capability slice; report skipped tests as unverified.
- Every write, install, export, delete, publication, and model pull needs an explicit approval boundary.
- Every analyzer has a workspace boundary, symlink policy, resource budget, and report-only default.
- Offline mode must not silently fall back to a hosted model, search provider, memory sync, or telemetry.