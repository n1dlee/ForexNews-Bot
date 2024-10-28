from dataclasses import dataclass
from environs import Env
from typing import List

@dataclass
class TgBot:
    token: str
    channel_id: str
    admin_id: int
    update_interval: int

@dataclass
class CurrencyConfig:
    currencies: List[str]

@dataclass
class Config:
    tg_bot: TgBot
    currency: CurrencyConfig

def load_config(path: str = None) -> Config:
    env = Env()
    env.read_env(path)

    return Config(
        tg_bot=TgBot(
            token=env.str("TELEGRAM_BOT_TOKEN"),
            channel_id=env.str("CHANNEL_ID"),
            admin_id=env.int("ADMIN_ID"),
            update_interval=env.int("UPDATE_INTERVAL", 3600)
        ),
        currency=CurrencyConfig(
            currencies=env.list("CURRENCIES", ["USD", "EUR", "CAD"])
        )
    )