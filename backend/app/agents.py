import os
from typing import Dict, Any

class PatchPilotAgentManager:
    """Manages system configurations and operational parameters for AI tools/skills."""
    
    def __init__(self):
        self.enabled_skills: Dict[str, Any] = {}
        # Default fallback context configs
        self.default_context = {
            "isolation_mode": True,
            "max_token_limit": 4096
        }

    def register_agent_skill(self, skill_name: str, config_payload: Dict[str, Any]) -> None:
        """Registers and validates a runtime agent competency skill block."""
        if not skill_name:
            raise ValueError("Skill name cannot be empty.")
        self.enabled_skills[skill_name] = {**self.default_context, **config_payload}

    def get_active_skills(self) -> Dict[str, Any]:
        """Returns the fully mapped ecosystem tracking configuration."""
        return self.enabled_skills

# Global management tracking object initialized for app integration
agent_manager = PatchPilotAgentManager()