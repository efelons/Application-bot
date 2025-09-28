import os
import json
import aiosqlite
import discord
from discord.ext import commands
from discord_components import components, interaction, Button, ButtonStyle

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, "data", "app.db")
CONFIG_PATH = os.path.join(BASE_DIR, "config", "forms.json")

def load_forms():
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)

class Review(commands.Cog):
    """Commands to manage and review applications"""

    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def pending(self, ctx, limit: int = 10):
        """List pending applications"""
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute("SELECT id, user_id, form_name, timestamp FROM applications WHERE status = 'pending' ORDER BY timestamp DESC LIMIT ?", (limit,))
            rows = await cursor.fetchall()
        if not rows:
            return await ctx.send("No pending applications.")
        embed = discord.Embed(title="Pending Applications", color=0xf1c40f)
        for r in rows:
            app_id, user_id, form_name, ts = r
            member = ctx.guild.get_member(user_id) or f"<@{user_id}>"
            embed.add_field(name=f"#{app_id} — {form_name}", value=f"Applicant: {member}\nSubmitted: {ts}", inline=False)
        await ctx.send(embed=embed)

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def review(self, ctx, app_id: int):
        """Show an application embed by ID with Accept/Deny buttons"""
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute("SELECT user_id, form_name, answers, status FROM applications WHERE id = ?", (app_id,))
            row = await cursor.fetchone()
        if not row:
            return await ctx.send("Application not found.")
        user_id, form_name, answers_json, status = row
        answers = json.loads(answers_json)
        forms = load_forms()
        form = forms.get(form_name, {})
        questions = form.get("questions", [])
        embed = discord.Embed(title=f"Application #{app_id} — {form.get('name', form_name)}", color=0x9b59b6)
        embed.add_field(name="Applicant", value=f"<@{user_id}> (`{user_id}`)", inline=False)
        for i, q in enumerate(questions):
            a = answers[i] if i < len(answers) else "No answer"
            embed.add_field(name=f"Q{i+1}: {q}", value=a[:1024], inline=False)
        embed.set_footer(text=f"Status: {status}")
        # send with buttons
        message = await ctx.send(
            embed=embed,
            components=[
                [
                    Button(style=ButtonStyle.green, label="Accept", custom_id=f"accept:{app_id}"),
                    Button(style=ButtonStyle.red, label="Deny", custom_id=f"deny:{app_id}")
                ]
            ]
        )

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def accept(self, ctx, app_id: int, *, reason: str = "Accepted"):
        """Accept an application manually."""
        # fetch application
        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute("SELECT user_id, form_name FROM applications WHERE id = ?", (app_id,))
            row = await cur.fetchone()
            if not row:
                return await ctx.send("Application not found.")
            user_id, form_name = row
            forms = load_forms()
            form = forms.get(form_name, {})
            role_id = form.get("accepted_role_id")
            # update DB
            await db.execute("UPDATE applications SET status = 'accepted', reviewer_id = ?, decision_reason = ? WHERE id = ?", (ctx.author.id, reason, app_id))
            await db.commit()

        # assign role if possible and DM user
        guild = ctx.guild
        member = guild.get_member(user_id)
        if role_id and member:
            role = guild.get_role(role_id)
            if role:
                try:
                    await member.add_roles(role, reason=f"Application #{app_id} accepted by {ctx.author}")
                except Exception:
                    pass
        try:
            user = await self.bot.fetch_user(user_id)
            await user.send(f"🎉 Your application (ID #{app_id}) for **{form.get('name', form_name)}** was accepted.\nReason: {reason}")
        except Exception:
            pass

        await ctx.send(f"Application #{app_id} accepted. Notified applicant if possible.")

    @commands.command()
    @commands.has_permissions(manage_guild=True)
    async def deny(self, ctx, app_id: int, *, reason: str = "Denied"):
        """Deny an application manually."""
        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute("SELECT user_id, form_name FROM applications WHERE id = ?", (app_id,))
            row = await cur.fetchone()
            if not row:
                return await ctx.send("Application not found.")
            user_id, form_name = row
            await db.execute("UPDATE applications SET status = 'denied', reviewer_id = ?, decision_reason = ? WHERE id = ?", (ctx.author.id, reason, app_id))
            await db.commit()
        try:
            user = await self.bot.fetch_user(user_id)
            await user.send(f"Your application (ID #{app_id}) for **{form_name}** was denied.\nReason: {reason}")
        except Exception:
            pass
        await ctx.send(f"Application #{app_id} denied and applicant notified (if possible).")

    # This listens for button interactions posted by Applications cog
    @commands.Cog.listener()
    async def on_button_click(self, inter):
        # custom_id: "accept:123" or "deny:123"
        custom = inter.component.custom_id
        if not custom:
            return
        if custom.startswith("accept:") or custom.startswith("deny:"):
            action, sid = custom.split(":", 1)
            try:
                app_id = int(sid)
            except:
                return await inter.respond(type=6)  # ACK
            # require manage_guild
            member = inter.author
            guild = inter.guild
            perm = False
            if member.guild_permissions.manage_guild:
                perm = True
            if not perm:
                return await inter.respond(content="You don't have permission to do that.", ephemeral=True)
            if action == "accept":
                # call same logic as accept command
                await inter.respond(type=6)  # ACK to avoid "This interaction failed"
                # reuse command: find the cog and call accept
                await self._process_accept(inter, app_id, reviewer=member)
            else:
                await inter.respond(type=6)
                await self._process_deny(inter, app_id, reviewer=member)

    async def _process_accept(self, inter, app_id: int, reviewer):
        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute("SELECT user_id, form_name FROM applications WHERE id = ?", (app_id,))
            row = await cur.fetchone()
            if not row:
                await inter.channel.send("Application not found.")
                return
            user_id, form_name = row
            forms = load_forms()
            form = forms.get(form_name, {})
            role_id = form.get("accepted_role_id")
            await db.execute("UPDATE applications SET status = 'accepted', reviewer_id = ?, decision_reason = ? WHERE id = ?", (reviewer.id, f"Accepted by {reviewer}", app_id))
            await db.commit()
        member = inter.guild.get_member(user_id)
        if role_id and member:
            role = inter.guild.get_role(role_id)
            if role:
                try:
                    await member.add_roles(role, reason=f"Application #{app_id} accepted")
                except:
                    pass
        try:
            user = await self.bot.fetch_user(user_id)
            await user.send(f"Your application (ID #{app_id}) was accepted.")
        except:
            pass
        await inter.channel.send(f"Application #{app_id} accepted by {reviewer.mention}.")

    async def _process_deny(self, inter, app_id: int, reviewer):
        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute("SELECT user_id, form_name FROM applications WHERE id = ?", (app_id,))
            row = await cur.fetchone()
            if not row:
                await inter.channel.send("Application not found.")
                return
            user_id, form_name = row
            await db.execute("UPDATE applications SET status = 'denied', reviewer_id = ?, decision_reason = ? WHERE id = ?", (reviewer.id, f"Denied by {reviewer}", app_id))
            await db.commit()
        try:
            user = await self.bot.fetch_user(user_id)
            await user.send(f"Your application (ID #{app_id}) was denied.")
        except:
            pass
        await inter.channel.send(f"Application #{app_id} denied by {reviewer.mention}.")

def setup(bot):
    bot.add_cog(Review(bot))
