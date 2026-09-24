import os

from dotenv import load_dotenv

load_dotenv()

def _readConfigValueByName(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(
            f"{name} is not set, .env and fill it in."
        )
    return value


DEEPINFRA_API_KEY = _readConfigValueByName("DEEPINFRA_API_KEY")
DEEPINFRA_BASE_URL = _readConfigValueByName("DEEPINFRA_BASE_URL")
DEEPINFRA_MODEL = _readConfigValueByName("DEEPINFRA_MODEL")

DB_CONFIG = {
    "host": _readConfigValueByName("DB_HOST"),
    "port": int(_readConfigValueByName("DB_PORT")),
    "user": _readConfigValueByName("DB_USER"),
    "password": _readConfigValueByName("DB_PASSWORD"),
    "database": _readConfigValueByName("DB_NAME"),
}