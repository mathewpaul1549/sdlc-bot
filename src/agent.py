

from langgraph.graph import StateGraph, END
from typing import TypedDict


from rag_pipeline import RAGPipeline
from code_generator import CodeGenerator
from safety_validator import is_safe
from test_generator import TestGenerator
from test_runner import TestRunner, extract_failures
from github_handler import GitHubHandler

class AgentState(TypedDict):
    requirement: str
    context: str
    code: str
    tests: str
    test_passed: bool
    retries: int
    result: str
    push_enabled: bool
    repo_override: str
    rejected: bool
    test_output: str

def retrieve_context(state: AgentState)  -> AgentState:
        # app.py already retrieves context for an uploaded document; don't clobber it.
        if state.get("context"):
            return state
        rag = RAGPipeline()
        state["context"] = rag.retrieve(state["requirement"])
        return state

def generate_code(state: AgentState) -> AgentState:
    generator = CodeGenerator()
    # On a retry, hand the model its previous attempt and the pytest failure so
    # it can correct the specific defect instead of re-rolling the same prompt.
    state["code"] = generator.generate_code(
        requirement=state["requirement"],
        context=state["context"],
        previous_code=state["code"] if state.get("retries") else "",
        failure_output=state.get("test_output", "") if state.get("retries") else ""
    )
    return state

def validate_code(state: AgentState) -> AgentState:
    safe, message = is_safe(state["code"])
    state["rejected"] = not safe
    if not safe:
        state["code"] =""
        state["result"] = f"Code rejected: {message}"
    return state

def generate_tests(state: AgentState) -> AgentState:
    generator = TestGenerator()
    state["tests"] = generator.generate_tests(
        code=state["code"],
        requirement=state["requirement"]
    )
    return state

def run_tests(state: AgentState) -> AgentState:
    runner = TestRunner()
    result = runner.run_tests(
        code=state["code"],
        test_code=state["tests"]
    )
    state["test_passed"] = result["passed"]
    state["test_output"] = "" if result["passed"] else extract_failures(result)
    state["retries"] = state["retries"] + 1
    return state

def push_to_github(state: AgentState) -> AgentState:
    handler = GitHubHandler(repo_name=state.get("repo_override") or None)
    push_result = handler.push_code(
        code=state["code"],
        filename=f"generated/output_{state['retries']}.py",
        commit_message=f"Auto-generated code for: {state['requirement'][:50]}"

    )
    state["result"] = push_result
    return state



def should_test(state: AgentState) -> str:
    # Rejected code is empty, so generating and running tests against it just
    # burns an LLM call and hides the rejection message. Stop here instead.
    return "end" if state.get("rejected") else "generate_tests"


def should_retry(state: AgentState) -> str:
    if state["test_passed"]:
        if state.get("push_enabled", True):
            return "push"
        else:
            return "end"
    elif state["retries"] >= 3:
        return "end"
    else:
        return "retry"

def build_agent():
    graph = StateGraph(AgentState)

    graph.add_node("retrieve", retrieve_context)
    graph.add_node("generate_code", generate_code)
    graph.add_node("validate", validate_code)
    graph.add_node("generate_tests", generate_tests)
    graph.add_node("run_tests", run_tests)
    graph.add_node("push", push_to_github)

    graph.set_entry_point("retrieve")

    graph.add_edge("retrieve", "generate_code")
    graph.add_edge("generate_code", "validate")
    graph.add_edge("generate_tests", "run_tests")

    graph.add_conditional_edges(
        "validate",
        should_test,
        {
            "generate_tests": "generate_tests",
            "end": END
        }
    )

    graph.add_conditional_edges(
        "run_tests",
        should_retry,
        {
            "push": "push",
            "retry": "generate_code",
            "end": END
        }
    )

    graph.add_edge("push", END)

    return graph.compile()


