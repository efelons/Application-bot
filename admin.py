import os
import json
import discord
from discord.ext import commands

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config", "forms.json")

def load_forms():
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)

def save_forms(forms):
    with open(CONFIG_PATH, "w") as f:
        json.dump(forms, f, indent=2)

def is_admin():
    async def predicate(ctx):
        return ctx.author.guild_permissions.manage_guild or ctx.author.id == ctx.bot.owner_id
    return commands.check(predicate)

class Admin(commands.Cog):
    """Admin commands for form management"""

    def __init__(self, bot):
        self.bot = bot
        self.config = load_forms()

    @commands.command()
    @is_admin()
    async def createform(self, ctx, key: str, *, display_name: str = None):
        """Create a new form: !createform staff "Staff Application" """
        forms = load_forms()
        if key in forms:
            return await ctx.send("A form with that key already exists.")
        forms[key] = {
            "name": display_name or key,
            "questions": [],
            "review_channel_id": None,
            "accepted_role_id": None,
            "reapply_cooldown_days": 30
        }
        save_forms(forms)
        await ctx.send(f"Form `{key}` created. Add questions with `!addquestion {key} \"Question text\"`.")

    @commands.command()
    @is_admin()
    async def addquestion(self, ctx, key: str, *, question: str):
        """Add question: !addquestion staff "Why do you want to join?" """
        forms = load_forms()
        form = forms.get(key)
        if not form:
            return await ctx.send("Form not found.")
        form.setdefault("questions", []).append(question)
        save_forms(forms)
        await ctx.send(f"Added question to `{key}`. Total questions: {len(form['questions'])}")

    @commands.command()
    @is_admin()
    async def listforms(self, ctx):
        forms = load_forms()
        embed = discord.Embed(title="Forms", color=0x2ecc71)
        for k, v in forms.items():
            embed.add_field(name=k, value=f"{v.get('name')} — {len(v.get('questions', []))} questions", inline=False)
        await ctx.send(embed=embed)

    @commands.command()
    @is_admin()
    async def setreview(self, ctx, key: str, channel: discord.TextChannel):
        forms = load_forms()
        if key not in forms:
            return await ctx.send("Form not found.")
        forms[key]["review_channel_id"] = channel.id
        save_forms(forms)
        await ctx.send(f"Set review channel for `{key}` to {channel.mention}")

    @commands.command()
    @is_admin()
    async def setacceptrole(self, ctx, key: str, role: discord.Role):
        forms = load_forms()
        if key not in forms:
            return await ctx.send("Form not found.")
        forms[key]["accepted_role_id"] = role.id
        save_forms(forms)
        await ctx.send(f"Set accept role for `{key}` to {role.mention}")

    @commands.command()
    @is_admin()
    async def removequestion(self, ctx, key: str, index: int):
        forms = load_forms()
        form = forms.get(key)
        if not form:
            return await ctx.send("Form not found.")
        try:
            q = form["questions"].pop(index)
            save_forms(forms)
            await ctx.send(f"Removed question: {q}")
        except Exception:
            await ctx.send("Invalid index. Use 0-based index.")

def setup(bot):
    bot.add_cog(Admin(bot))
