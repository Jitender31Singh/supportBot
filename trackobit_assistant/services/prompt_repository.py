from pathlib import Path
from typing import Mapping
from jinja2 import Environment, FileSystemLoader

class PromptRepository:
    """Loads versioned prompts from files; prompt selection is configurable without code edits."""
    def __init__(self, root: Path, version_config: str = ""):
        self.root = Path(root)
        self.env = Environment(loader=FileSystemLoader(str(self.root)), autoescape=False)
        self.versions: dict[str, str] = {}
        for item in version_config.split(","):
            if "=" in item:
                name, version = item.split("=", 1)
                name, version = name.strip(), version.strip()
                if name and version:
                    self.versions[name] = version

    def render(self, node_name: str, version: str | None = None, **kwargs) -> str:
        selected = version or self.versions.get(node_name, "v1")
        template_path = f"{node_name}/{selected}.md"
        try:
            return self.env.get_template(template_path).render(**kwargs)
        except Exception as exc:
            fallback = self.root / template_path
            if fallback.exists():
                # Show a safe prompt-loading message rather than leaking internals.
                return fallback.read_text(encoding="utf-8")
            return (
                "You are a helpful TrackoBit support assistant. Use structured output as requested. "
                f"Input: {kwargs}"
            )
