import fnmatch
import os
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional


@dataclass
class RepoProfile:
    """Detected repository traits used by agent capabilities."""

    root: str
    languages: List[str]
    config_files: List[str]
    source_files: List[str]
    test_files: List[str]
    entrypoints: List[str]
    notes: List[str]


class ProjectPolicy:
    """Shared project rules for file classification, exclusions, and language hints."""

    exclude_dirs = {".git", "__pycache__", ".venv", ".agents", "node_modules", ".gemini"}
    checkpoint_file_patterns = {"checkpoint.json", "*_checkpoint.json"}
    generated_file_patterns = {
        ".DS_Store",
        "*.pyc",
        "*.pyo",
        "*.log",
        "*.tmp",
        "*~",
        ".vscode/*",
        ".idea/*",
        "__pycache__/*",
        "mock_trace.json",
        "verifier_trace.json",
        "temp_*/*",
    }
    test_file_patterns = {
        "test_*.py",
        "*_test.py",
        "tests/*",
        "*/tests/*",
    }
    doc_file_patterns = {
        "README.md",
        "VERSION.md",
        "AGENTS.md",
        "docs/*",
        "examples/*",
    }
    example_file_patterns = {"examples/*"}
    config_files = {
        "AGENTS.md",
        "Cargo.toml",
        "go.mod",
        "package.json",
        "pyproject.toml",
        "requirements.txt",
        "baomi.json",
    }
    code_suffixes = (".py", ".js", ".ts", ".tsx", ".go", ".rs")
    doc_suffixes = (".md", ".rst", ".txt")
    language_by_suffix = {
        ".go": "go",
        ".js": "javascript",
        ".json": "json",
        ".md": "markdown",
        ".py": "python",
        ".rs": "rust",
        ".toml": "toml",
        ".ts": "typescript",
        ".tsx": "typescript-react",
        ".txt": "text",
    }
    project_language_markers = {
        "python": ("pyproject.toml", "requirements.txt", "setup.py"),
        "node": ("package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock"),
        "go": ("go.mod",),
        "rust": ("Cargo.toml",),
    }

    def __init__(
        self,
        exclude_dirs: Optional[Iterable[str]] = None,
        exclude_file_patterns: Optional[Iterable[str]] = None,
    ):
        self.exclude_dirs = set(exclude_dirs or self.exclude_dirs)
        self.exclude_file_patterns = set(exclude_file_patterns or self.checkpoint_file_patterns)

    def should_descend_dir(self, dirname: str) -> bool:
        return dirname not in self.exclude_dirs

    def should_track_file(self, path: str) -> bool:
        return not self.matches(path, self.exclude_file_patterns)

    def is_generated_file(self, path: str) -> bool:
        return self.matches(path, self.generated_file_patterns)

    def is_test(self, path: str) -> bool:
        return self.matches(path, self.test_file_patterns)

    def is_doc(self, path: str) -> bool:
        return self.matches(path, self.doc_file_patterns) or path.endswith(self.doc_suffixes)

    def is_example(self, path: str) -> bool:
        return self.matches(path, self.example_file_patterns)

    def is_code(self, path: str) -> bool:
        return path.endswith(self.code_suffixes)

    def is_config(self, path: str) -> bool:
        return os.path.basename(path) in self.config_files

    def role(self, path: str) -> str:
        if self.is_test(path):
            return "test"
        if self.is_example(path):
            return "example"
        if self.is_doc(path):
            return "documentation"
        if self.is_config(path):
            return "config"
        if self.is_code(path):
            return "runtime"
        return "other"

    def commit_category(self, path: str) -> str:
        role = self.role(path)
        if role == "runtime":
            return "runtime code"
        if role == "config":
            return "project configuration"
        if role == "documentation":
            return "documentation"
        return role

    def language(self, path: str) -> str:
        return self.language_by_suffix.get(os.path.splitext(path)[1], "unknown")

    def matches(self, path: str, patterns: Iterable[str]) -> bool:
        basename = os.path.basename(path)
        return any(fnmatch.fnmatch(path, pattern) or fnmatch.fnmatch(basename, pattern) for pattern in patterns)

    def to_dict(self) -> Dict[str, object]:
        return {
            "exclude_dirs": sorted(self.exclude_dirs),
            "exclude_file_patterns": sorted(self.exclude_file_patterns),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, object]) -> "ProjectPolicy":
        exclude_dirs = data.get("exclude_dirs")
        exclude_file_patterns = data.get("exclude_file_patterns")
        return cls(
            exclude_dirs=exclude_dirs if isinstance(exclude_dirs, list) else None,
            exclude_file_patterns=exclude_file_patterns if isinstance(exclude_file_patterns, list) else None,
        )


class ProjectProfiler:
    """Detects lightweight repository traits from files and shared policy."""

    def __init__(self, workspace_dir: str, policy: Optional[ProjectPolicy] = None):
        self.workspace_dir = os.path.abspath(workspace_dir)
        self.policy = policy or ProjectPolicy()

    def profile(self) -> RepoProfile:
        files = self._iter_files()
        languages = self._detect_languages(files)
        config_files = [path for path in files if self.policy.is_config(path)]
        source_files = [path for path in files if self.policy.role(path) == "runtime"]
        test_files = [path for path in files if self.policy.is_test(path)]
        entrypoints = [path for path in files if self._is_entrypoint(path)]
        notes = []
        if not test_files:
            notes.append("No test files detected.")
        if not config_files:
            notes.append("No project configuration files detected.")

        return RepoProfile(
            root=self.workspace_dir,
            languages=languages,
            config_files=config_files,
            source_files=source_files,
            test_files=test_files,
            entrypoints=entrypoints,
            notes=notes,
        )

    def _iter_files(self) -> List[str]:
        files = []
        if not os.path.isdir(self.workspace_dir):
            return files
        for root, dirs, filenames in os.walk(self.workspace_dir):
            dirs[:] = sorted(d for d in dirs if self.policy.should_descend_dir(d))
            for filename in sorted(filenames):
                path = os.path.relpath(os.path.join(root, filename), self.workspace_dir)
                if self.policy.should_track_file(path):
                    files.append(path)
        return files

    def _detect_languages(self, files: List[str]) -> List[str]:
        languages = set()
        file_set = set(files)
        for language, markers in self.policy.project_language_markers.items():
            if any(marker in file_set for marker in markers):
                languages.add(language)

        if any(path.endswith(".py") for path in files):
            languages.add("python")
        if any(path.endswith((".js", ".ts", ".tsx")) for path in files):
            languages.add("node")
        if any(path.endswith(".go") for path in files):
            languages.add("go")
        if any(path.endswith(".rs") for path in files):
            languages.add("rust")

        return sorted(languages)

    def _is_entrypoint(self, path: str) -> bool:
        basename = os.path.basename(path)
        if path.startswith("examples/demo_"):
            return True
        return basename in {"main.py", "app.py", "cli.py", "run.py"}
