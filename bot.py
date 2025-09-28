import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
from discord_components import DiscordComponents

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
PREFIX = os.getenv("PREFIX", "!")
OWNER_ID = int(os.getenv("OWNER_ID")or 0)

intents = discord.Intents.default()
intents.members = True
intents.guilds = True
intents.messages = True

bot = commands.Bot(command_prefix=PREFIX, intents = intents)
bot.remove_command("help") # optional

@bot.event
async def on_ready():
    DiscordComponents(bot) # initialize the component system
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    # create DB if needed - each cog will ensure schema
    # Load cogs
    for cog in ("cogs.applications", "cogs.admin", "cogs.review"):
        try:
            bot.load_extension(cog)
            print(f"Loaded {cog}: {e}")
        except Exception as e:
            print(f"Failed to load {cog}: {e}")

if __name__ == "__main__":
    bot.run(TOKEN)
