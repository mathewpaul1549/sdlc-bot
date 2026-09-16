import ollama


class TestGenerator:
    def __init__(self):
        self.model = "qwen2.5-coder:7b"

    def generate_tests(self, code: str, requirement: str) -> str:
        prompt = f"""You are an expert Python test engineer.
Based on the following code and requirement, generate pytest test cases.
Do NOT include any import statements for the function being tested — assume it is already defined in the same file.
Every pytest fixture you use must be declared as a parameter of the test function that uses it.
In particular, a test that captures stdout must be written as `def test_x(capsys):` — never
reference capsys (or tmp_path, monkeypatch, etc.) without taking it as a parameter.
Prefer asserting on return values; only capture stdout when the behaviour under test is the printed output.
Only return the pytest code, nothing else.

Code to test:
{code}

Requirement:
{requirement}

Generate pytest test cases:"""

        response = ollama.chat(
            model=self.model,
            messages=[{"role": "user", "content": prompt}]
        )
        tests = response["message"]["content"]
        tests = tests.replace("```python", "").replace("```", "").strip()
        return tests

if __name__ == "__main__":
        generator = TestGenerator()
        code = """
    def validate_email(email):
        import re
        regex = r'^\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        if email == "":
            return False
        if re.fullmatch(regex, email):
            return True
        return False
    """
        requirement = "Validate email address format"
        print(generator.generate_tests(code, requirement))