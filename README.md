# Agentic AI SDLC Bot

A LangGraph agent that turns a plain-English requirement into tested Python code and
pushes it to GitHub. Retrieval-augmented: you can upload a requirements document, and
the agent grounds generation in the relevant excerpts. Everything runs locally against
[Ollama](https://ollama.com) — no API keys beyond a GitHub token.

## How it works

```
retrieve ──▶ generate_code ──▶ validate ──┬──▶ generate_tests ──▶ run_tests ──┬──▶ push ──▶ END
                   ▲                      │                                   │
                   │                      └──▶ END (unsafe code rejected)     │
                   └──────────── retry (max 3) ◀───────────────────────────────┘
```

| Node | Module | What it does |
| --- | --- | --- |
| `retrieve` | `rag_pipeline.py` | Pulls the top-3 chunks from Chroma, scoped to a single document. Skipped if the caller already supplied context. |
| `generate_code` | `code_generator.py` | Prompts `qwen2.5-coder:7b` with the requirement + retrieved context. On a retry it also receives the previous attempt and the pytest failure, and is asked to correct that specific defect. |
| `validate` | `safety_validator.py` | Blocklist check (`os.remove`, `subprocess`, `eval(`, …). Rejection ends the run. |
| `generate_tests` | `test_generator.py` | Generates pytest cases against the code. |
| `run_tests` | `test_runner.py` | Inlines the code with the tests and runs pytest in a subprocess. |
| `push` | `github_handler.py` | Commits to `generated/output_<n>.py` (create or update). |

If tests fail the agent loops back to `generate_code`, up to 3 attempts, feeding the
pytest failure back in so each retry is a correction rather than a re-roll. Push only
happens when tests pass **and** the push checkbox is enabled.

## Prerequisites

- **Python 3.9+**
- **Ollama** running locally, with both models pulled:

  ```bash
  ollama pull qwen2.5-coder:7b   # code + test generation (~4.7 GB)
  ollama pull nomic-embed-text   # embeddings for retrieval (~274 MB)
  ```

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Create a `.env` in the project root:

```
GITHUB_TOKEN=ghp_your_token_here
GITHUB_REPO=username/repo-name
```

The token needs `repo` scope. Both are only read when pushing — you can run the whole
pipeline with the push checkbox unticked and no token configured.

## Running

```bash
streamlit run src/app.py
```

Upload a requirements document (optional), type a requirement, and run. Streamlit puts
the script's directory on `sys.path`, so the flat `from agent import ...` imports in
`src/` resolve correctly.

There is also a headless demo, run from the project root:

```bash
python src/demo.py
```

Individual modules are runnable on their own for quick checks — each has a `__main__`
block, e.g. `python src/code_generator.py`.

## Configuration

| What | Where |
| --- | --- |
| LLM model | `self.model` in `code_generator.py` and `test_generator.py` |
| Embedding model | `OllamaEmbeddings(model=...)` in `rag_pipeline.py` |
| Vector store location | `PERSIST_DIR` in `rag_pipeline.py` (defaults to `./chroma_db`) |
| Chunk size / overlap | `RecursiveCharacterTextSplitter` in `rag_pipeline.py` |
| Retrieved chunk count | `k=3` in `RAGPipeline.retrieve` |
| Last-uploaded pointer | `chroma_db/last_doc.json` (delete it to reset retrieval) |
| Max retries | `state["retries"] >= 3` in `should_retry` (`agent.py`) |
| Blocked patterns | `dangerous_patterns` in `safety_validator.py` |

`PERSIST_DIR` is anchored to the project root, so the store is the same no matter which
directory you launch from.

## Notes and known limitations

- **Generated code is inlined into the test file**, so anything at module level would run
  on import. `strip_module_level_code` in `test_runner.py` removes demo calls, stdin reads
  and `__main__` blocks first; module-level constants (a compiled regex, say) are kept
  because the functions under test may depend on them.
- **Retrieval is scoped to one document.** The Chroma store is cumulative — every upload
  adds to it — so an unfiltered search blends documents together and returns chunks from
  files uploaded in earlier sessions. Each chunk is therefore tagged with a `doc_id` (the
  SHA-256 of the source file's bytes) and `retrieve` filters on it. A run that uploads a
  file is scoped to that file; a run that does not upload falls back to the most recent
  upload, recorded in `chroma_db/last_doc.json`.
- **Document chunks are keyed by content hash**, namespaced under their `doc_id`, so
  re-uploading the same document overwrites its chunks rather than appending duplicates,
  and shared boilerplate across two documents does not collide on one row.
- **The safety validator is a substring blocklist**, not a sandbox. It will flag a
  docstring mentioning `eval(` and will miss anything obfuscated. Generated code still
  executes on your machine when tests run — review before trusting it on real input.
- **PDF uploads go through `PyPDFLoader`**, `.txt` and `.md` through `TextLoader`, chosen
  by extension in `RAGPipeline._loader_for`. Scanned/image-only PDFs yield no text — there
  is no OCR step.
- **Retries feed the pytest failure back.** `extract_failures` in `test_runner.py` trims the
  output to the FAILURES/ERRORS section (capped at 2000 chars) so the repair prompt is not
  dominated by the session header and pass list.
- **The test generator is not failure-aware.** Only the code is corrected on a retry; tests
  are regenerated from scratch each round, so a test that is itself wrong may be replaced by
  a different wrong test rather than fixed.
- **There is no test suite for the bot itself** — the generated code is tested, but the
  pipeline modules are not.

## Layout

```
src/
  app.py               Streamlit UI and entry point
  agent.py             LangGraph state machine
  rag_pipeline.py      Chroma + Ollama embeddings
  code_generator.py    Requirement -> code
  test_generator.py    Code -> pytest cases
  test_runner.py       Sandboxed pytest execution
  safety_validator.py  Blocklist check
  github_handler.py    Commit to GitHub
  demo.py              Headless pipeline run
chroma_db/             Persisted vector store
test_requirement_invoice.txt   Sample requirements document
```
