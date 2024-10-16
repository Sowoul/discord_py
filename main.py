import asyncio

import os
import random
import re
import time
from collections import deque, Counter
import math
import aiohttp
import discord
import yt_dlp
from aiohttp import ClientError
from discord.ext import commands
from discord.utils import get
from urllib.request import Request, urlopen
import os
from dotenv import load_dotenv

from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker , relationship, Query

Base = declarative_base()

class Economy(Base):
    __tablename__ = "economy"
    id = Column(Integer, ForeignKey("user.id"), primary_key=True, default=0)
    cash = Column(Integer)
    user = relationship("User", back_populates="economy")

class User(Base):
    __tablename__ = "user"
    id = Column(Integer, primary_key=True)
    name = Column(String)
    avatar = Column(String)
    roles = relationship("UserRole", back_populates="user")
    economy = relationship("Economy", back_populates="user", uselist=False)

class UserRole(Base):
    __tablename__ = "userrole"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user.id"))
    role_id = Column(Integer, ForeignKey("role.id"))
    user = relationship("User", back_populates="roles")
    role = relationship("Role", back_populates="users")

class Role(Base):
    __tablename__ = "role"
    id = Column(Integer, primary_key=True)
    name = Column(String)
    users = relationship("UserRole", back_populates="role")

engine = create_engine("sqlite:///db.sqlite3")
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)
session = Session()

class Diddler(commands.Bot):
    def __init__(self,**kwargs) -> None:
        super().__init__(intents=discord.Intents.all(), command_prefix=kwargs.get('command_prefix', "$"))
        self.changelogs = deque(maxlen=50)
        self.logs = deque(maxlen=50)
        self.song_queue = deque(maxlen=20)
        self.muted_role : discord.Role | None = None
        self.words = []
        self.wordle = {}
        self.color_roles = {}
        self.games = {}
        self.nums = [i for i in range(0,1001)]
        self.weights =[(1/(i+1))**1.2 if i<100 else 1/(i+1)**2 for i in range(0,1001)]
        self.cooldowns = {}
        self.black = {}

    def deleted(self, message : discord.Message) -> None:
        embed = discord.Embed(description=f"**Message**: {message.content}", color=0x00ff00)
        embed.set_author(name=f"{message.author}", icon_url=message.author.avatar.url if message.author.avatar else None)
        embed.set_footer(text=f"Deleted in #{message.channel}")
        self.logs.append(embed)

    def edited_message(self, before : discord.Message, after: discord.Message) -> None:
        embed = discord.Embed(description=f"**Before**: {before.content}\n **After**: {after.content}", color=0x00ff00)
        embed.set_author(name=f"{before.author}", icon_url=before.author.avatar.url if before.author.avatar else None)
        embed.set_footer(text=f"Edited in #{before.channel}")
        self.changelogs.append(embed)

    def snipe(self, num) -> str:
        if len(self.logs)<num:
            raise ValueError("Not enough messages to snipe")
        return self.logs[-num]
    def esnipe(self,num) ->str:
        if len(self.changelogs)<num:
            raise ValueError("Not enough messages to esnipe")
        return self.changelogs[-num]

bot = Diddler(command_prefix = "$")


load_dotenv()
intents = discord.Intents.all()
channels = {
    "general": 1288765788051738687,
    "member_info_vc": 1289161212487143444
}

async def update_member_count(guild):
    vc = await guild.fetch_channel(channels["member_info_vc"])
    await vc.edit(name=f"Members: {guild.member_count}")

async def periodic_member_count_update(guild):
    while True:
        await update_member_count(guild)
        await asyncio.sleep(3000)

async def load_words():
    with open('words.txt' , 'r') as file:
        bot.words = file.read().split(' ')[:-1]
        print(f"{len(bot.words)} words loaded")



async def scrape_movie_info(movie, max_retries=5, delay=2):
    url = f'https://www.theflixertv.to/search/{movie}'

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'DNT': '1',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
    }

    async with aiohttp.ClientSession() as sessin:
        for attempt in range(max_retries):
            try:
                async with sessin.get(url, headers=headers, timeout=10) as response:
                    if response.status == 200:
                        f = await response.text()

                        pattern = r'<img data-src="(https://[^"]+)"[^>]*class="film-poster-img[^>]*>.*?<a href="([^"]+)"[^>]*class="film-poster-ahref".*?<h2 class="film-name"><a[^>]*>([^<]+)</a>'

                        matches = re.findall(pattern, f, re.DOTALL)

                        results = []
                        for image_url, movie_url, title in matches:
                            results.append({
                                'image_url': image_url,
                                'movie_url': f"https://www.theflixertv.to{movie_url}",
                                'title': title.strip()
                            })

                        return results
                    else:
                        raise ClientError(f"HTTP error {response.status}")

            except (ClientError, asyncio.TimeoutError) as e:
                if attempt < max_retries - 1:
                    await asyncio.sleep(delay + random.uniform(0, 1))
                else:
                    raise Exception(f"Failed to fetch data after {max_retries} attempts: {str(e)}")


async def send_msg():
    async def add_role(interaction : discord.Interaction):
        role = bot.color_roles[interaction.data['custom_id']]
        if role in interaction.user.roles:
            asyncio.create_task(interaction.response.send_message(f"Removed {role.mention} from {interaction.user.mention}", ephemeral=True))
            await interaction.user.remove_roles(role)
            return
        asyncio.create_task(interaction.response.send_message(f"Added {role.mention} to {interaction.user.mention}", ephemeral=True))
        await interaction.user.add_roles(role)

    stores = {
        'red' : '🟥',
        'green' : '🟩',
        'blue' : '🟦',
        'yellow' : '🟨',
        'pink' : '🐷',
        'orange' : '🟧',
        'purple' : '🟪'
    }
    view = discord.ui.View(timeout=None)
    for color in stores.keys():
        role_id = session.query(Role).filter_by(name = color).first()
        role = bot.guilds[0].get_role(role_id.id)
        bot.color_roles[color] = role
        button = discord.ui.Button(emoji=stores[color], style=discord.ButtonStyle.secondary, custom_id=f"{color}")
        button.callback = add_role
        view.add_item(button)
    embed = discord.Embed(title="Select a color", color=0x00ff00)
    embed.add_field(name="", value=f"{', '.join([role.mention for role in bot.color_roles.values()])}")
    embed.set_author(name=f"{bot.user.name}", icon_url=bot.user.avatar.url)
    rc = get(bot.guilds[0].channels, id = 1294954582941896746)
    old_message = await rc.fetch_message(1294981556036833341)
    if old_message:
        await old_message.edit(embed=embed, view=view)
    else:
        await rc.send(embed=embed, view=view)
@bot.event
async def on_ready():
    print(f"Bot is ready as {bot.user}")
    await bot.change_presence(activity=discord.Game(name="Ur mother"))
    asyncio.create_task(load_words())
    async def add_muted_role_to_db():
        for role in bot.guilds[0].roles:
            existing_role = session.query(Role).filter_by(id=role.id).first()
            if existing_role:
                existing_role.name = role.name
            else:
                new_role = Role(id=role.id, name=role.name)
                session.add(new_role)
            session.commit()
        print("Roles added to db")
    async def add_user_to_database():
        for member in bot.guilds[0].members:
            existing_user = session.query(User).filter_by(id=member.id).first()
            if existing_user:
                old_cash = session.query(Economy).filter_by(id = member.id).first()
                if not old_cash:
                    add_cash = Economy(id = existing_user.id, cash = 0)
                    session.add(add_cash)
                existing_user.name = member.name
                existing_user.avatar = member.avatar.url if member.avatar else None
            else:
                new_user = User(id=member.id, name=member.name, avatar=member.avatar.url if member.avatar else None)
                new_cash = Economy(id = new_user.id, cash=0)
                session.add(new_cash)
                session.add(new_user)
            session.commit()

            for role in member.roles:
                existing_user_role = session.query(UserRole).filter_by(user_id=member.id, role_id=role.id).first()
                if not existing_user_role:
                    new_user_role = UserRole(user_id=member.id, role_id=role.id)
                    session.add(new_user_role)
            session.commit()
        print("Users added to db")
    bot.muted_role = get(bot.guilds[0].roles, name="muted")
    asyncio.gather(add_muted_role_to_db(), send_msg(), add_user_to_database())
    if not bot.muted_role:
        bot.muted_role = await bot.guilds[0].create_role(name="muted")
        print("Making a new role")
        await asyncio.gather(*(channel.set_permissions(bot.muted_role, speak=False, send_messages=False) for channel in bot.guilds[0].channels))
    print("Muted role is set up.")
    for guild in bot.guilds:
        bot.loop.create_task(periodic_member_count_update(guild))

@bot.event
async def on_message(message):
    async def sendmsg():
        if message.channel.id==1293821426616369232 and not message.content.isdigit():
            await message.delete()
    asyncio.create_task(sendmsg())
    if message.channel.id!=1293821426616369232:
        await bot.process_commands(message)

@bot.event
async def on_command_error(ctx, error):
    embed = discord.Embed(description=f"**Command**: {ctx.message.content}\n **Error**: {error}", color=0xff0000)
    embed.set_author(name=f"{ctx.author}", icon_url=ctx.author.avatar.url if ctx.author.avatar else None)
    embed.set_footer(text=f"Error in #{ctx.channel}")
    await ctx.send(embed=embed)

@bot.event
async def on_message_edit(before, after):
    if before.author == bot.user:
        return
    if before.channel.id == 1293821426616369232 and not after.content.isdigit():
        await after.delete()
        return
    bot.edited_message(before, after)

@bot.event
async def on_member_update(before, after):
    async def modify_user():
        id = before.id
        existing = session.query(User).filter_by(id=id).first()

        if existing:
            if before.nick != after.nick:
                existing.name = after.nick

            before_role_ids = {role.id for role in before.roles}
            after_role_ids = {role.id for role in after.roles}
            for role in before.roles:
                if role.id not in after_role_ids:
                    user_role = session.query(UserRole).filter_by(user_id=before.id, role_id=role.id).first()
                    if user_role:
                        session.delete(user_role)

            for role in after.roles:
                if role.id not in before_role_ids:
                    role_in_db = session.query(Role).filter_by(id=role.id).first()
                    if not role_in_db:
                        role_in_db = Role(id=role.id, name=role.name)
                        session.add(role_in_db)
                        session.commit()

                    user_role = UserRole(user_id=before.id, role_id=role.id)
                    session.add(user_role)
            session.commit()

    asyncio.create_task(modify_user())

@bot.event
async def on_message_delete(message):
    if message.author == bot.user:
        return
    bot.deleted(message)

@bot.event
async def on_member_join(member : discord.Member):
    gen = await member.guild.fetch_channel(channels["general"])
    async def hello_there():
        embed = discord.Embed(description=f"{member.mention} has joined the server", color=discord.Color.random())
        embed.set_author(name=f"{member}", icon_url=member.avatar.url if member.avatar else None)
        embed.set_footer(text=f"Member count: {member.guild.member_count}")
        await gen.send(embed=embed)
    async def add_user_to_database():
        existing = session.query(User).filter_by(id=member.id).first()
        if existing:
            roles = [get(bot.guilds[0].roles, id = role.role_id) for role in existing.roles if role.role_id!=1287525272748560496]
        else:
            role = get(member.guild.roles, name="diddy's victim")
            roles = [role]
            existing = User(id=member.id, name=member.name, avatar=member.avatar.url if member.avatar else None)
            money = Economy(id=existing.id, cash=0)
            session.add(money)
            session.add(existing)
            session.commit()
        async def ad_role(role):
            try:
                await member.add_roles(role)
            except Exception as e:
                print(f"{e} occured in {role}")
        asyncio.gather(*(ad_role(role) for role in roles))
    asyncio.gather(hello_there(), add_user_to_database())


@bot.event
async def on_member_remove(member):
    gen = await member.guild.fetch_channel(channels["general"])
    embed = discord.Embed(description=f"{member.mention} has left the server", color=discord.Color.random())
    embed.set_author(name=f"{member}", icon_url=member.avatar.url if member.avatar else None)
    embed.set_footer(text=f"Member count: {member.guild.member_count}")
    await gen.send(embed=embed)

@bot.event
async def on_voice_state_update(member, before, after):
    if not before:
        return
    if not after or before.channel != after.channel:
        voice_client = member.guild.voice_client
        if voice_client and voice_client.channel:
            if len(voice_client.channel.members) == 1:
                await voice_client.disconnect()
                bot.song_queue = deque()

@bot.command(aliases=["hi", "hey"])
async def hello(ctx):
    embed= discord.Embed(description=(f"Hello there {ctx.author.mention}, want some kids?"), color=0x00ff00)
    await ctx.send(embed=embed)

@bot.command(aliases=[])
async def snipe(ctx, nums = 1):
    if nums>len(bot.logs):
        await ctx.send(embed = discord.Embed(description="Not enough messages to snipe", color = 0x00ff00))
        return
    await ctx.send(embed = bot.snipe(nums))

@bot.command(aliases=["esnipe"])
async def changelog(ctx, nums = 1):
    if nums>len(bot.changelogs):
        await ctx.send(embed = discord.Embed(description="Not enough messages to esnipe", color = 0x00ff01))
        return
    await ctx.send(embed = bot.esnipe(nums))

@bot.command()
async def ping(ctx):
    await ctx.send(f"Pong! {round(bot.latency * 1000)}ms")

@bot.command()
async def snake(ctx):
    await ctx.send(embed = discord.Embed(description="snake-ogii.onrender.com"))

@bot.command()
async def spank(ctx, to_spank : discord.Member | None | discord.User= None):
    from_spank = ctx.author
    if not to_spank:
        to_spank = await bot.fetch_user(470142142287970305)
    embed = discord.Embed(description=f"{from_spank.mention} oiled up and spanked {to_spank.mention}", color=0x00ff00)
    embed.set_image(url="https://media1.tenor.com/m/V8vUcWo4dLIAAAAC/spank-peach.gif")
    embed.set_author(name=f"{from_spank}", icon_url=from_spank.avatar.url if from_spank.avatar else None)
    await ctx.send(embed=embed)

@bot.command()
async def kiss(ctx , to_kiss = None):
    from_kiss = ctx.author
    if not to_kiss:
        to_kiss = await bot.fetch_user(1247271643009777704)
    embed = discord.Embed(color=0x00ff00, description = f"{from_kiss.mention} ***smooches*** {to_kiss}")
    embed.set_image(url="https://media1.tenor.com/m/o_5RQarGvJ0AAAAC/kiss.gif")
    embed.set_author(name=f"{from_kiss}", icon_url=from_kiss.avatar.url if from_kiss.avatar else None)
    await ctx.send(embed=embed)

@bot.command()
@commands.has_permissions(administrator=True)
async def mute(ctx, member: discord.Member):
    if not member:
        await ctx.send("Please specify a member to mute.")
        return
    async def add_role():
        muted_role = bot.muted_role
        await member.add_roles(muted_role, reason=f"Muted by {ctx.author}")
    asyncio.create_task(add_role())
    embed = discord.Embed(description=f"{member.mention} has been muted by {ctx.author.mention}", color=0x00ff00)
    await ctx.send(embed=embed)

@bot.command()
@commands.has_permissions(administrator=True)
async def unmute(ctx, member: discord.Member):
    if not member:
        await ctx.send("Please specify a member to mute.")
        return
    async def add_role():
        muted_role = bot.muted_role
        await member.remove_roles(muted_role, reason=f"Unmuted by {ctx.author}")
    asyncio.create_task(add_role())
    embed = discord.Embed(description=f"{member.mention} has been unmuted by {ctx.author.mention}", color=0x00ff00)
    await ctx.send(embed=embed)

@bot.command()
@commands.has_permissions(administrator=True)
async def kick(ctx, to_kick : discord.Member):
    if sum(1 for i in to_kick.roles if i.name == ":/") == 1:
        await ctx.send("no")
        return
    async def send_msg():
        embed = discord.Embed(description=f"{to_kick.mention} has been kicked by {ctx.author.mention}", color=0x00ff00)
        await ctx.send(embed=embed)
    asyncio.gather( to_kick.kick() , send_msg())

@bot.command()
@commands.has_permissions(administrator=True)
async def ban(ctx, to_ban : discord.Member, reason : str | None = None):
    if sum(1 for i in to_ban.roles if i.name == ":/") == 1:
        await ctx.send("no")
        return
    async def send_msg():
        embed = discord.Embed(description=f"{to_ban.mention} has been banned by {ctx.author.mention}", color=0x00ff00)
        await ctx.send(embed=embed)

    asyncio.gather(to_ban.ban(reason=reason, delete_message_days=0) , send_msg())

@bot.command()
@commands.has_permissions(administrator=True)
async def unban(ctx, to_unban : str | None = None):
    if not to_unban:
        await ctx.send("who to unban")
        return
    member =  await bot.fetch_user(to_unban)
    async def send_msg():
        embed = discord.Embed(description=f"{member.mention} has been unbanned by {ctx.author.mention}", color=0x00ff00)
        await ctx.send(embed=embed)
    asyncio.gather(ctx.guild.unban(member) , send_msg())


@bot.command()
async def invite(ctx):
    await ctx.send(f"Invite link: {discord.utils.oauth_url(bot.user.id)}")

@bot.command()
async def poll(ctx, *, question):
    embed = discord.Embed(title="Poll", description=question, color=0x00ff00)
    embed.set_author(name=ctx.author.name, icon_url=ctx.author.avatar.url if ctx.author.avatar else None)
    embed.set_footer(text=f"Poll created by {ctx.author.name}", icon_url=ctx.author.avatar.url if ctx.author.avatar else None)
    poll_message = await ctx.send(embed=embed)
    for emoji in ["👍", "👎", "🤷‍♂️"]:
        await poll_message.add_reaction(emoji)

@bot.command(aliases=["choose"])
async def rand(ctx,*, args : str=""):
    if not args:
        await ctx.send("Your mom a hoe")
        return
    temp = args.split(",")
    embed = discord.Embed(description=f"**I** chose **{random.choice(temp)}**", color=0x00ff00)
    embed.set_author(name=f"{ctx.author}", icon_url=ctx.author.avatar.url if ctx.author.avatar else None)
    await ctx.send(embed=embed)

@bot.command()
async def pp(ctx, user : discord.Member = None):
    if not user:
        user = ctx.author
    if "woman" in {role.name.lower() for role in ctx.guild.get_member(user.id).roles}:
        embed = discord.Embed(description=f"{user.mention} has no pp", color=0x00ff00)
        embed.set_author(name=f"{user}", icon_url=user.avatar.url if user.avatar else None)
        await ctx.send(embed=embed)
        return
    ppsize = f"8{"="*random.randint(2,8)}D" if user.id != 909101433083813958 else f"8{'='*random.randint(8,14)}D"
    embed = discord.Embed(description=f"{user.mention} has a {ppsize} pp", color=0x00ff00)
    embed.set_author(name=f"{user}", icon_url=user.avatar.url if user.avatar else None)
    await ctx.send(embed=embed)

@bot.command()
async def gayrate(ctx, user : discord.Member | None = None):
    if not user:
        user = ctx.author
    gayrate = random.gauss(50, 20)
    gayrate = max(0, min(100, gayrate))
    if random.randint(0,1000) == 69:
        gayrate = 1000
    embed = discord.Embed(description=f"{user.mention} is {gayrate}% gay", color=0x00ff00)
    embed.set_author(name=f"{user}", icon_url=user.avatar.url if user.avatar else None)
    await ctx.send(embed=embed)

@bot.command()
async def touch(ctx, user : discord.Member | None = None):
    if not user:
        user = ctx.author
    embed = discord.Embed(description=f"{ctx.author.mention} touched {user.mention}", color=0x00ff00)
    embed.set_image(url="https://media.discordapp.net/attachments/1125755890704863312/1223572603046985789/makesweet-x0u4zi.gif?ex=66f530c9&is=66f3df49&hm=9c877be4ca80702f0be44890c4fbf88824d1a8ec964de276f6889e5aadf13e2e&")
    embed.set_author(name=f"{ctx.author}", icon_url=ctx.author.avatar.url if ctx.author.avatar else None)
    await ctx.send(embed=embed)

@bot.command(aliases=["kms","suicide","killme","endme","die","murder","uicide"])
async def kickme(ctx):
    start = time.time()
    inv = os.environ.get("INVITE")
    await ctx.author.send(f"yoo why you leave the party?? come back!\n{inv}")
    async def he_left():
        embed = discord.Embed(description=f"{ctx.author.mention} killed themselves", color=0x00ff00)
        embed.set_author(name=f"{ctx.author}", icon_url=ctx.author.avatar.url if ctx.author.avatar else None)
        await ctx.send(embed=embed)
    asyncio.gather(ctx.author.kick(reason="He asked for it."),he_left())
    print(time.time() - start)

@bot.command()
async def roulette(ctx, user : discord.Member | None = None):
    if not user:
        user = ctx.author
    embed = discord.Embed(color=0x00ff00)
    if random.randint(0,6) == 1:
        embed.description = f"{user.mention} died"
        embed.set_image(url = "https://images-ext-1.discordapp.net/external/NbnFjJTry-slSIXdkS0APwB-nVTeDz_yr0wdPCwvNBw/https/media.tenor.com/3ni-e-SSFYsAAAPo/outlast-game.mp4")
    else:
        embed.description = f"{user.mention} survived"
    embed.set_author(name=f"{ctx.author}", icon_url=ctx.author.avatar.url if ctx.author.avatar else None)
    await ctx.send(embed=embed)

@bot.command()
async def watch(ctx, *, movie):
    movie = movie.replace(" ", "-")
    message = await ctx.send("Searching for movies...")

    async def update_results():
        try:
            results = await scrape_movie_info(movie)
            if not results:
                await message.edit(content="No results found.")
                return

            embeds = []
            for i, result in enumerate(results):
                embed = discord.Embed(title=result['title'], url=result['movie_url'], color=0x00ff00)
                embed.set_image(url=result['image_url'])
                embed.set_footer(text=f"Result {i+1}/{len(results)}")
                embeds.append(embed)

            current_page = 0
            await message.edit(content=None, embed=embeds[current_page])

            await message.add_reaction("⬅️")
            await message.add_reaction("➡️")

            def check(reaction, user):
                return user == ctx.author and str(reaction.emoji) in ["⬅️", "➡️"] and reaction.message.id == message.id

            while True:
                try:
                    reaction, user = await bot.wait_for("reaction_add", timeout=60.0, check=check)

                    if str(reaction.emoji) == "➡️" and current_page < len(embeds) - 1:
                        current_page += 1
                        await message.edit(embed=embeds[current_page])
                    elif str(reaction.emoji) == "⬅️" and current_page > 0:
                        current_page -= 1
                        await message.edit(embed=embeds[current_page])

                    await message.remove_reaction(reaction, user)

                except asyncio.TimeoutError:
                    await message.clear_reactions()
                    break

        except Exception as e:
            await message.edit(content=f"An error occurred: {str(e)}")
    asyncio.create_task(update_results())

@bot.command(aliases=["join"])
async def join_vc(ctx):
    if ctx.voice_client and ctx.voice_client.channel != ctx.author.voice.channel:
        await ctx.send("You arent in the party lil bro")
        return
    if not ctx.author.voice:
        await ctx.send("You arent in a vc")
        return
    await ctx.author.voice.channel.connect()

@bot.command(aliases=["leave"])
async def leave_vc(ctx):
    if ctx.voice_client and ctx.voice_client.channel != ctx.author.voice.channel:
        await ctx.send("You arent in the party lil bro")
        return
    if not ctx.author.voice:
        await ctx.send("You arent in a vc")
        return
    await ctx.voice_client.disconnect()


@bot.command(aliases=["play"])
async def play_music(ctx, youtube_url: str):
    if ctx.voice_client and ctx.voice_client.channel != ctx.author.voice.channel:
        await ctx.send("You aren't in the party lil bro")
        return
    if not ctx.voice_client:
        if ctx.author.voice:
            await ctx.author.voice.channel.connect()
        else:
            await ctx.send("You're not in the party")
            return

    embed = discord.Embed(description=f"Loading: {youtube_url}", color=0x00ff00)
    msg = await ctx.send(embed=embed)

    ydl_opts = {
        'format': 'bestaudio/best',
        'quiet': True,
        'default_search': 'auto',
        'geo_bypass': True,
        'no_warnings': True,
        'ignoreerrors': False,
        'username': os.environ.get("YT_USERNAME"),
        'password': os.environ.get("YT_PASSWORD"),
        'user_agent': (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/91.0.4472.124 Safari/537.36'
        )
    }

    async def play_next(ctx):
        if bot.song_queue:
            next_song = bot.song_queue.popleft()
            await play_music(ctx, next_song)

    def after_playing(error):
        coro = play_next(ctx)
        fut = asyncio.run_coroutine_threadsafe(coro, bot.loop)
        try:
            fut.result()
        except Exception as e:
            print(f"Error occurred: {e}")

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(youtube_url, download=False)
            if 'entries' in info:
                info = info['entries'][0]
            audio_url = info['url']
    except yt_dlp.utils.DownloadError as e:
        await msg.edit(content=f"An error occurred while extracting audio: {e}")
        return
    except Exception as e:
        await msg.edit(content=f"An unexpected error occurred: {e}")
        return

    source = discord.FFmpegPCMAudio(audio_url)
    if ctx.voice_client.is_playing():
        bot.song_queue.append(youtube_url)
        embed = discord.Embed(description=f"Added to queue: [{info.get('title', 'Unknown Title')}]({youtube_url})", color=0x00ff00)
        await msg.edit(embed=embed)
    else:
        ctx.voice_client.play(source, after=after_playing)
        embed = discord.Embed(description=f"Now playing: [{info.get('title', 'Unknown Title')}]({youtube_url})", color=0x00ff00)
        await msg.edit(embed=embed)

@bot.command()
async def stop(ctx):
    if ctx.voice_client and ctx.voice_client.channel != ctx.author.voice.channel:
        await ctx.send("You arent in the party lil bro")
        return

    if not ctx.author.voice:
        await ctx.send("You arent in a vc")
        return

    if ctx.voice_client:
        ctx.voice_client.stop()
        await ctx.send("Music stopped.")
    else:
        await ctx.send("I'm not in a voice channel.")

@bot.command(aliases=["search"])
async def search_song(ctx, *, song):
    if ctx.voice_client and ctx.voice_client.channel != ctx.author.voice.channel:
        await ctx.send("You aren't in the party lil bro")
        return
    if not ctx.voice_client:
        if ctx.author.voice:
            await ctx.author.voice.channel.connect()
        else:
            await ctx.send("You're not in the party")
            return

    embed = discord.Embed(description=f"Searching for: {song}", color=0x00ff00)
    msg = await ctx.send(embed=embed)

    async def getinfo_song(song):
        ydl_opts = {
            'format': 'bestaudio/best',
            'quiet': True,
            'default_search': 'auto',
            'geo_bypass': True,
            'no_warnings': True,
            'ignoreerrors': False,
            'username': os.environ.get("YT_USERNAME"),
            'password': os.environ.get("YT_PASSWORD"),
            'user_agent': (
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/91.0.4472.124 Safari/537.36'
            )
        }

        async def play_next(ctx):
            if bot.song_queue:
                next_song = bot.song_queue.popleft()
                await play_music(ctx, next_song)

        def after_playing(error):
            coro = play_next(ctx)
            fut = asyncio.run_coroutine_threadsafe(coro, bot.loop)
            try:
                fut.result()
            except Exception as e:
                print(f"Error occurred: {e}")

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(f"ytsearch:{song}", download=False)
                if 'entries' in info:
                    info = info['entries'][0]
                audio_url = info['url']
        except yt_dlp.utils.DownloadError as e:
            await msg.edit(content=f"An error occurred while extracting audio: {e}")
            return
        except Exception as e:
            await msg.edit(content=f"An unexpected error occurred: {e}")
            return

        source = discord.FFmpegPCMAudio(audio_url)
        if ctx.voice_client.is_playing():
            bot.song_queue.append(f"ytsearch:{song}")
            embed = discord.Embed(description=f"Added to queue: [{info.get('title', 'Unknown Title')}]", color=0x00ff00)
            await msg.edit(embed=embed)
        else:
            ctx.voice_client.play(source, after=after_playing)
            embed = discord.Embed(description=f"Now playing: [{info.get('title', 'Unknown Title')}]", color=0x00ff00)
            await msg.edit(embed=embed)

    asyncio.create_task(getinfo_song(song))

@bot.command(aliases=["skip"])
async def next(ctx):
    if ctx.voice_client and ctx.voice_client.channel != ctx.author.voice.channel:
        await ctx.send("You aren't in the party lil bro")
        return
    if not ctx.voice_client:
        await ctx.send("You're not in the party")
        return
    if ctx.voice_client:
        ctx.voice_client.stop()
        await ctx.send("Skipped the song.")
    else:
        await ctx.send("I'm not in a voice channel.")

@bot.command()
async def boobs(ctx, user : discord.Member = None):
    if not user:
        user = ctx.author
    embed = discord.Embed(description=f"{user.mention}'s chesticles",color=0x00ff00)
    embed.set_author(name=f"{user}", icon_url=user.avatar.url if user.avatar else None)
    embed.set_image(url='https://media1.tenor.com/m/wQnHMN5pJXAAAAAd/mynameisgus-gusfring.gif')
    await ctx.send(embed=embed)

@bot.command()
@commands.has_permissions(administrator=True)
async def purge(ctx : discord.ext.commands.Context, nums=5):
    start = time.time()
    nums = int(nums)
    nums = min(100,nums)
    before = bot.logs
    await ctx.channel.purge(limit = nums)
    bot.logs = before

@bot.command()
@commands.has_permissions(administrator=True)
async def userpurge(ctx : discord.ext.commands.Context,member : discord.Member, nums=5):
    nums = int(nums)
    nums = min(100,nums)
    before = bot.logs
    await ctx.channel.purge(limit = nums, check=lambda msg: msg.author == member)
    bot.logs = before

@bot.command(aliases=["avatar"])
async def pfp(ctx, member:discord.Member=None):
    if not member:
        member = ctx.author
    embed = discord.Embed(color=0x00ff00, description = f"{member.mention}'s avatar was searched by {ctx.author.mention}")
    embed.set_image(url = member.avatar.url)
    embed.set_author(name=member,icon_url = member.avatar.url)
    await ctx.send(embed = embed)

class Timer:
    def __init__(self, ctx, time):
        self.ctx = ctx
        self.time = time
    async def start_timer(self):
        await self.ctx.send(embed = discord.Embed(description = f"Timer started for {self.time} seconds by {self.ctx.author.mention}", color = 0x00ff00))
        self.task = asyncio.create_task(self.countdown())
    async def countdown(self):
        await asyncio.sleep(self.time)
        await self.ctx.send(f"{self.ctx.author.mention}", embed = discord.Embed(description = f"Timer ended by {self.ctx.author.mention}", color = 0x00ff00))

@bot.command()
async def timer(ctx, time):
    if not time.isdigit():
        await ctx.send("That aint a number")
        return
    timer = Timer(ctx, int(time))
    await timer.start_timer()

# class Wordle():
#     def __init__(self, ctx):
#         self.word = random.choice(bot.words)
#         self.tries = 0
#         self.author = ctx.author
#         self.ctx = ctx
#         self.options  = {
#                 'wrong' : "⬛",
#                 'right' : "🟩",
#                 'unplaced': "🟨"
#                 }
#         self.message = ""
#         print(self.word)

#     async def check(self, word):
#         if len(word) != 5:
#             await self.ctx.send("The word must be 5 letters long")
#             return

#         count = 0
#         word_matched = [False] * 5
#         guess_matched = [False] * 5
#         temp = [self.options['unplaced']] * 5
#         for idx, val in enumerate(word):
#             if val == self.word[idx]:
#                 count += 1
#                 temp[idx] = self.options['right']
#                 word_matched[idx] = True
#                 guess_matched[idx] = True

#         for idx, val in enumerate(word):
#             if not guess_matched[idx]:
#                 if val in self.word:
#                     for target_idx in range(5):
#                         if val == self.word[target_idx] and not word_matched[target_idx]:
#                             temp[target_idx] = self.options['unplaced']
#                             word_matched[target_idx] = True
#                             guess_matched[idx] = True
#                             break
#                 if not guess_matched[idx]:
#                     temp[idx] = self.options['wrong']
#         self.message+= "".join(temp)
#         self.message += f" {word}"
#         self.tries += 1

#         embed = discord.Embed(description=self.message, color=0x00ff00)
#         embed.set_author(name=self.ctx.author, icon_url=self.ctx.author.avatar.url)
#         embed.set_footer(text=f"{6 - self.tries} tries remaining")
#         await self.ctx.send(embed=embed)
#         self.message+='\n'
#         if count == 5:
#             await self.ctx.send(embed=discord.Embed(description=f"Congrats {self.ctx.author.mention}, you guessed the word!", color=0x00ff00))
#             del bot.wordle[self.ctx.author]
#             return

#         if self.tries == 6:
#             await self.ctx.send(embed=discord.Embed(description=f"{self.ctx.author.mention} game over! The word was '{self.word}'.", color=0xff0000))
#             del bot.wordle[self.ctx.author]

# @bot.command()
# async def wordle(ctx, word):
#     if ctx.author not in bot.wordle:
#         bot.wordle[ctx.author] = Wordle(ctx)
#     game = bot.wordle[ctx.author]
#     game.ctx = ctx
#     await game.check(word)

class Butt(discord.ui.View):
    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        self.butt = discord.ui.Button(label="Butt", style=discord.ButtonStyle.primary, custom_id="butt")
        self.butt.callback = self.show_butt
        self.add_item(self.butt)

    async def show_butt(self, interaction : discord.Interaction):
        chads = {740543572524138587 , 909101433083813958, 829684348298199091}
        if interaction.user.id not in chads:
            await interaction.response.send_message("nuh uh", ephemeral=True)
            return
        modal = discord.ui.Modal(title="Butt")
        butt = discord.ui.TextInput(label="Butt", style=discord.TextStyle.short, custom_id="butt", placeholder="Butt")
        modal.add_item(butt)
        modal.on_submit = self.butt_submit
        await interaction.response.send_modal(modal)

    async def butt_submit(self, interaction : discord.Interaction):
        await self.ctx.send(f"{interaction.data["components"][0]["components"][0]["value"]}", ephemeral=True)
        await interaction.response.defer()

@bot.command()
async def butt(ctx):
    chads = {740543572524138587 , 909101433083813958, 829684348298199091}
    if ctx.author.id not in chads:
        await ctx.send("nuh uh")
        return
    view = Butt(ctx)
    await ctx.send(view=view)

@bot.command()
async def show(ctx):
    button = discord.ui.Button(label="candy", style = discord.ButtonStyle.secondary)
    view = discord.ui.View()
    button.callback = lambda instance : instance.response.send_message("no", ephemeral=True)
    view.add_item(button)
    await ctx.send(view = view)

@bot.command()
async def diddler(ctx):
    await ctx.send(embed = discord.Embed(title="Welcome to the diddy party"))

class Game(discord.ui.Modal):
    def __init__(self, ctx):
        super().__init__(title = "idk", timeout=None)
        self.ctx = ctx
        text = discord.ui.TextInput(label = "Type your word")
        self.add_item(text)
        self.options  = {
                'wrong' : "⬛",
                'right' : "🟩",
                'unplaced': "🟨"
                }

    async def on_submit(self, interaction : discord.Interaction):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("Not your game lil bro")
            return
        temp : discord.Message = bot.games[self.ctx.author]['message']
        to_check = bot.games[self.ctx.author]['word']
        msg = bot.games[self.ctx.author]['tries']
        attempts = bot.games[self.ctx.author]['attempts']
        word = interaction.data["components"][0]["components"][0]["value"]
        if len(word)!=5:
            await interaction.response.send_message("The word must be 5 letters long")
            return
        c = Counter(to_check)
        t = [self.options['wrong']]*5
        idx=0
        rights = 0
        unplaced = 0
        for i,j in zip(word, to_check):
            if i==j:
                t[idx]=self.options['right']
                c[i]-=1
                rights+=1
            idx+=1
        for idx,val in enumerate(word):
            if t[idx] == self.options['right']:
                continue
            if val in to_check and c[val]>0:
                t[idx]=self.options['unplaced']
                unplaced+=1
                c[val]-=1
        msg += ''.join(t)
        msg+=f' {interaction.data["components"][0]["components"][0]["value"]}\n'
        if word == to_check:
            wins = int(500 * (attempts/2+1))
            old_money = session.query(Economy).filter_by(id = self.ctx.author.id).first()
            if not old_money:
                old_money = Economy(id = self.ctx.author.id, cash=0)
                session.add(old_money)
            old_money.cash += wins
            session.commit()
            await temp.edit(embed = discord.Embed(description=f'{msg[-11:-6]}\n{msg[-6:]}\nYou win, the word was ||**{to_check}**||, in **{7-attempts} tries**\nYou won {wins} coins!', color = 0x00ff00), view = discord.ui.View())
            await interaction.response.defer()
            return
        if attempts == 0:
            wins=rights*100 + unplaced*20
            old_money = session.query(Economy).filter_by(id = self.ctx.author.id).first()
            if not old_money:
                old_money = Economy(id = self.ctx.author.id, cash=0)
                session.add(old_money)
            old_money.cash += wins
            session.commit()
            await temp.edit(embed = discord.Embed(description=f'Last attempt : {msg[-11:-6]}\n{msg[-6:]}\nGame over, the word was ||**{to_check}**||\nYou won {wins} coins!', color = 0x00ff00), view = discord.ui.View())
            await interaction.response.defer()
            return

        bot.games[self.ctx.author]['tries'] = msg
        view = discord.ui.View(timeout=None)
        button = discord.ui.Button(label = "Next Try", style=discord.ButtonStyle.green)
        button.callback = lambda interaction : interaction.response.send_modal(Game(self.ctx))
        view.add_item(button)
        embed = discord.Embed(description=msg, title="Wordle", color=0x00ff00)
        embed.set_author(name=self.ctx.author, icon_url=self.ctx.author.avatar.url if self.ctx.author.avatar else None)
        embed.set_footer(text=f"{attempts} tries remaining")
        await temp.edit(embed = embed, view = view)
        bot.games[self.ctx.author]['attempts']-=1
        await interaction.response.defer()

class Wrd(discord.ui.View):
    def __init__(self , ctx : discord.Message, butt = "Start Game"):
        super().__init__(timeout=None)
        bot.games[ctx.author] = {"word" : random.choice(bot.words).lower(), "tries" : "", "attempts" : 6}
        print(bot.games[ctx.author]['word'])
        self.ctx=ctx
        self.author = ctx.author
        button = discord.ui.Button(label = f"{butt}", style = discord.ButtonStyle.green)
        button.callback = self.startgame
        self.game = Game(ctx)
        self.add_item(button)
    async def startgame(self, interaction : discord.Interaction):
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("start a new game by doing $wordle", ephemeral=True)
        await interaction.response.send_modal(self.game)

@bot.command()
async def wordle(ctx):
    wordle = Wrd(ctx)
    embed = discord.Embed(description="Start the game", title="Wordle", color=0x00ff00)
    embed.set_author(name=ctx.author, icon_url=ctx.author.avatar.url if ctx.author.avatar else None)
    embed.set_footer(text=f"6 tries remaining")

    message = await ctx.send(embed = embed, view = wordle)
    bot.games[ctx.author]["message"] = message

@bot.command(aliases=['cash', 'bal'])
async def money(ctx, dude : discord.Member | None = None):
    if not dude:
        dude = ctx.author
    id = dude.id
    money = session.query(Economy).filter_by(id= id).first()
    if not money:
        money = Economy(id = id, cash=0)
        session.add(money)
    embed = discord.Embed(description=f"{dude.mention} has `{money.cash}` coins\nPlay wordle to earn more coins", color=0x00ff00, title="Balance")
    embed.set_author(name=dude.name, icon_url=dude.avatar.url if dude.avatar else None)
    await ctx.send(embed=embed)

@bot.command(aliases=["leaderboard"])
async def lb(ctx):
    users = session.query(User).join(Economy).order_by(-Economy.cash).all()
    lbs = []
    own = 0
    owncash = 0
    for idx,user in enumerate(users):
        if len(lbs)<10:
            lbs.append(f'{idx+1}. <@{user.id}>  -  `{user.economy.cash}`')
        if user.id == ctx.author.id:
            own = idx
            owncash = user.economy
    if own>10:
        lbs.extend(['.']*2)
        lbs.append(f'{own+1}. {ctx.author.mention}  -  `{owncash.cash}`')

    embed = discord.Embed(title = "Leaderboard", color = 0x00ff00, description='\n'.join(lbs))
    embed.set_author(name=  ctx.author.name, icon_url= ctx.author.avatar.url if ctx.author.avatar else None)
    embed.set_footer(text="Earn more coins by playing $wordle")
    await ctx.send(embed = embed)

@bot.command(aliases=['donate', 'gib'])
async def give(ctx, to : discord.Member | None = None, amount : int = 0):
    if ctx.author.id == to.id:
        await ctx.send("Cant donate to yourself")
        return
    if not to:
        await ctx.send("Enter who to donate to")
        return
    if not amount:
        await ctx.send("Enter a value greater than 0")
        return
    fr = session.query(Economy).filter_by(id= ctx.author.id).first()
    ts = session.query(Economy).filter_by(id = to.id).first()
    if not fr or not ts:
        await ctx.send("Something went wrong")
        return
    if fr.cash<amount:
        await ctx.send(f"You dont have {amount} coins brokie")
        return
    fr.cash-=amount
    ts.cash+=amount
    session.commit()
    await ctx.send(embed = discord.Embed(color = 0x00ff00, description=f"Successfully sent {amount} from {ctx.author.mention} to {to.mention}"))

@bot.command()
async def beg(ctx):
    if ctx.author.id not in bot.cooldowns or time.time() - bot.cooldowns[ctx.author.id] >90:
        val = random.choices(bot.nums, weights=bot.weights)[0]
        asyncio.create_task(ctx.send(f'You found {val} coins!'))
        old = session.query(Economy).filter_by(id = ctx.author.id).first()
        old.cash += val
        session.commit()
        bot.cooldowns[ctx.author.id] = time.time()
        return
    await ctx.send(f'Wait {90-int(time.time() - bot.cooldowns[ctx.author.id])} seconds')

class Bj(discord.ui.View):
    def __init__(self,ctx : discord.Message):
        super().__init__(timeout=None)
        self.ctx = ctx
        hit_button = discord.ui.Button(label = "Hit", style = discord.ButtonStyle.primary)
        hit_button.callback = self.hit
        stand_button = discord.ui.Button(label = "stand", style = discord.ButtonStyle.red)
        stand_button.callback = self.stand
        self.add_item(hit_button)
        self.add_item(stand_button)

    async def hit(self, interaction: discord.Interaction):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message('Not your game, lil bro.', ephemeral=True)
            return
        store = bot.black[self.ctx.author.id]
        user_cards = store['user_cards']
        dealer_cards = store['dealer_cards']
        amount = store['amount']
        new_card = random.randint(1, 13)
        user_cards.append(new_card)

        aces = user_cards.count(1)
        sm = 0
        for val in user_cards:
            if val > 1:
                sm += min(val, 10)
        while aces:
            if aces - 1 + sm + 11 > 21:
                sm += aces
                break
            else:
                aces -= 1
                sm += 11

        embed = discord.Embed(
            title="Blackjack",
            description=f"Your hand: {' '.join(map(str, user_cards))}\nDealer's cards: {' '.join(map(str, dealer_cards))}",
            color=0x00ff00
        )
        embed.set_author(name=self.ctx.author.name, icon_url=self.ctx.author.avatar.url if self.ctx.author.avatar else None)
        embed.set_footer(text=f"Bet: {amount}")
        old_money = session.query(Economy).filter_by(id = self.ctx.author.id).first()
        if sm > 21:
            embed.title = "You Bust"
            embed.description += f'\nBalance : {old_money.cash} - {amount}'
            old_money.cash -= amount
            embed.color = 0xff0000
            await store['message'].edit(embed=embed, view=discord.ui.View())
            session.commit()
        else:
            await store['message'].edit(embed=embed, view=Bj(self.ctx))


    async def stand(self, interaction: discord.Interaction):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message('Not your game, lil bro.', ephemeral=True)
            return
        store = bot.black[self.ctx.author.id]
        user_cards = store['user_cards']
        dealer_cards = store['dealer_cards']
        amount = store['amount']
        dealer_cards.pop()
        next_card = random.randint(1, 13)
        dealer_cards.append(next_card)

        sm = 0
        aces = 0
        for val in dealer_cards:
            if val == 1:
                aces += 1
            else:
                sm += min(10, val)

        while sm < 17:
            new_card = random.randint(1, 13)
            dealer_cards.append(new_card)
            if new_card == 1:
                aces += 1
            else:
                sm += min(10, new_card)
        while aces:
            if aces - 1 + sm + 11 > 21:
                sm += aces
                break
            else:
                aces -= 1
                sm += 11

        user_total = sum(min(10, card) for card in user_cards)

        embed = discord.Embed(
            title="Blackjack",
            description=f"Your hand: {' '.join(map(str, user_cards))}\nDealer's cards: {' '.join(map(str, dealer_cards))}",
            color=0x00ff00
        )
        embed.set_author(name=self.ctx.author.name, icon_url=self.ctx.author.avatar.url if self.ctx.author.avatar else None)
        embed.set_footer(text=f"Bet: {amount}")
        old_bal = session.query(Economy).filter_by(id = self.ctx.author.id).first()
        if sm > 21:
            embed.title = "Dealer Busts! You Win!"
            embed.description += f'\nBalance : {old_bal.cash} + {amount}'
            embed.color = 0x00ff00
            old_bal.cash+=amount
        elif sm > user_total:
            embed.title = "Dealer Wins!"
            embed.description += f'\nBalance : {old_bal.cash} - {amount}'
            embed.color = 0xff0000
            old_bal.cash-=amount
        elif sm == user_total:
            embed.title = "It's a Draw!"
            embed.description += f'\nBalance : {old_bal.cash} + 0'
            embed.color = 0xffff00
        else:
            embed.title = "You Win!"
            embed.color = 0x00ff00
            embed.description += f'\nBalance : {old_bal.cash} + {amount}'
            old_bal.cash += amount
        session.commit()
        await store['message'].edit(embed=embed, view=discord.ui.View())

@bot.command(aliases=['blackjack'])
async def bj(ctx : discord.Message, amount : int = 100):
    if session.query(Economy).filter_by(id = ctx.author.id).first().cash < amount:
        await ctx.send(f"You dont have {amount} money boy")
        return
    view = Bj(ctx)
    user_cards = [random.randint(1,13) , random.randint(1,13)]
    dealer_cards = [random.randint(1,13), "?"]
    embed = discord.Embed(title='Blackjack',
    description=f"Your hand : {' '.join([str(i) for i in user_cards])}\nDealer's cards : {' '.join([str(i) for i in dealer_cards])}",
    color=0x00ff00
    )
    embed.set_author(name = ctx.author.name, icon_url = ctx.author.avatar.url if ctx.author.avatar else None)
    embed.set_footer(text = f"Bet : {amount}")
    msg = await ctx.send(embed= embed, view = view)
    temp = {
        'message' : msg,
        'amount' : amount,
        'user_cards' : user_cards,
        'dealer_cards' : dealer_cards
    }
    bot.black[ctx.author.id] = temp

bot.run(token=os.getenv("TOKEN"))
