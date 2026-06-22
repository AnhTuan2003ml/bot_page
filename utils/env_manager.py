from database.config_manager import get_public_configs
from utils.config_service import set_global_config, set_global_configs


def load_runtime_env(*args, **kwargs):
    print("[ENV_MANAGER] deprecated: redirected to DB config")
    return True


def get_env_path():
    return None


def update_env_file(key: str, value: str) -> bool:
    print("[ENV_MANAGER] deprecated: redirected to DB config")
    set_global_config(key, value)
    return True


def update_env_values(values: dict) -> list:
    print("[ENV_MANAGER] deprecated: redirected to DB config")
    set_global_configs(values or {})
    return list((values or {}).keys())


def read_env_config():
    print("[ENV_MANAGER] deprecated: redirected to DB config")
    return get_public_configs()


def get_public_config():
    return read_env_config()


def get_env_value(key: str, default: str = "") -> str:
    from utils.config_service import get_runtime_config
    return get_runtime_config(key, default)


def mask_string(s: str, show_last: int = 4) -> str:
    from database.config_manager import mask_secret
    return mask_secret(s)
