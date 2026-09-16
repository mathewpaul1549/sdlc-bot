import ast
import builtins
import re
import subprocess
import sys
import tempfile
import os

_SECTION = re.compile(r"^=+ (?:FAILURES|ERRORS) =+$", re.M)
_SUMMARY = re.compile(r"^=+ short test summary info =+$", re.M)


def extract_failures(result: dict, max_chars: int = 2000) -> str:
    """Pull the diagnostic part out of a pytest run.

    Feeding the whole stdout back to the model wastes most of the prompt on the
    session header and the pass list; the FAILURES/ERRORS section is the part
    that says what actually went wrong.
    """
    output = result.get("output") or ""
    start = _SECTION.search(output)
    if start:
        end = _SUMMARY.search(output, start.end())
        section = output[start.start():end.start() if end else len(output)]
    else:
        # Collection crashed before pytest wrote a report section.
        section = (result.get("error") or "").strip() or output

    section = section.strip()
    if len(section) > max_chars:
        section = section[:max_chars] + "\n... (truncated)"
    return section


def _is_main_guard(node: ast.If) -> bool:
    test = node.test
    return (
        isinstance(test, ast.Compare)
        and isinstance(test.left, ast.Name)
        and test.left.id == "__name__"
        and len(test.ops) == 1
        and isinstance(test.ops[0], ast.Eq)
    )


ASSIGN_TYPES = (ast.Assign, ast.AnnAssign, ast.AugAssign)


def _reads_stdin(node: ast.AST) -> bool:
    """True if the statement reads stdin, which is fatal under pytest capture."""
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            func = sub.func
            if isinstance(func, ast.Name) and func.id == "input":
                return True
            if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Attribute):
                if func.value.attr == "stdin":
                    return True
    return False


def _assigned_names(node: ast.AST) -> set:
    targets = getattr(node, "targets", None) or [getattr(node, "target", None)]
    return {t.id for t in targets if isinstance(t, ast.Name)}


def _value_names(node: ast.AST) -> set:
    """Names read by an assignment's value expression."""
    value = getattr(node, "value", None)
    if value is None:
        return set()
    return {n.id for n in ast.walk(value) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}


def strip_module_level_code(code: str) -> str:
    """Drop top-level statements that would execute on import.

    The generated code is inlined into the test file, so anything at module
    level runs the moment pytest imports it. Demo scaffolding the model likes
    to append — print(...)/login(...) calls, or a stray input() — then hangs or
    crashes the run regardless of whether the functions under test are correct.

    Definitions and imports are always kept. Assignments are kept only when
    they look like constants: module-level state such as a compiled regex is
    needed by the functions under test, but an assignment that reads stdin or
    calls the code under test is demo scaffolding.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        # Let pytest surface the real syntax error rather than masking it here.
        return code

    defined_here = {n.name for n in tree.body
                    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}

    kept = []
    for node in tree.body:
        if isinstance(node, ast.Expr):
            # Keep docstrings, drop bare expressions (demo calls, print, input).
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                kept.append(node)
            continue
        if isinstance(node, ast.If) and _is_main_guard(node):
            continue
        if isinstance(node, ASSIGN_TYPES):
            # Reading stdin raises OSError under pytest capture, and invoking a
            # function defined in this file is demo usage, not a constant.
            if _reads_stdin(node) or (_value_names(node) & defined_here):
                continue
        kept.append(node)

    # Dropping those assignments can strip a name that a later assignment still
    # reads (email = input(...) then result = login(email, ...)), so cascade
    # until nothing references a module-level name that no longer exists.
    safe_names = set(dir(builtins))
    for node in kept:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            safe_names |= {(a.asname or a.name).split(".")[0] for a in node.names}
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            safe_names.add(node.name)

    changed = True
    while changed:
        changed = False
        bound = safe_names | {n for node in kept if isinstance(node, ASSIGN_TYPES)
                              for n in _assigned_names(node)}
        for node in list(kept):
            if isinstance(node, ASSIGN_TYPES) and not _value_names(node) <= bound:
                kept.remove(node)
                changed = True

    # If nothing testable survived, the input wasn't shaped the way we assumed;
    # return it untouched instead of handing pytest an empty file.
    if not any(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) for n in kept):
        return code

    tree.body = kept
    return ast.unparse(tree)


class TestRunner:
    def __init__(self):
        self.temp_dir = tempfile.mkdtemp()
    def run_tests(self, code:str, test_code: str) -> dict:
        code_file =os.path.join(self.temp_dir, "temp_code.py")
        test_file=os.path.join(self.temp_dir, "temp_tests.py")

        importable_code = strip_module_level_code(code)

        with open(code_file, "w") as f:
            f.write(importable_code)

        with open(test_file, "w") as f:
            f.write(importable_code)
            f.write("\n\n")
            f.write(test_code)

        result =subprocess.run(
            [sys.executable, "-m", "pytest", test_file, "-v"],
            capture_output=True,
            text=True
        )
        return {
            "passed": result.returncode == 0,
            "output": result.stdout,
            "error": result.stderr

        }


if __name__ == "__main__":
    runner = TestRunner()

    code = """
def add(a, b):
    return a + b
"""

    test_code = """
from temp_code import add

def test_add():
    assert add(2, 3) == 5

def test_add_negative():
    assert add(-1, 1) == 0
"""

    result = runner.run_tests(code, test_code)
    print("Passed:", result["passed"])
    print("Output:", result["output"])

