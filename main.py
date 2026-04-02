#!/usr/bin/env python3
"""Entry point — load config, wire dependencies, start the bot."""
import logging

from dotenv import load_dotenv

from bot import NescoBot
from config import Config
from nesco_client import NescoClient

logging.basicConfig(
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    level=logging.INFO,
)


def main() -> None:
    load_dotenv()
    config = Config.from_env()
    client = NescoClient()
    bot = NescoBot(config=config, client=client)
    try:
        bot.run()
    finally:
        client.close()


if __name__ == "__main__":
    main()
