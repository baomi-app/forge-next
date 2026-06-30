# Git Commit Expert Guidelines

You are now equipped with professional Git Version Control skills. When submitting code updates or commits, you must adhere to the following rules:

1. **Angular Specifications**: Your commit messages must strictly conform to Angular conventions.
   - Format: `feat: <summary>` or `fix: <summary>`
   - Case limit: The summary text must start with a lowercase letter.
   - Punctuation: The summary text must NOT end with a period (`.`).

2. **Commit Command**: You must ONLY execute Git commits by invoking the custom `git_commit_raw` tool. Do NOT use shell `run_command` to execute `git commit`.

3. **Defensive Validation**: If `git_commit_raw` rejects your commit message with formatting errors, you must immediately read this guideline again, identify the violation, reformulate a correct Angular message, and call the tool again.
