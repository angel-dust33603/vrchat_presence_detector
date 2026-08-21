import json
import logging
from pathlib import Path

import aiohttp


API_BASE = "https://api.vrchat.cloud/api/1"
COOKIE_FILE = Path("data/vrchat_session.json")

USER_AGENT = "VRC-DiscordPresence/1.0"


class VRChatAuthError(RuntimeError):
    """Raised when the VRChat session is no longer valid."""


class VRChatClient:

    def __init__(self, session_token: str):

        self.session_token = session_token
        self.session = None

        self.logger = logging.getLogger(
            "VRChat"
        )

    # ========================================================
    # Start HTTP session
    # ========================================================

    async def start(self):

        await self.close()

        self.session = aiohttp.ClientSession(
            headers={
                "User-Agent": USER_AGENT
            },
            cookies={
                "auth": self.session_token
            },
            timeout=aiohttp.ClientTimeout(
                total=30
            )
        )

    # ========================================================
    # Close HTTP session
    # ========================================================

    async def close(self):

        if self.session:

            await self.session.close()

            self.session = None

    # ========================================================
    # Make authenticated request
    # ========================================================

    async def _get(self, url, **kwargs):

        if not self.session:

            raise RuntimeError(
                "VRChat HTTP session is not started."
            )

        try:

            response = await self.session.get(
                url,
                **kwargs
            )

        except aiohttp.ClientError as error:

            raise RuntimeError(
                f"VRChat connection error: {error}"
            ) from error

        # ----------------------------------------------------
        # Authentication/session expired
        # ----------------------------------------------------

        if response.status in (401, 403):

            text = await response.text()

            raise VRChatAuthError(
                f"VRChat authentication failed "
                f"(HTTP {response.status}): {text}"
            )

        # ----------------------------------------------------
        # Other HTTP errors
        # ----------------------------------------------------

        if response.status != 200:

            text = await response.text()

            raise RuntimeError(
                f"VRChat API request failed "
                f"(HTTP {response.status}): {text}"
            )

        return await response.json()

    # ========================================================
    # Get currently authenticated user
    # ========================================================

    async def get_current_user(self):

        return await self._get(
            f"{API_BASE}/auth/user"
        )

    # ========================================================
    # Get a specific user
    # ========================================================

    async def get_user(
        self,
        user_id
    ):

        return await self._get(
            f"{API_BASE}/users/{user_id}"
        )

    # ========================================================
    # Get friends
    # ========================================================

    async def get_friends(self):

        all_friends = {}

        for offline in (False, True):

            friends = await self._get(
                f"{API_BASE}/auth/user/friends",
                params={
                    "offline": str(
                        offline
                    ).lower()
                }
            )

            for friend in friends:

                user_id = friend.get(
                    "id"
                )

                if user_id:

                    all_friends[
                        user_id
                    ] = friend

        return list(
            all_friends.values()
        )

    # ========================================================
    # Get own presence state
    # ========================================================

    async def get_own_state(self):

        user = await self.get_current_user()

        return {
            "id": user.get("id"),
            "displayName": user.get(
                "displayName"
            ),
            "state": user.get(
                "state",
                "offline"
            ),
            "status": user.get(
                "status",
                "offline"
            ),
            "location": user.get(
                "location"
            )
        }


# ============================================================
# Load VRChat session token
# ============================================================

def load_session_token():

    if not COOKIE_FILE.exists():

        raise FileNotFoundError(
            f"Could not find {COOKIE_FILE}"
        )

    try:

        with open(
            COOKIE_FILE,
            "r",
            encoding="utf-8"
        ) as file:

            data = json.load(file)

    except json.JSONDecodeError as error:

        raise ValueError(
            "vrchat_session.json contains "
            "invalid JSON."
        ) from error

    token = data.get(
        "auth"
    )

    if not token:

        raise ValueError(
            "No 'auth' value was found in "
            "vrchat_session.json"
        )

    return token