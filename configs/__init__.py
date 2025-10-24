"""
D.E.V.I 2.0 Configuration Management

Loads and manages all system configurations.
"""

import json
from typing import Dict, Any
from pathlib import Path
import jsonschema


class ConfigLoader:
    """Loads and manages system configurations."""
    
    def __init__(self, config_dir: str = "configs"):
        """
        Initialize configuration loader.
        
        Args:
            config_dir: Directory containing configuration files
        """
        self.config_dir = Path(config_dir)
        self.configs = {}
        self._load_all_configs()
    
    def _load_all_configs(self) -> None:
        """Load all configuration files."""
        config_files = {
            'sessions': 'sessions.json',
            'indicators': 'indicators.json',
            'structure': 'structure.json',
            'guards': 'guards.json',
            'sltp': 'sltp.json',
            'scoring': 'scoring.json',
            'system': 'system.json',
            'news_events': 'news_events.json'
        }
        
        for config_name, filename in config_files.items():
            try:
                config_path = self.config_dir / filename
                if config_path.exists():
                    with open(config_path, 'r') as f:
                        self.configs[config_name] = json.load(f)
                    # Validate structure config with JSON Schema when loading
                    if config_name == 'structure':
                        schema_path = self.config_dir / 'structure.schema.json'
                        if schema_path.exists():
                            with open(schema_path, 'r') as sf:
                                schema = json.load(sf)
                            jsonschema.validate(instance=self.configs[config_name], schema=schema)
                else:
                    # Silent default; rely on validation when used
                    self.configs[config_name] = {}
            except Exception as e:
                # On validation or parse error, store empty to force fail-fast at usage sites
                self.configs[config_name] = {}
    
    def get_config(self, config_name: str) -> Dict[str, Any]:
        """
        Get configuration by name.
        
        Args:
            config_name: Name of configuration
            
        Returns:
            Configuration dictionary
        """
        return self.configs.get(config_name, {})
    
    def get_all_configs(self) -> Dict[str, Dict[str, Any]]:
        """
        Get all configurations.
        
        Returns:
            Dictionary of all configurations
        """
        return self.configs.copy()
    
    def reload_config(self, config_name: str) -> None:
        """
        Reload specific configuration.
        
        Args:
            config_name: Name of configuration to reload
        """
        config_files = {
            'sessions': 'sessions.json',
            'indicators': 'indicators.json',
            'structure': 'structure.json',
            'guards': 'guards.json',
            'sltp': 'sltp.json',
            'scoring': 'scoring.json',
            'system': 'system.json',
            'news_events': 'news_events.json'
        }
        
        if config_name in config_files:
            try:
                config_path = self.config_dir / config_files[config_name]
                with open(config_path, 'r') as f:
                    self.configs[config_name] = json.load(f)
                if config_name == 'structure':
                    schema_path = self.config_dir / 'structure.schema.json'
                    if schema_path.exists():
                        with open(schema_path, 'r') as sf:
                            schema = json.load(sf)
                        jsonschema.validate(instance=self.configs[config_name], schema=schema)
            except Exception as e:
                # ignore; retain prior config
                pass


# Global configuration loader instance
config_loader = ConfigLoader()

