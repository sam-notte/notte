from hvac import Client
from typing import Optional
from notte.password.models import Credentials
from urllib.parse import urlparse

class HashiCorpVault:
    def __init__(self, url: str = "http://localhost:8200", token: str = "dev-root-token"):
        self.client = Client(url=url, token=token)
        self._mount_path = "secret"
        
        # Check if secrets engine is enabled and properly configured
        try:
            mounts = self.client.sys.list_mounted_secrets_engines()
            if self._mount_path not in mounts['data']:
                self.client.sys.enable_secrets_engine(
                    backend_type='kv',
                    path=self._mount_path,
                    options={'version': '2'}
                )
            else:
                # Verify it's a v2 KV store
                mount_info = mounts['data'][f'{self._mount_path}/']['options']
                if mount_info.get('version') != '2':
                    raise ValueError(f"Existing {self._mount_path} mount is not a KV v2 secrets engine")
        except Exception as e:
            if "path is already in use" not in str(e):
                raise e

    def add_credentials(self, url: str, username: str, password: str) -> None:
        """Store credentials for a given URL"""
        domain = urlparse(url).netloc or url  # Handle cases where url might not have scheme
        self.client.secrets.kv.v2.create_or_update_secret(
            path=f'credentials/{domain}',
            secret=dict(
                url=url,
                username=username,
                password=password
            ),
            mount_point=self._mount_path
        )

    def get_credentials(self, url: str) -> Optional[Credentials]:
        """Retrieve credentials for a given URL"""
        domain = urlparse(url).netloc or url
        try:
            secret = self.client.secrets.kv.v2.read_secret_version(
                path=f'credentials/{domain}',
                mount_point=self._mount_path
            )
            data = secret['data']['data']
            return Credentials(
                url=data['url'],
                username=data['username'],
                password=data['password']
            )
        except Exception:
            return None

    def remove_credentials(self, url: str) -> None:
        """Remove credentials for a given URL"""
        domain = urlparse(url).netloc or url
        self.client.secrets.kv.v2.delete_metadata_and_all_versions(
            path=f'credentials/{domain}',
            mount_point=self._mount_path
        )