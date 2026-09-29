from pathlib import Path

from src.rag_pipeline import RAGPipeline
from src.agent import build_agent

# Repo-root-relative so the demo runs on a fresh clone.
REQUIREMENT_DOC = Path(__file__).resolve().parent.parent / "test_requirement_invoice.txt"

print("=" * 60)
print("AGENTIC AI SDLC BOT — LIVE DEMO")
print("=" * 60)

rag = RAGPipeline()
print("\n[1] Loading requirement document...")
doc_id, load_message = rag.load_document(str(REQUIREMENT_DOC))
print(load_message)

print("\n[2] Running full agentic pipeline...\n")

agent = build_agent()
result = agent.invoke({
    "requirement": "Write a Python function that validates an email address",
    "context": "",
    "code": "",
    "tests": "",
    "test_passed": False,
    "retries": 0,
    "result": ""
})

print("\n" + "=" * 60)
print("FINAL RESULT")
print("=" * 60)
print("\nGenerated Code:\n", result["code"])
print("\nTests Passed:", result["test_passed"])
print("\nGitHub Result:", result["result"])
print("\nRetries used:", result["retries"])