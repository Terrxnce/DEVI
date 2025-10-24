"""
Configuration models.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional
from hashlib import sha256
import json


@dataclass
class ConfigHash:
    """Configuration hash for reproducibility."""
    hash_value: str
    timestamp: str
    
    @staticmethod
    def compute(config_dict: Dict[str, Any]) -> str:
        """Compute SHA256 hash of config."""
        json_str = json.dumps(config_dict, sort_keys=True, default=str)
        return sha256(json_str.encode()).hexdigest()


@dataclass
class Config:
    """System configuration."""
    session_configs: Dict[str, Any] = field(default_factory=dict)
    session_rotation: Dict[str, Any] = field(default_factory=dict)
    structure_configs: Dict[str, Any] = field(default_factory=dict)
    quality_thresholds: Dict[str, Any] = field(default_factory=dict)
    scoring_weights: Dict[str, Any] = field(default_factory=dict)
    max_structures: Dict[str, Any] = field(default_factory=dict)
    guard_configs: Dict[str, Any] = field(default_factory=dict)
    risk_limits: Dict[str, Any] = field(default_factory=dict)
    sltp_configs: Dict[str, Any] = field(default_factory=dict)
    indicator_configs: Dict[str, Any] = field(default_factory=dict)
    system_configs: Dict[str, Any] = field(default_factory=dict)
    execution_configs: Dict[str, Any] = field(default_factory=dict)
    broker_configs: Dict[str, Any] = field(default_factory=dict)
    config_hash: Optional[ConfigHash] = None
    
    def __post_init__(self):
        if self.config_hash is None:
            combined = {
                'system': self.system_configs,
                'structure': self.structure_configs,
                'execution': self.execution_configs,
                'broker': self.broker_configs
            }
            hash_value = ConfigHash.compute(combined)
            from datetime import datetime, timezone
            object.__setattr__(self, 'config_hash', ConfigHash(
                hash_value=hash_value,
                timestamp=datetime.now(timezone.utc).isoformat()
            ))
