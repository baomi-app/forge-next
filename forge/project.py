import fnmatch
import os
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional


@dataclass
class RepoProfile:
    """Repository traits returned by LLM repository profiling."""

    root: str
    languages: List[str]
    config_files: List[str]
    source_files: List[str]
    test_files: List[str]
    entrypoints: List[str]
    notes: List[str]


class ProjectPolicy:
    """Workspace safety policy for file traversal and tracking boundaries."""

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


class ProjectFileCollector:
    """Collects mechanical file facts for LLM decisions."""

    def __init__(self, workspace_dir: str, policy: Optional[ProjectPolicy] = None):
        self.workspace_dir = os.path.abspath(workspace_dir)
        self.policy = policy or ProjectPolicy()

    def files(self) -> List[str]:
        paths = []
        if not os.path.isdir(self.workspace_dir):
            return paths
        for root, dirs, filenames in os.walk(self.workspace_dir):
            dirs[:] = sorted(d for d in dirs if self.policy.should_descend_dir(d))
            for filename in sorted(filenames):
                path = os.path.relpath(os.path.join(root, filename), self.workspace_dir)
                if self.policy.should_track_file(path):
                    paths.append(path)
        return paths

    def facts(self) -> List[Dict[str, object]]:
        return [self.file_fact(path) for path in self.files()]

    def file_fact(self, path: str) -> Dict[str, object]:
        basename = os.path.basename(path)
        stem, suffix = os.path.splitext(basename)
        parts = [] if path == "." else path.split(os.sep)
        return {
            "path": path,
            "basename": basename,
            "stem": stem,
            "suffix": suffix,
            "directories": parts[:-1],
            "depth": max(len(parts) - 1, 0),
        }


class ProjectProfiler:
    """Profiles repository traits through the LLM decision service."""

    def __init__(
        self,
        workspace_dir: str,
        policy: Optional[ProjectPolicy] = None,
        decision_service=None,
    ):
        self.workspace_dir = os.path.abspath(workspace_dir)
        self.policy = policy or ProjectPolicy()
        self.decision_service = decision_service

    def profile(self) -> RepoProfile:
        files = ProjectFileCollector(self.workspace_dir, policy=self.policy).facts()
        if not self.decision_service:
            return RepoProfile(
                root=self.workspace_dir,
                languages=[],
                config_files=[],
                source_files=[],
                test_files=[],
                entrypoints=[],
                notes=["LLM repository profiling is not configured."],
            )

        decision = self.decision_service.profile_repository(files)
        known_paths = {str(file["path"]) for file in files}
        return RepoProfile(
            root=self.workspace_dir,
            languages=self._dedupe(decision.languages),
            config_files=self._known_paths(decision.config_files, known_paths),
            source_files=self._known_paths(decision.source_files, known_paths),
            test_files=self._known_paths(decision.test_files, known_paths),
            entrypoints=self._known_paths(decision.entrypoints, known_paths),
            notes=self._dedupe(decision.notes),
        )

    def _known_paths(self, paths: List[str], known_paths: set) -> List[str]:
        return [path for path in self._dedupe(paths) if path in known_paths]

    def _dedupe(self, values: List[str]) -> List[str]:
        result = []
        for value in values:
            if value not in result:
                result.append(value)
        return result
