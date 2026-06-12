import mirage.resource.databricks_volume as databricks_volume
from mirage.resource.databricks_volume import token_provider as provider_module


class FakeWorkspaceConfig:
    calls: list[dict] = []

    def __init__(self, **kwargs) -> None:
        self.calls.append(kwargs)

    def authenticate(self) -> dict[str, str]:
        return {"Authorization": "Bearer profile-token"}


def test_token_provider_types_are_public():
    assert hasattr(databricks_volume, "TokenProvider")
    assert hasattr(databricks_volume, "StaticTokenProvider")
    assert hasattr(databricks_volume, "DatabricksProfileTokenProvider")


def test_static_token_provider_returns_token():
    provider = databricks_volume.StaticTokenProvider("token")

    assert provider.get_token() == "token"


def test_profile_token_provider_uses_host_and_profile(monkeypatch):
    FakeWorkspaceConfig.calls = []
    monkeypatch.setattr(
        provider_module,
        "WorkspaceConfig",
        FakeWorkspaceConfig,
    )
    provider = databricks_volume.DatabricksProfileTokenProvider(
        "https://example.cloud.databricks.com",
        profile="DEV",
    )

    assert provider.get_token() == "profile-token"
    assert provider.get_token() == "profile-token"
    assert FakeWorkspaceConfig.calls == [{
        "host": "https://example.cloud.databricks.com",
        "profile": "DEV",
    }]
