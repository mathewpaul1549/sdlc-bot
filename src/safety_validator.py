from typing import Tuple


def is_safe(code: str) -> Tuple[bool, str]:
    dangerous_patterns =["os.remove","shutil.rmtree","subprocess","eval(","exec(","sys.exit"]

    for pattern in dangerous_patterns:
        if pattern in code:
            return False, f"Unsafe code detected: {pattern}"
    return True, "Code is safe"


if __name__ == "__main__":
    safe_code = "def add(a, b):\n    return a + b"
    dangerous_code = "os.remove('important_file.txt')"

    print(is_safe(safe_code))
    print(is_safe(dangerous_code))