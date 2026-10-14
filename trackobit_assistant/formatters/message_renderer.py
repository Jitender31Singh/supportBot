"""Jinja-based rendering for message templates, with safe fallbacks for local development."""
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, Undefined


class MessageRenderer:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.env = Environment(loader=FileSystemLoader(str(self.root)), autoescape=False)

    def render(self, template_name: str, **context: object) -> str:
        try:
            return self.env.get_template(template_name).render(**context).strip()
        except Exception:
            return ""
