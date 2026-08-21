import json
from pathlib import Path


CONFIG_FILE = Path("config.json")


def load_config():
    if not CONFIG_FILE.exists():
        raise FileNotFoundError(
            f"Could not find {CONFIG_FILE}"
        )

    with open(
        CONFIG_FILE,
        "r",
        encoding="utf-8"
    ) as file:
        config = json.load(file)

    if "watched_users" not in config:
        raise ValueError(
            "config.json is missing 'watched_users'"
        )

    if "discord" not in config:
        raise ValueError(
            "config.json is missing 'discord'"
        )

    if "settings" not in config:
        raise ValueError(
            "config.json is missing 'settings'"
        )

    return config


def get_watched_users(config):
    return config["watched_users"]


def get_discord_channel_id(config):
    return config["discord"]["channel_id"]


def resolve_watched_users(config, friends):
    watched_names = config["watched_users"]

    resolved = {}
    missing = []

    friends_by_name = {
        friend.get("displayName", "").casefold(): friend
        for friend in friends
    }

    for name in watched_names:
        friend = friends_by_name.get(name.casefold())

        if friend:
            resolved[friend["id"]] = friend["displayName"]
        else:
            missing.append(name)

    return resolved, missing