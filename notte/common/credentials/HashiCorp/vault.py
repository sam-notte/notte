from typing import Optional
from urllib.parse import urlparse

from hvac import Client

from notte.actions.base import ActionParameterValue

from ..models import Credentials, VaultInterface


class HashiCorpVault(VaultInterface):
    def __init__(self, url: str, token: str):
        self.client = Client(url=url, token=token)
        self._mount_path = "secret"
        self._init_vault()

    def _init_vault(self) -> None:
        try:
            mounts = self.client.sys.list_mounted_secrets_engines()
            if self._mount_path not in mounts["data"]:
                self.client.sys.enable_secrets_engine(
                    backend_type="kv", path=self._mount_path, options={"version": "2"}
                )
            else:
                mount_info = mounts["data"][f"{self._mount_path}/"]["options"]
                if mount_info.get("version") != "2":
                    raise ValueError(f"Existing {self._mount_path} mount is not a KV v2 secrets engine")
        except Exception as e:
            if "path is already in use" not in str(e):
                raise e

    def add_credentials(self, url: str, username: str, password: str) -> None:
        domain = urlparse(url).netloc or url
        self.client.secrets.kv.v2.create_or_update_secret(
            path=f"credentials/{domain}",
            secret=dict(url=url, username=username, password=password),
            mount_point=self._mount_path,
        )

    def get_credentials(self, url: str) -> Optional[Credentials]:
        domain = urlparse(url).netloc or url
        try:
            secret = self.client.secrets.kv.v2.read_secret_version(
                path=f"credentials/{domain}", mount_point=self._mount_path
            )
            data = secret["data"]["data"]
            return Credentials(url=data["url"], username=data["username"], password=data["password"])
        except Exception:
            return None

    def remove_credentials(self, url: str) -> None:
        domain = urlparse(url).netloc or url
        self.client.secrets.kv.v2.delete_metadata_and_all_versions(
            path=f"credentials/{domain}", mount_point=self._mount_path
        )

    def replace_placeholder_credentials(
        self, url: str | None, params: list[ActionParameterValue] | None
    ) -> list[ActionParameterValue] | None:
        """Replace placeholder credentials with actual credentials"""
        if not params:
            return params

        if not url:
            return params

        # Get credentials for current domain
        creds = self.get_credentials(url)
        if not creds:
            return params

        # Replace placeholder values with actual credentials
        new_params = []
        for param in params:
            new_param = ActionParameterValue(name=param.name, value=param.value)

            if param.value == "login@login_page.com":
                new_param.value = creds.username
            elif param.value == "login_password":
                new_param.value = creds.password

            new_params.append(new_param)

        return new_params
