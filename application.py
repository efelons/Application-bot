import os
import json
import asyncio
import aiosqlite
import discord
from discord.ext import commands
from discord_components import Button, ButtonStyle, Interaction

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config", "forms.json")
DB_PATH = os.path.join(BASE_DIR, "data", "app.db")
os.makedirs(os.path.join(BASE_DIR, "data"), exist_ok=True)
os.makedirs(os.path.join(BASE_DIR, "config"), exist_ok=True)

# Ensure config exists
if not os.path.exists(CONFIG_PATH):
    with open(CONFIG_PATH, "w") as f:
        json.dump({}, f, indent=2)

async def ensure_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            guild_id INTEGER NOT NULL,
            form_name TEXT NOT NULL,
            answers TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            reviewer_id INTEGER,
            decision_reason TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        """)
        await db.commit()

def load_forms():
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)

def save_forms(forms):
    with open(CONFIG_PATH, "w") as f:
        json.dump(forms, f, indent=2)

class Applications(commands.Cog):
    """Handles user-facing application flows."""

    def __init__(self, bot):
        self.bot = bot
        self.bot.loop.create_task(ensure_db())

    @commands.command()
    async def forms(self, ctx):
        """List all available forms"""
        forms = load_forms()
        if not forms:
            return await ctx.send("No forms available yet. Admins can create forms with `!createform`.")
        embed = discord.Embed(title="Available Forms", color=0x00aaff)
        for key, v in forms.items():
            q_count = len(v.get("questions", []))
            embed.add_field(name=key, value=f"{v.get('name', key)} — {q_count} questions\nUse `{ctx.prefix}apply {key}`", inline=False)
        await ctx.send(embed=embed)

    @commands.command()
    async def apply(self, ctx, form_key: str):
        """Start an application. Usage: !apply staff"""
        forms = load_forms()
        form = forms.get(form_key)
        if not form:
            return await ctx.send(f"Form `{form_key}` not found. Use `{ctx.prefix}forms` to see available forms.")

        # DM flow
        try:
            dm = await ctx.author.create_dm()
        except Exception:
            return await ctx.send("I can't DM you — please enable DMs and try again.")

        questions = form.get("questions", [])
        answers = []
        await dm.send(f"Starting application **{form.get('name', form_key)}**. You have 5 minutes per question. Reply `cancel` to cancel anytime.")

        for i, q in enumerate(questions, start=1):
            await dm.send(f"**Q{i}/{len(questions)}:** {q}")
            def check(m):
                return m.author.id == ctx.author.id and m.channel == dm
            try:
                msg = await self.bot.wait_for("message", check=check, timeout=300)
            except asyncio.TimeoutError:
                await dm.send("Timed out — application cancelled. You can run the command again when ready.")
                return
            if msg.content.lower().strip() == "cancel":
                await dm.send("Application cancelled.")
                return
            answers.append(msg.content.strip())

        # Save to DB
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO applications (user_id, guild_id, form_name, answers) VALUES (?, ?, ?, ?)",
                (ctx.author.id, ctx.guild.id if ctx.guild else 0, form_key, json.dumps(answers))
            )
            await db.commit()
            cursor = await db.execute("SELECT last_insert_rowid()")
            row = await cursor.fetchone()
            app_id = row[0]

        await dm.send("✅ Your application has been submitted. Thank you!")
        await ctx.send(f"{ctx.author.mention}, your application has been submitted (ID #{app_id}). Staff will review it soon.")

        # Post embed to review channel if set
        rc_id = form.get("review_channel_id")
        if rc_id:
            review_chan = ctx.guild.get_channel(rc_id)
            if review_chan:
                embed = discord.Embed(title=f"New Application — {form.get('name', form_key)}", color=0x3498db)
                embed.add_field(name="Applicant", value=f"{ctx.author} (`{ctx.author.id}`)", inline=False)
                for idx, q in enumerate(questions):
                    answer = answers[idx] if idx < len(answers) else "No answer"
                    embed.add_field(name=f"Q{idx+1}: {q}", value=answer[:1024], inline=False)
                embed.set_footer(text=f"App ID: {app_id}")
                # Buttons: Accept / Deny
                await review_chan.send(
                    embed=embed,
                    components=[
                        [
                            Button(style=ButtonStyle.green, label="Accept", custom_id=f"accept:{app_id}"),
                            Button(style=ButtonStyle.red, label="Deny", custom_id=f"deny:{app_id}")
                        ]
                    ]
                )
        else:
            # No review channel set
            await ctx.send("⚠️ Admins: this form doesn't have a review channel set. Use `!setreview <form> #channel`.")

def setup(bot):
    bot.add_cog(Applications(bot))
