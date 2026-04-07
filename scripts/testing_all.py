def partition(s: str) -> list[list[str]]:
    results = []

    def is_palindrome(sub: str) -> bool:
        return sub == sub[::-1]

    def backtrack(start: int, current: list[str]):
        # Base case: consumed the whole string — valid partition found
        if start == len(s):
            results.append(current[:])
            return

        # Try every possible end index from start
        for end in range(start + 1, len(s) + 1):
            segment = s[start:end]
            if is_palindrome(segment):
                current.append(segment)
                backtrack(end, current)   # recurse on remainder
                current.pop()             # undo choice (backtrack)

    backtrack(0, [])
    return results