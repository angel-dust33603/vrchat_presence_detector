import discord
from discord import app_commands


# Only this Discord user can use /status
OWNER_ID = insert id here


def register_commands(
    command_tree,
    get_runtime_status,
    query_vrchat_presence
):
    """
    Register Discord slash commands.
    """

    @command_tree.command(
        name="status",
        description="Show the VRChat presence bot's current status."
    )
    async def status(interaction: discord.Interaction):

        # Restrict /status to the bot owner
        if interaction.user.id != OWNER_ID:
            await interaction.response.send_message(
                "❌ You don't have permission to use this command.",
                ephemeral=True
            )
            return

        data = get_runtime_status()

        runtime_seconds = int(data["runtime"])

        days, remainder = divmod(
            runtime_seconds,
            86400
        )

        hours, remainder = divmod(
            remainder,
            3600
        )

        minutes, seconds = divmod(
            remainder,
            60
        )

        if days:
            runtime = (
                f"{days}d "
                f"{hours}h "
                f"{minutes}m "
                f"{seconds}s"
            )

        elif hours:
            runtime = (
                f"{hours}h "
                f"{minutes}m "
                f"{seconds}s"
            )

        elif minutes:
            runtime = (
                f"{minutes}m "
                f"{seconds}s"
            )

        else:
            runtime = f"{seconds}s"

        discord_status = (
            "🟢 Connected"
            if data["discord_connected"]
            else "🔴 Disconnected"
        )

        vrchat_status = (
            "🟢 Connected"
            if data["vrchat_connected"]
            else "🔴 Disconnected"
        )

        websocket_status = (
            "🟢 Connected"
            if data["websocket_connected"]
            else "🔴 Disconnected"
        )

        embed = discord.Embed(
            title="🤖 Bot Status",
            color=discord.Color.green()
        )

        embed.add_field(
            name="Discord",
            value=discord_status,
            inline=True
        )

        embed.add_field(
            name="VRChat API",
            value=vrchat_status,
            inline=True
        )

        embed.add_field(
            name="WebSocket",
            value=websocket_status,
            inline=True
        )

        embed.add_field(
            name="Runtime",
            value=runtime,
            inline=False
        )

        embed.add_field(
            name="Watched Users",
            value=str(data["watched_users"]),
            inline=True
        )

        if data["vrchat_username"]:
            embed.add_field(
                name="VRChat Account",
                value=data["vrchat_username"],
                inline=True
            )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True
        )

    @command_tree.command(
        name="query",
        description="Show the current online/offline status of watched VRChat users."
    )
    async def query(interaction: discord.Interaction):

        await interaction.response.defer()

        try:
            results = await query_vrchat_presence()

        except Exception as error:

            await interaction.followup.send(
                "❌ Failed to query VRChat:\n"
                f"`{error}`",
                ephemeral=True
            )

            return

        online = []
        offline = []
        not_found = []

        for result in results:

            username = result["username"]
            status = result["status"]

            if status == "online":
                online.append(username)

            elif status == "offline":
                offline.append(username)

            else:
                not_found.append(username)

        lines = []

        if online:
            lines.append("🟢 **Online**")

            for username in online:
                lines.append(
                    f"🟢 **{username} is online**"
                )

            lines.append("")

        if offline:
            lines.append("🔴 **Offline**")

            for username in offline:
                lines.append(
                    f"🔴 **{username} is offline**"
                )

            lines.append("")

        if not_found:
            lines.append("⚠️ **Not found**")

            for username in not_found:
                lines.append(
                    f"⚠️ **{username} could not be found**"
                )

        if not lines:
            lines.append(
                "No watched users were found."
            )

        await interaction.followup.send(
            "\n".join(lines)
        )
