import json
import logging

import websockets


WEBSOCKET_URL = "wss://pipeline.vrchat.cloud/"

USER_AGENT = "VRC-DiscordPresence/1.0"


class VRChatWebSocket:

    def __init__(
        self,
        session_token,
        watched_users
    ):

        self.session_token = session_token

        # Dictionary:
        #
        # {
        #     "VRChat user ID": "Display Name"
        # }

        self.watched_users = watched_users

        # Current known state:
        #
        # {
        #     "VRChat user ID": True/False
        # }

        self.status = {}

        self.websocket = None
        self.running = False

        self.logger = logging.getLogger(
            "VRChatWebSocket"
        )

        # Function supplied by the Discord bot.
        #
        # It will receive:
        #
        #     user_id
        #     display_name
        #     online
        #
        self.on_status_change = None

    # ========================================================
    # Connect
    # ========================================================

    async def connect(self):

        url = (
            f"{WEBSOCKET_URL}"
            f"?authToken={self.session_token}"
        )

        self.logger.info(
            "Connecting to VRChat WebSocket..."
        )

        self.websocket = await websockets.connect(
            url,
            additional_headers={
                "User-Agent": USER_AGENT
            }
        )

        self.logger.info(
            "Connected to VRChat WebSocket."
        )

    # ========================================================
    # Disconnect
    # ========================================================

    async def disconnect(self):

        self.running = False

        if self.websocket:

            await self.websocket.close()

            self.websocket = None

    # ========================================================
    # Close
    # ========================================================

    async def close(self):

        await self.disconnect()

    # ========================================================
    # Listen
    # ========================================================

    async def listen(self):

        if not self.websocket:

            raise RuntimeError(
                "WebSocket is not connected."
            )

        self.running = True

        while self.running:

            try:

                message = (
                    await self.websocket.recv()
                )

                await self.handle_message(
                    message
                )

            except websockets.ConnectionClosed:

                self.logger.warning(
                    "VRChat WebSocket connection closed."
                )

                self.running = False

    # ========================================================
    # Handle incoming message
    # ========================================================

    async def handle_message(
        self,
        message
    ):

        # ----------------------------------------------------
        # Decode bytes
        # ----------------------------------------------------

        if isinstance(
            message,
            bytes
        ):

            message = message.decode(
                "utf-8"
            )

        # ----------------------------------------------------
        # Parse top-level JSON
        # ----------------------------------------------------

        try:

            data = json.loads(
                message
            )

        except (
            json.JSONDecodeError,
            TypeError
        ):

            self.logger.warning(
                "Received invalid JSON from VRChat."
            )

            return

        # ----------------------------------------------------
        # Make sure the top-level object is a dictionary
        # ----------------------------------------------------

        if not isinstance(
            data,
            dict
        ):

            return

        event_type = data.get(
            "type"
        )

        content = data.get(
            "content"
        )

        # ----------------------------------------------------
        # We only care about presence events
        # ----------------------------------------------------

        if event_type not in {
            "friend-online",
            "friend-offline",
            "friend-active"
        }:

            return

        # ----------------------------------------------------
        # VRChat commonly sends content as a JSON string.
        # ----------------------------------------------------

        if isinstance(
            content,
            str
        ):

            try:

                content = json.loads(
                    content
                )

            except json.JSONDecodeError:

                return

        # ----------------------------------------------------
        # Content must now be a dictionary
        # ----------------------------------------------------

        if not isinstance(
            content,
            dict
        ):

            return

        # ----------------------------------------------------
        # Get user ID
        # ----------------------------------------------------

        user_id = content.get(
            "userId"
        )

        if not user_id:

            return

        # ----------------------------------------------------
        # Ignore users we're not watching
        # ----------------------------------------------------

        if user_id not in self.watched_users:

            return

        display_name = (
            self.watched_users[user_id]
        )

        # ----------------------------------------------------
        # Determine online state
        # ----------------------------------------------------

        if event_type == "friend-offline":

            online = False

        else:

            online = True

        # ----------------------------------------------------
        # Get previous state
        # ----------------------------------------------------

        previous = self.status.get(
            user_id
        )

        # ----------------------------------------------------
        # Store new state
        # ----------------------------------------------------

        self.status[user_id] = online

        # ----------------------------------------------------
        # Don't announce duplicate events
        # ----------------------------------------------------

        if (
            previous is not None
            and previous == online
        ):

            return

        # ----------------------------------------------------
        # Terminal output
        # ----------------------------------------------------

        print()

        if online:

            print(
                f"🟢 {display_name} is ONLINE"
            )

        else:

            print(
                f"🔴 {display_name} has gone OFFLINE"
            )

        print()

        # ----------------------------------------------------
        # Notify Discord bot
        # ----------------------------------------------------

        if self.on_status_change:

            await self.on_status_change(
                user_id,
                display_name,
                online
            )

    # ========================================================
    # Run
    # ========================================================

    async def run(self):

        await self.connect()

        try:

            await self.listen()

        finally:

            await self.disconnect()