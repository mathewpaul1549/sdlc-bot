import os
from github import Github
from dotenv import load_dotenv

load_dotenv()

class GitHubHandler:
    def __init__(self, repo_name: str = None):
        self.token = os.getenv("GITHUB_TOKEN")
        self.repo_name = repo_name or os.getenv("GITHUB_REPO")
        self.github = Github(self.token)
        self.repo = self.github.get_repo(self.repo_name)

    def push_code(self, code: str, filename: str, commit_message: str) -> str:
        try:
            contents = self.repo.get_contents(filename)
            self.repo.update_file(
                path=filename,
                message=commit_message,
                content=code,
                sha=contents.sha,
            )
            return f"Updated {filename} successfully"
        except Exception:
            self.repo.create_file(
                path=filename,
                message=commit_message,
                content=code,
            )
            return f"Created {filename} successfully"


if __name__ == "__main__":
    handler = GitHubHandler()
    code = """
def add(a, b):
    return a + b
"""
    result = handler.push_code(
        code=code,
        filename="generated/add.py",
        commit_message="Add: generated add function from SDLC bot"
    )
    print(result)