import asyncio
import json
import time
from pathlib import Path

import discord
from discord import app_commands

from vrchat import (
    VRChatClient,
    VRChatAuthError,
    load_session_token
)

from vrchat_websocket import VRChatWebSocket

from discord_commands import register_commands


# ============================================================
# Paths
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

CONFIG_FILE = BASE_DIR / "config.json"
DISCORD_TOKEN_FILE = DATA_DIR / "discord_bot.txt"


# ============================================================
# Configuration
# ============================================================

def load_config():

    print("Loading configuration...")

    with open(
        CONFIG_FILE,
        "r",
        encoding="utf-8"
    ) as file:

        return json.load(file)


def load_discord_token():

    if not DISCORD_TOKEN_FILE.exists():

        raise FileNotFoundError(
            f"Discord token file not found:\n"
            f"{DISCORD_TOKEN_FILE}"
        )

    token = DISCORD_TOKEN_FILE.read_text(
        encoding="utf-8"
    ).strip()

    if not token:

        raise ValueError(
            "Discord token file is empty."
        )

    return token


# ============================================================
# Discord
# ============================================================

intents = discord.Intents.default()

discord_client = discord.Client(
    intents=intents
)

# Client does not automatically have .tree like commands.Bot
command_tree = app_commands.CommandTree(
    discord_client
)


# ============================================================
# Globals
# ============================================================

config = load_config()

DISCORD_CHANNEL_ID = int(
    config["discord"]["channel_id"]
)

# Development/test Discord server
DISCORD_GUILD_ID = 1540215898768408617

WATCHED_USERS = config["watched_users"]

watched_user_ids = {}

discord_channel = None

vrchat_client = None
vrchat_websocket = None

current_user_id = None
current_username = None

own_status = None

# Runtime tracking
startup_time = time.monotonic()

# Connection state
vrchat_connected = False
websocket_connected = False

# Prevent on_ready from registering commands repeatedly
commands_registered = False


# ============================================================
# Runtime status callback
# ============================================================

def get_runtime_status():

    return {
        "runtime": time.monotonic() - startup_time,

        "discord_connected":
            discord_client.is_ready(),

        "vrchat_connected":
            vrchat_connected,

        "websocket_connected":
            websocket_connected,

        "watched_users":
            len(watched_user_ids),

        "vrchat_username":
            current_username
    }


# ============================================================
# Query current VRChat presence
# ============================================================

async def query_vrchat_presence():

    if vrchat_client is None:

        raise RuntimeError(
            "VRChat client is not connected."
        )

    results = []

    # --------------------------------------------------------
    # Get current friends from VRChat
    # --------------------------------------------------------

    friends = await (
        vrchat_client.get_friends()
    )

    friend_lookup = {
        friend.get("displayName"): friend
        for friend in friends
        if friend.get("displayName")
    }

    # --------------------------------------------------------
    # Check every watched user
    # --------------------------------------------------------

    for username in WATCHED_USERS:

        # ----------------------------------------------------
        # Our own account
        # ----------------------------------------------------

        if username == current_username:

            # The process monitor is our source of truth for
            # our own account.
            if own_status is True:

                results.append({
                    "username": username,
                    "status": "online"
                })

            elif own_status is False:

                results.append({
                    "username": username,
                    "status": "offline"
                })

            else:

                results.append({
                    "username": username,
                    "status": "unknown"
                })

            continue

        # ----------------------------------------------------
        # Friend
        # ----------------------------------------------------

        friend = friend_lookup.get(
            username
        )

        if friend is None:

            results.append({
                "username": username,
                "status": "not_found"
            })

            continue

        # VRChat friend objects expose the current online state
        # through the "status" field.
        status = friend.get(
            "status"
        )

        if status == "active":

            results.append({
                "username": username,
                "status": "online"
            })

        elif status in (
            "offline",
            None
        ):

            results.append({
                "username": username,
                "status": "offline"
            })

        else:

            # Treat other active presence states as online.
            results.append({
                "username": username,
                "status": "online"
            })

    return results


# ============================================================
# VRChat setup
# ============================================================

async def setup_vrchat():

    global vrchat_client
    global vrchat_websocket
    global watched_user_ids
    global current_user_id
    global current_username
    global vrchat_connected
    global websocket_connected

    print()
    print("Connecting to VRChat...")

    # --------------------------------------------------------
    # Load session token
    # --------------------------------------------------------

    session_token = load_session_token()

    vrchat_client = VRChatClient(
        session_token
    )

    await vrchat_client.start()

    # --------------------------------------------------------
    # Verify authentication
    # --------------------------------------------------------

    current_user = await (
        vrchat_client.get_current_user()
    )

    current_username = current_user.get(
        "displayName"
    )

    current_user_id = current_user.get(
        "id"
    )

    vrchat_connected = True

    print(
        f"Authenticated as: "
        f"{current_username}"
    )

    # --------------------------------------------------------
    # Get friends
    # --------------------------------------------------------

    print("Getting friends...")

    friends = await (
        vrchat_client.get_friends()
    )

    friend_lookup = {
        friend["displayName"]: friend
        for friend in friends
        if friend.get("displayName")
    }

    # --------------------------------------------------------
    # Resolve watched users
    # --------------------------------------------------------

    print()
    print("Watched users:")

    for username in WATCHED_USERS:

        # ----------------------------------------------------
        # Own account
        # ----------------------------------------------------

        if username == current_username:

            if current_user_id:

                watched_user_ids[
                    current_user_id
                ] = username

                print(
                    f"  ✓ {username} → "
                    f"{current_user_id}"
                )

            else:

                print(
                    f"  ✗ {username} → "
                    f"NO USER ID"
                )

            continue

        # ----------------------------------------------------
        # Friend
        # ----------------------------------------------------

        friend = friend_lookup.get(
            username
        )

        if friend:

            user_id = friend.get(
                "id"
            )

            if user_id:

                watched_user_ids[
                    user_id
                ] = username

                print(
                    f"  ✓ {username} → "
                    f"{user_id}"
                )

            else:

                print(
                    f"  ✗ {username} → "
                    f"NO USER ID"
                )

        else:

            print(
                f"  ✗ {username} → "
                f"NOT FOUND"
            )

    print()

    # --------------------------------------------------------
    # Create WebSocket
    # --------------------------------------------------------

    vrchat_websocket = VRChatWebSocket(
        session_token,
        watched_user_ids
    )

    vrchat_websocket.on_status_change = (
        handle_vrchat_status_change
    )

    print(
        "[WebSocket] Connecting..."
    )

    await vrchat_websocket.connect()

    websocket_connected = True

    print(
        "[WebSocket] Connected."
    )


# ============================================================
# Send VRChat presence notification
# ============================================================

async def send_presence_message(
    username,
    online
):

    global discord_channel

    if online:

        message = (
            f"🟢 **{username} is online**"
        )

    else:

        message = (
            f"🔴 **{username} has gone offline**"
        )

    print()
    print(message)

    if discord_channel is None:

        print(
            "Discord channel is not ready yet."
        )

        return

    try:

        await discord_channel.send(
            message
        )

        print(
            "Sent to Discord."
        )

    except Exception as error:

        print()
        print(
            "Failed to send Discord message:"
        )

        print(error)

        print()


# ============================================================
# Friend WebSocket event
# ============================================================

async def handle_vrchat_status_change(
    user_id,
    username,
    online
):

    # --------------------------------------------------------
    # Friend events are handled here.
    #
    # Our own account is ignored here because VRChat does not
    # reliably send our own presence through friend events.
    # --------------------------------------------------------

    if user_id == current_user_id:

        return

    await send_presence_message(
        username,
        online
    )


# ============================================================
# Check whether VRChat.exe is running
# ============================================================

async def is_vrchat_running():

    try:

        process = await asyncio.create_subprocess_exec(
            "tasklist",
            "/FI",
            "IMAGENAME eq VRChat.exe",
            "/FO",
            "CSV",
            "/NH",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL
        )

        stdout, _ = await process.communicate()

        output = stdout.decode(
            "utf-8",
            errors="ignore"
        )

        return "VRChat.exe" in output

    except Exception as error:

        print(
            f"[Process] Could not check VRChat.exe: "
            f"{error}"
        )

        return False


# ============================================================
# Own-account monitor
# ============================================================

async def monitor_own_status():

    global own_status

    print(
        "[Monitor] Own-account process monitor started."
    )

    print(
        "[Monitor] Checking for VRChat.exe every 5 seconds."
    )

    print()

    while True:

        try:

            new_status = await is_vrchat_running()

            # ------------------------------------------------
            # First check establishes initial state.
            # ------------------------------------------------

            if own_status is None:

                own_status = new_status

                print(
                    "[Own Account] "
                    f"{'ONLINE' if new_status else 'OFFLINE'}"
                )

            # ------------------------------------------------
            # Nothing changed.
            # ------------------------------------------------

            elif new_status == own_status:

                pass

            # ------------------------------------------------
            # Status changed.
            # ------------------------------------------------

            else:

                own_status = new_status

                print()

                print(
                    "[Own Account] Status changed: "
                    f"{'ONLINE' if new_status else 'OFFLINE'}"
                )

                print()

                if current_username:

                    await send_presence_message(
                        current_username,
                        new_status
                    )

            await asyncio.sleep(5)

        except asyncio.CancelledError:

            raise

        except Exception as error:

            print()
            print(
                "[Own Account] Monitor error:"
            )

            print(error)

            print()

            await asyncio.sleep(5)


# ============================================================
# VRChat WebSocket monitor
# ============================================================

async def monitor_vrchat():

    print(
        "[Monitor] Starting VRChat friend event listener..."
    )

    print()

    try:

        await vrchat_websocket.listen()

    except asyncio.CancelledError:

        raise

    except Exception as error:

        print()
        print(
            "[WebSocket] Monitor error:"
        )

        print(error)

        print()


# ============================================================
# Register Discord commands
# ============================================================

async def setup_discord_commands():

    global commands_registered

    if commands_registered:

        return

    guild = discord.Object(
        id=DISCORD_GUILD_ID
    )

    print()
    print(
        "[Discord] Registering slash commands..."
    )

    # --------------------------------------------------------
    # Register commands using your existing
    # discord_commands.py
    #
    # That file creates /status and /query as global commands
    # in the local CommandTree.
    # --------------------------------------------------------

    register_commands(
        command_tree,
        get_runtime_status,
        query_vrchat_presence
    )

    # --------------------------------------------------------
    # Grab the commands that were just created.
    # --------------------------------------------------------

    commands_to_keep = list(
        command_tree.get_commands()
    )

    print(
        "[Discord] Commands loaded:"
    )

    for command in commands_to_keep:

        print(
            f"  • /{command.name}"
        )

    # --------------------------------------------------------
    # SAFETY CLEANUP
    #
    # First remove any locally registered guild commands.
    # --------------------------------------------------------

    command_tree.clear_commands(
        guild=guild
    )

    # --------------------------------------------------------
    # Remove the commands from the global tree.
    #
    # This prevents the same commands from existing both
    # globally and in the development server.
    # --------------------------------------------------------

    command_tree.clear_commands(
        guild=None
    )

    # --------------------------------------------------------
    # Sync the empty global tree.
    #
    # This removes old global /status and /query commands that
    # may have been created during the previous attempts.
    # --------------------------------------------------------

    try:

        await command_tree.sync()

        print(
            "[Discord] Global command cleanup synced."
        )

    except Exception as error:

        print()
        print(
            "[Discord] WARNING: Could not sync global "
            "command cleanup:"
        )

        print(error)

    # --------------------------------------------------------
    # Add ONLY the desired commands to our development guild.
    # --------------------------------------------------------

    for command in commands_to_keep:

        command_tree.add_command(
            command,
            guild=guild
        )

    # --------------------------------------------------------
    # Sync guild commands.
    # --------------------------------------------------------

    synced = await command_tree.sync(
        guild=guild
    )

    print(
        "[Discord] Slash commands registered."
    )

    print(
        f"[Discord] Synced {len(synced)} command(s) "
        f"to guild {DISCORD_GUILD_ID}."
    )

    for command in synced:

        print(
            f"  • /{command.name}"
        )

    commands_registered = True


# ============================================================
# Discord ready
# ============================================================

@discord_client.event
async def on_ready():

    global discord_channel

    print()
    print("===================================")
    print(" VRChat → Discord Presence Monitor")
    print("===================================")
    print()

    print(
        "Logged into Discord as:"
    )

    print(
        f"  {discord_client.user}"
    )

    print()

    # --------------------------------------------------------
    # Find channel
    # --------------------------------------------------------

    discord_channel = (
        discord_client.get_channel(
            DISCORD_CHANNEL_ID
        )
    )

    if discord_channel is None:

        print(
            "ERROR: Could not find "
            "the configured Discord channel."
        )

        print(
            f"Channel ID: {DISCORD_CHANNEL_ID}"
        )

        print()

        print(
            "Make sure the bot:"
        )

        print(
            "  • is in the server"
        )

        print(
            "  • can view the private channel"
        )

        print(
            "  • can send messages"
        )

        print()

    else:

        print(
            "Discord channel found:"
        )

        print(
            f"  #{discord_channel.name}"
        )

        print()

    # --------------------------------------------------------
    # Register slash commands
    # --------------------------------------------------------

    try:

        await setup_discord_commands()

    except Exception as error:

        print()
        print(
            "[Discord] ERROR registering slash commands:"
        )

        print(error)

        print()

    # --------------------------------------------------------
    # Watching information
    # --------------------------------------------------------

    print("Watching:")

    for username in WATCHED_USERS:

        print(
            f"  • {username}"
        )

    print()

    print(
        "Listening for presence changes..."
    )

    print()


# ============================================================
# Main
# ============================================================

async def main():

    global vrchat_client
    global vrchat_websocket
    global websocket_connected
    global vrchat_connected

    websocket_task = None
    own_status_task = None

    try:

        # ----------------------------------------------------
        # Discord token
        # ----------------------------------------------------

        discord_token = (
            load_discord_token()
        )

        # ----------------------------------------------------
        # VRChat
        # ----------------------------------------------------

        try:

            await setup_vrchat()

        except VRChatAuthError:

            print()
            print(
                "[VRChat] Authentication failed."
            )

            raise

        # ----------------------------------------------------
        # Friend monitor
        # ----------------------------------------------------

        websocket_task = asyncio.create_task(
            monitor_vrchat()
        )

        # ----------------------------------------------------
        # Own-account monitor
        # ----------------------------------------------------

        own_status_task = asyncio.create_task(
            monitor_own_status()
        )

        # ----------------------------------------------------
        # Discord
        # ----------------------------------------------------

        await discord_client.start(
            discord_token
        )

    finally:

        # ----------------------------------------------------
        # Stop WebSocket monitor
        # ----------------------------------------------------

        if websocket_task:

            websocket_task.cancel()

            try:

                await websocket_task

            except asyncio.CancelledError:

                pass

        # ----------------------------------------------------
        # Stop own-status monitor
        # ----------------------------------------------------

        if own_status_task:

            own_status_task.cancel()

            try:

                await own_status_task

            except asyncio.CancelledError:

                pass

        # ----------------------------------------------------
        # Close WebSocket
        # ----------------------------------------------------

        if vrchat_websocket:

            try:

                await vrchat_websocket.disconnect()

            except Exception:

                pass

            websocket_connected = False

        # ----------------------------------------------------
        # Close VRChat HTTP session
        # ----------------------------------------------------

        if vrchat_client:

            try:

                await vrchat_client.close()

            except Exception:

                pass

            vrchat_connected = False

        # ----------------------------------------------------
        # Close Discord
        # ----------------------------------------------------

        if not discord_client.is_closed():

            try:

                await discord_client.close()

            except Exception:

                pass


# ============================================================
# Run
# ============================================================

if __name__ == "__main__":

    try:

        asyncio.run(
            main()
        )

    except KeyboardInterrupt:

        print()
        print("Stopped.")

