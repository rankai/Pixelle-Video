from pixelle_video.config.manager import ConfigManager
from pixelle_video.config.schema import PixelleVideoConfig


def _manager(config: PixelleVideoConfig) -> ConfigManager:
    manager = ConfigManager.__new__(ConfigManager)
    manager.config = config
    return manager


def test_legacy_llm_is_migrated_to_shared_profile():
    config = PixelleVideoConfig(
        llm={
            "api_key": "shared-key",
            "base_url": "https://shared.example/v1",
            "model": "shared-model",
        }
    )
    manager = _manager(config)
    manager._ensure_llm_profiles(config)

    assert config.llm_source == "shared"
    assert config.llm_shared.model == "shared-model"
    assert config.llm_custom.model == ""


def test_switching_profiles_preserves_shared_and_custom_active_configs():
    config = PixelleVideoConfig(
        llm={
            "api_key": "shared-key",
            "base_url": "https://shared.example/v1",
            "model": "shared-model",
        }
    )
    manager = _manager(config)

    manager.set_llm_source("custom")
    assert config.llm_source == "custom"
    assert config.llm.api_key == ""

    config.llm.api_key = "custom-key"
    config.llm.base_url = "https://custom.example/v1"
    config.llm.model = "custom-model"
    manager.sync_active_llm_profile()

    manager.set_llm_source("shared")
    assert config.llm.api_key == "shared-key"
    assert config.llm.model == "shared-model"
    manager.set_llm_source("custom")
    assert config.llm.api_key == "custom-key"
    assert config.llm.model == "custom-model"
    # ConfigManager is a process singleton; leave the active profile at the
    # documented shared default so later API tests do not inherit test state.
    manager.set_llm_source("shared")
