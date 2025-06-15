import os
from pathlib import Path

import notte_core

CONFIG_PATH = Path(__file__).parent / "test_notte_config.toml"
notte_core.set_error_mode("developer")

os.environ["NOTTE_CONFIG_PATH"] = str(CONFIG_PATH)
