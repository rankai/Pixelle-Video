# Copyright (C) 2025 AIDC-AI
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
API Configuration
"""

import os
from typing import Optional

from pydantic import BaseModel, Field


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class APIConfig(BaseModel):
    """API configuration"""
    
    # Server settings
    host: str = "0.0.0.0"
    port: int = 8000
    reload: bool = False
    
    # CORS settings
    cors_enabled: bool = True
    cors_origins: list[str] = ["*"]
    
    # Task settings
    max_concurrent_tasks: int = 5
    task_cleanup_interval: int = 3600  # Clean completed tasks every hour
    task_retention_time: int = 86400   # Keep task results for 24 hours
    
    # File upload settings
    max_upload_size: int = 100 * 1024 * 1024  # 100MB

    # Enterprise asset library V2. Gate C has passed; keep the explicit
    # environment switch so operators can roll back to the legacy routes.
    asset_center_v2_enabled: bool = Field(
        default_factory=lambda: _env_flag("PIXELLE_ASSET_CENTER_V2", True),
        description="V2 asset center enabled by default; set PIXELLE_ASSET_CENTER_V2=false to roll back.",
    )
    # UX-0 contract gate. This is intentionally independent from the V2
    # kernel/UI switch so migrations and compatibility routes are unaffected.
    asset_center_smb_ux_enabled: bool = Field(
        default_factory=lambda: _env_flag("PIXELLE_ASSET_CENTER_SMB_UX", False),
        description="SMB asset-center UX rollout; remains off until UX-E evidence review.",
    )
    
    # API settings
    api_prefix: str = "/api"
    docs_url: Optional[str] = "/docs"
    redoc_url: Optional[str] = "/redoc"
    openapi_url: Optional[str] = "/openapi.json"


# Global config instance
api_config = APIConfig()
