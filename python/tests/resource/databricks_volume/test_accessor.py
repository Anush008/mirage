from mirage.accessor.databricks_volume import DatabricksVolumeAccessor
from mirage.resource.databricks_volume import DatabricksVolumeConfig


class FakeFilesClient:
    pass


def test_accessor_stores_config_and_files_client():
    config = DatabricksVolumeConfig(
        catalog="main",
        schema="default",
        volume="agent_files",
        host="https://example.cloud.databricks.com",
        timeout=17,
    )
    client = FakeFilesClient()

    accessor = DatabricksVolumeAccessor(config, client)

    assert accessor.config is config
    assert accessor.client is client
