import ollama


class CodeGenerator:
    def __init__(self):
        self.model = "qwen2.5-coder:7b"

    def generate_code(self, requirement: str, context: str,
                      previous_code: str = "", failure_output: str = "") -> str:
        if previous_code and failure_output:
            prompt = f"""You are an expert Python developer.
Your previous attempt at this requirement failed its tests. Fix the code so the
tests pass. Change only what the failure requires — keep the same function names
and signatures, since the tests call them.
Only return the corrected Python code, nothing else.

Context: {context}

Requirement: {requirement}

Your previous attempt:
{previous_code}

The pytest failure it produced:
{failure_output}

Return the corrected Python code:"""
        else:
            prompt = f"""You are an expert Python developer.
Based on the following context and requirement, generate clean Python code.
Only return the Python code, nothing else.

Context: {context}

Requirement: {requirement}

Generate Python code:"""

        response = ollama.chat(
            model=self.model,
            messages=[{"role": "user", "content": prompt}]
        )
        code = response["message"]["content"]
        code = code.replace("```python", "").replace("```", "").strip()
        return code

if __name__ == "__main__":
        generator = CodeGenerator()
        context = "The system should allow users to login with email and password."
        requirement = "Write a Python function that validates an email address"
        print(generator.generate_code(requirement, context))