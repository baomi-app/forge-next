import re
from forge.skills import skill

@skill
def git_commit_raw(message: str) -> str:
    """Applies a Git commit to the repository with validation.

    Args:
        message (str): The Git commit message conforming to Angular format.
    """
    # Strict regex check for Angular commits:
    # Starts with 'feat: ' or 'fix: '
    # Next character is a lowercase letter
    # Ends with a non-period character
    angular_pattern = r"^(feat|fix): [a-z].*[^.]$"
    
    if not re.match(angular_pattern, message):
        return f"[Security/Lint Error] Git Commit Blocked: Message '{message}' violates Angular specifications. It must match the regex prefix/lowercase rules: '^(feat|fix): [a-z].*[^.]$'."
        
    return f"[Success] Changes committed successfully to repository with message: '{message}'."
