"""Prompt loading and rendering for AI models."""

import hashlib
import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Optional, Tuple

from src.core.config import settings


class PromptLoader:
    """
    Loads and renders prompts for AI model evaluation.

    Supports the core + wrapper pattern:
    - Core prompt: Shared decision logic
    - Wrapper prompt: Provider-specific formatting instructions
    """

    def __init__(self, prompts_dir: Optional[str] = None):
        self.prompts_dir = Path(prompts_dir or "prompts")

    @lru_cache(maxsize=32)
    def _load_file(self, filename: str) -> str:
        """Load a prompt file from disk."""
        filepath = self.prompts_dir / filename
        if not filepath.exists():
            raise FileNotFoundError(f"Prompt file not found: {filepath}")
        return filepath.read_text(encoding="utf-8")

    def load_core_prompt(self, version: str = "v1") -> str:
        """Load the core decision logic prompt."""
        return self._load_file(f"core_decision_{version}.md")

    def load_wrapper_prompt(self, model_name: str, version: str = "v1") -> str:
        """Load a model-specific wrapper prompt."""
        return self._load_file(f"{model_name}_wrapper_{version}.md")

    def render_prompt(
        self,
        model_name: str,
        enriched_event: dict,
        constraints: dict,
        core_version: str = "v1",
        wrapper_version: str = "v1",
    ) -> Tuple[str, str, str]:
        """
        Render a complete prompt for model evaluation.

        Args:
            model_name: Model name (e.g., 'chatgpt', 'gemini')
            enriched_event: The enriched signal event data
            constraints: Trading constraints
            core_version: Core prompt version
            wrapper_version: Wrapper prompt version

        Returns:
            Tuple of (rendered_prompt, prompt_version, prompt_hash)
        """
        # Load prompts
        core_prompt = self.load_core_prompt(core_version)
        wrapper_prompt = self.load_wrapper_prompt(model_name, wrapper_version)

        # Render core prompt with data
        rendered_core = core_prompt.replace(
            "{enriched_event}",
            json.dumps(enriched_event, indent=2, default=str)
        ).replace(
            "{constraints}",
            json.dumps(constraints, indent=2)
        )

        # Combine wrapper with rendered core
        rendered_prompt = wrapper_prompt.replace("{core_prompt}", rendered_core)

        # Generate version and hash
        prompt_version = f"{model_name}_{wrapper_version}_core_{core_version}"
        prompt_hash = self._compute_hash(wrapper_prompt + core_prompt)

        return rendered_prompt, prompt_version, prompt_hash

    def _compute_hash(self, content: str) -> str:
        """Compute SHA-256 hash of prompt content."""
        return hashlib.sha256(content.encode()).hexdigest()

    def get_available_prompts(self) -> dict:
        """List available prompts."""
        result = {
            "core_versions": [],
            "wrappers": {},
        }

        for filepath in self.prompts_dir.glob("*.md"):
            name = filepath.stem
            if name.startswith("core_decision_"):
                version = name.replace("core_decision_", "")
                result["core_versions"].append(version)
            elif name.endswith("_wrapper_v1") or "_wrapper_" in name:
                parts = name.rsplit("_wrapper_", 1)
                if len(parts) == 2:
                    model_name, version = parts
                    if model_name not in result["wrappers"]:
                        result["wrappers"][model_name] = []
                    result["wrappers"][model_name].append(version)

        return result


# Global prompt loader instance
prompt_loader = PromptLoader()


def get_prompt_for_model(
    model_name: str,
    enriched_event: dict,
    constraints: dict,
) -> Tuple[str, str, str]:
    """
    Convenience function to get a rendered prompt for a model.

    Args:
        model_name: Model name
        enriched_event: Enriched signal data
        constraints: Trading constraints

    Returns:
        Tuple of (prompt, version, hash)
    """
    return prompt_loader.render_prompt(
        model_name=model_name,
        enriched_event=enriched_event,
        constraints=constraints,
    )
