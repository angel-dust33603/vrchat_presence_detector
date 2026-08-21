import asyncio
import logging

from vrchat import VRChatClient, load_session_token
from vrchat_websocket import VRChatWebSocket


class VRChatMonitor:

    def __init__(
        self,
        watched_users,
        on_status_change=None
    ):
        self.watched_users = watched_users
        self.on_status_change = on_status_change

        self.client = None
        self.websocket = None

        self.session_token = None

        self.running = False
        self.websocket_task = None

        self.logger = logging.getLogger(
            "VRChatMonitor"
        )

    # ========================================================
    # Start
    # ========================================================

    async def start(self):

        self.running = True

        await self.connect_vrchat()

        self.websocket_task = asyncio.create_task(
            self.websocket_loop()
        )

    # ========================================================
    # Connect VRChat API
    # ========================================================

    async def connect_vrchat(self):

        print()
        print("[VRChat] Connecting...")

        self.session_token = (
            load_session_token()
        )

        if self.client:

            try:
                await self.client.close()

            except Exception:
                pass

        self.client = VRChatClient(
            self.session_token
        )

        await self.client.start()

        current_user = await (
            self.client.get_current_user()
        )

        username = current_user.get(
            "displayName"
        )

        print(
            f"[VRChat] Authenticated as: "
            f"{username}"
        )

        await self.connect_websocket()

    # ========================================================
    # Connect WebSocket
    # ========================================================

    async def connect_websocket(self):

        if self.websocket:

            try:
                await self.websocket.disconnect()

            except Exception:
                pass

        self.websocket = VRChatWebSocket(
            self.session_token,
            self.watched_users
        )

        self.websocket.on_status_change = (
            self.on_status_change
        )

        print(
            "[WebSocket] Connecting..."
        )

        await self.websocket.connect()

        print(
            "[WebSocket] Connected."
        )

    # ========================================================
    # WebSocket watchdog
    # ========================================================

    async def websocket_loop(self):

        print(
            "[Monitor] WebSocket watchdog started."
        )

        while self.running:

            try:

                if not self.websocket:

                    raise RuntimeError(
                        "WebSocket object does not exist."
                    )

                await self.websocket.listen()

                if self.running:

                    print(
                        "[WebSocket] Listener stopped."
                    )

            except asyncio.CancelledError:

                raise

            except Exception as error:

                print()
                print(
                    "[WebSocket] Connection error:"
                )
                print(error)

            if not self.running:
                break

            print(
                "[Monitor] WebSocket disconnected."
            )

            print(
                "[Monitor] Reconnecting in "
                "5 seconds..."
            )

            await asyncio.sleep(5)

            if not self.running:
                break

            # ------------------------------------------------
            # Try existing authentication first.
            # ------------------------------------------------

            try:

                print(
                    "[Monitor] Reconnecting "
                    "WebSocket..."
                )

                await self.connect_websocket()

                print(
                    "[Monitor] WebSocket "
                    "reconnected."
                )

                continue

            except Exception as error:

                print(
                    "[Monitor] WebSocket "
                    "reconnect failed:"
                )

                print(error)

            # ------------------------------------------------
            # If that failed, reauthenticate.
            # ------------------------------------------------

            print(
                "[Monitor] Checking VRChat "
                "authentication..."
            )

            try:

                await self.reauthenticate()

            except Exception as error:

                print(
                    "[Monitor] Reauthentication "
                    "failed:"
                )

                print(error)

                print(
                    "[Monitor] Retrying in "
                    "10 seconds..."
                )

                await asyncio.sleep(10)

    # ========================================================
    # Reauthentication
    # ========================================================

    async def reauthenticate(self):

        print(
            "[VRChat] Reloading "
            "authentication token..."
        )

        new_token = (
            load_session_token()
        )

        if new_token != self.session_token:

            print(
                "[VRChat] New session token "
                "detected."
            )

        else:

            print(
                "[VRChat] Session token "
                "unchanged."
            )

        self.session_token = new_token

        if self.client:

            try:
                await self.client.close()

            except Exception:
                pass

        self.client = VRChatClient(
            self.session_token
        )

        await self.client.start()

        current_user = await (
            self.client.get_current_user()
        )

        username = current_user.get(
            "displayName"
        )

        print(
            f"[VRChat] Reauthenticated as: "
            f"{username}"
        )

        await self.connect_websocket()

        print(
            "[Monitor] VRChat connection "
            "restored."
        )

    # ========================================================
    # Get current user
    # ========================================================

    async def get_current_user(self):

        if not self.client:

            raise RuntimeError(
                "VRChat client is not connected."
            )

        return await (
            self.client.get_current_user()
        )

    # ========================================================
    # Stop
    # ========================================================

    async def stop(self):

        self.running = False

        if self.websocket_task:

            self.websocket_task.cancel()

            try:
                await self.websocket_task

            except asyncio.CancelledError:
                pass

            self.websocket_task = None

        if self.websocket:

            try:
                await self.websocket.disconnect()

            except Exception:
                pass

            self.websocket = None

        if self.client:

            try:
                await self.client.close()

            except Exception:
                pass

            self.client = None