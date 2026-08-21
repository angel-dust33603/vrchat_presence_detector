import asyncio

from vrchat import VRChatClient, load_session_token


async def main():
    print("Connecting to VRChat...")

    token = load_session_token()
    client = VRChatClient(token)

    try:
        await client.start()

        print("Getting friends...")

        friends = await client.get_friends()

        print(f"\nFound {len(friends)} friends.\n")

        for friend in friends:
            name = friend.get("displayName", "Unknown")
            user_id = friend.get("id", "Unknown")
            status = friend.get("status", "unknown")

            print(
                f"{name} → {user_id} → {status}"
            )

    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())