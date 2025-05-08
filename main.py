import asyncio
from pyDes import *
import base64
import datetime
import os
import random
import re
import time
from collections import deque, Counter
import math
import aiohttp
import discord
import discord.ext.commands
import json
from aiohttp import ClientError
from discord.ext import commands
from discord.utils import get
from urllib.request import Request, urlopen
import os
from dotenv import load_dotenv

from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey, CheckConstraint, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker , relationship, Query

import discord.ext

Base = declarative_base()


class Level(Base):
    __tablename__ = "level"
    id = Column(Integer, ForeignKey("user.id"), primary_key = True)
    level = Column(Integer)
    current = Column(Integer)
    user = relationship("User", back_populates="level")

class Job(Base):
    __tablename__ = "job"
    id = Column(Integer, ForeignKey("user.id"), primary_key=True)
    name = Column(String)
    salary = Column(Integer)
    user = relationship("User", back_populates="job")

class Economy(Base):
    __tablename__ = "economy"
    id = Column(Integer, ForeignKey("user.id"), primary_key=True, default=0)
    _cash = Column(Integer)
    user = relationship("User", back_populates="economy")

    __table_args__ = (
        CheckConstraint("_cash>=0", name="cash_not_neg"),
    )

    @property
    def cash(self):
        return max(self._cash, 0)

    @cash.setter
    def cash(self, value):
        self._cash = max(value, 0)

class Bestrace(Base):
    __tablename__ = "bestrace"
    id = Column(Integer, ForeignKey("user.id"), primary_key=True)
    time = Column(Float, default= 10)
    user = relationship("User", back_populates="bestrace", uselist=False)

class User(Base):
    __tablename__ = "user"
    id = Column(Integer, primary_key=True)
    name = Column(String)
    avatar = Column(String)
    roles = relationship("UserRole", back_populates="user" , cascade="all, delete-orphan")
    economy = relationship("Economy", back_populates="user", uselist=False, cascade="all, delete-orphan")
    bank = relationship("Bank", back_populates="user", uselist=False, cascade="all, delete-orphan")
    level = relationship("Level", back_populates="user", uselist=False, cascade="all, delete-orphan")
    job = relationship("Job", back_populates="user", uselist=False, cascade="all, delete-orphan")
    bestrace = relationship("Bestrace", back_populates="user", uselist=False,cascade="all, delete-orphan" )

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

class Bank(Base):
    __tablename__ = "bank"
    id = Column(Integer, ForeignKey("user.id"), primary_key=True)
    user = relationship("User", back_populates="bank")
    _cash = Column(Integer)

    @property
    def cash(self):
        return max(self._cash, 0)

    @cash.setter
    def cash(self, value):
        self._cash = max(value, 0)

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
        self.beg_cooldowns = {}
        self.race_cooldowns = {}
        self.black = {}
        self.race = {}
        self.playing = {}
        self.lastmsg : discord.Message | None = None
        self.song_msg : discord.Message | None = None
        self.links = []
        self.vc = None
        self.jobs = {
            "housewife" : {"salary" : 15000, "min" : 10},
            "factory-worker" : {"salary" : 5000, "min" : 5},
            "streamer" : {"salary" : 1000, "min" : 3},
            "clown" : {"salary" : 500, "min" : 1}
        }


    def deleted(self, message : discord.Message) -> None:
        embed = discord.Embed(description=f"**Message**: {message.content}", color=0xC3B1E1)
        embed.set_author(name=f"{message.author}", icon_url=message.author.avatar.url if message.author.avatar else None)
        embed.set_footer(text=f"Deleted in #{message.channel}")
        self.logs.append(embed)

    def edited_message(self, before : discord.Message, after: discord.Message) -> None:
        embed = discord.Embed(description=f"**Before**: {before.content}\n **After**: {after.content}", color=0xC3B1E1)
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

def is_guild_owner():
    def predicate(ctx):
        return ctx.guild is not None and ctx.guild.owner_id == ctx.author.id
    return commands.check(predicate)


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
        await asyncio.sleep(6000)

async def load_words():
    with open('words.txt' , 'r') as file:
        bot.words = file.read().split(' ')[:-1]
        print(f"{len(bot.words)} words loaded")

search_url = "https://www.jiosaavn.com/api.php?__call=autocomplete.get&_format=json&_marker=0&cc=in&includeMetaTags=1&query="
song_url = "https://www.jiosaavn.com/api.php?__call=song.getDetails&cc=in&_marker=0%3F_marker%3D0&_format=json&pids="


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
    embed = discord.Embed(title="Select a color", color=0xC3B1E1)
    embed.add_field(name="", value=f"{', '.join([role.mention for role in bot.color_roles.values()])}")
    embed.set_author(name=f"{bot.user.name}", icon_url=bot.user.avatar.url)
    rc = get(bot.guilds[0].channels, id = 1294954582941896746)
    old_message = await rc.fetch_message(1294981556036833341)
    if old_message:
        await old_message.edit(embed=embed, view=view)
    else:

        await rc.send(embed=embed, view=view)

class Raward(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)
        button = discord.ui.Button(label = "Click me", style=discord.ButtonStyle.green)
        button.callback = self.press
        self.add_item(button)

    async def on_timeout(self):
        await bot.lastmsg.delete()

    async def press(self, interaction : discord.Interaction):
        self.timeout = None
        old_cash = session.query(Economy).filter_by(id = interaction.user.id).first()
        rand = random.randint(10,1000)
        embed = discord.Embed(title = "Reward added", color = 0xC3B1E1, description=f"Clamined by {interaction.user.mention}")
        embed.add_field(name = "Balance", value = f"{old_cash.cash} + {rand}")
        old_cash.cash += rand
        session.commit()
        await interaction.message.edit(embed=embed, view = discord.ui.View(timeout=None))

async def send_random():
    while True:
        embed = discord.Embed(title = "Click me for a reward", color = 0xC3B1E1)
        bot.lastmsg = await bot.get_channel(1287525272748560499).send(embed = embed, view = Raward())
        to_sleep = random.randint(30, 60)
        await asyncio.sleep(to_sleep*60)

async def apply_interest(guild):
    while True:
        await asyncio.sleep(60*60)
        rate = random.gauss(0.08, 0.01)
        rate = max(0.01, min(0.3, rate))
        chann = get(guild.channels, id = 1297858484506988565)
        asyncio.create_task(chann.edit(name = f"Interest rate: {rate*100:.2f}%"))
        for user in guild.members:
            old_user = session.query(User).filter_by(id = user.id).first()
            old_user.bank.cash += min(3_000 * old_user.level.level ,old_user.bank.cash * rate)
            old_user.bank.cash = math.ceil(old_user.bank.cash)
            old_user.economy.cash += old_user.job.salary
        session.commit()
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
                old_cash = existing_user.economy
                old_bank = existing_user.bank
                old_level = existing_user.level
                old_job = existing_user.job
                old_best = existing_user.bestrace
                if not old_bank:
                    add_bank = Bank(id = existing_user.id, cash = 0)
                    session.add(add_bank)
                if not old_cash:
                    add_cash = Economy(id = existing_user.id, cash = 0)
                    session.add(add_cash)
                if not old_level:
                    add_level = Level(id = existing_user.id, level = 1, current = 20)
                    session.add(add_level)
                if not old_job:
                    add_job = Job(id = existing_user.id, name = "clown", salary = bot.jobs["clown"]["salary"])
                    session.add(add_job)
                if not old_best:
                    add_best = Bestrace(id = existing_user.id, time = 10.0)
                    session.add(add_best)
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
    bot.loop.create_task(send_random())
    await bot.tree.sync()
    print("Slash commands synced")
    for guild in bot.guilds:
        bot.loop.create_task(periodic_member_count_update(guild))
        bot.loop.create_task(apply_interest(guild))
@bot.event
async def on_message(message):
    async def check_level_up():
        if message.author.id == bot.user.id:
            return
        user : User = session.query(User).filter_by(id = message.author.id).first()
        if not user.level:
            print(user.name)
        user.level.current -= 1
        if user.level.current <= 0:
            user.level.level+=1
            inc = (user.level.level)**2 * 500
            user.level.current = int(user.level.level**1.5) * 20
            embed = discord.Embed(title = "Level up", description=f"{message.author.mention}, you have leveled up to {user.level.level}",color=0xC3B1E1)
            embed.add_field(name="Balance", value=f"{user.economy.cash} + {inc}")
            user.economy.cash += inc
            await get(bot.guilds[0].channels, id = 1297979432149057626).send(embed = embed)
        session.commit()
    async def sendmsg():
        if message.channel.id==1293821426616369232 and not message.content.isdigit():
            await message.delete()
    asyncio.gather(sendmsg(),check_level_up())
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
            bank = Bank(id=existing.id, cash=0)
            level = Level(id = existing.id, level = 1, current = 20)
            best = Bestrace(id = existing.id, time = 10.0)
            session.add(existing)
            session.add(bank)
            session.add(money)
            session.add(level)
            session.add(best)
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

@bot.command(aliases=[])
async def snipe(ctx, nums = 1):
    if nums>len(bot.logs):
        await ctx.send(embed = discord.Embed(description="Not enough messages to snipe", color = 0xC3B1E1))
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
    embed = discord.Embed(description=f"{from_spank.mention} oiled up and spanked {to_spank.mention}", color=0xC3B1E1)
    embed.set_image(url="https://media1.tenor.com/m/V8vUcWo4dLIAAAAC/spank-peach.gif")
    embed.set_author(name=f"{from_spank}", icon_url=from_spank.avatar.url if from_spank.avatar else None)
    await ctx.send(embed=embed)

@bot.command()
async def kiss(ctx , to_kiss = None):
    from_kiss = ctx.author
    if not to_kiss:
        to_kiss = await bot.fetch_user(1247271643009777704)
    embed = discord.Embed(color=0xC3B1E1, description = f"{from_kiss.mention} ***smooches*** {to_kiss}")
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
    embed = discord.Embed(description=f"{member.mention} has been muted by {ctx.author.mention}", color=0xC3B1E1)
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
    embed = discord.Embed(description=f"{member.mention} has been unmuted by {ctx.author.mention}", color=0xC3B1E1)
    await ctx.send(embed=embed)

@bot.command()
@commands.has_permissions(administrator=True)
async def kick(ctx, to_kick : discord.Member):
    if sum(1 for i in to_kick.roles if i.name == ":/") == 1:
        await ctx.send("no")
        return
    async def send_msg():
        embed = discord.Embed(description=f"{to_kick.mention} has been kicked by {ctx.author.mention}", color=0xC3B1E1)
        await ctx.send(embed=embed)
    asyncio.gather( to_kick.kick() , send_msg())

@bot.command()
@commands.has_permissions(administrator=True)
async def ban(ctx, to_ban : discord.Member, reason : str | None = None):
    if sum(1 for i in to_ban.roles if i.name == ":/") == 1:
        await ctx.send("no")
        return
    async def send_msg():
        embed = discord.Embed(description=f"{to_ban.mention} has been banned by {ctx.author.mention}", color=0xC3B1E1)
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
        embed = discord.Embed(description=f"{member.mention} has been unbanned by {ctx.author.mention}", color=0xC3B1E1)
        await ctx.send(embed=embed)
    asyncio.gather(ctx.guild.unban(member) , send_msg())


@bot.command()
async def invite(ctx):
    await ctx.send(f"Invite link: {discord.utils.oauth_url(bot.user.id)}")

@bot.command()
async def poll(ctx, *, question):
    embed = discord.Embed(title="Poll", description=question, color=0xC3B1E1)
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
    embed = discord.Embed(description=f"**I** chose **{random.choice(temp)}**", color=0xC3B1E1)
    embed.set_author(name=f"{ctx.author}", icon_url=ctx.author.avatar.url if ctx.author.avatar else None)
    await ctx.send(embed=embed)

@bot.command()
async def pp(ctx, user : discord.Member = None):
    if not user:
        user = ctx.author
    if "woman" in {role.name.lower() for role in ctx.guild.get_member(user.id).roles}:
        embed = discord.Embed(description=f"{user.mention} has no pp", color=0xC3B1E1)
        embed.set_author(name=f"{user}", icon_url=user.avatar.url if user.avatar else None)
        await ctx.send(embed=embed)
        return
    ppsize = f"8{"="*random.randint(2,8)}D" if user.id != 909101433083813958 else f"8{'='*random.randint(8,14)}D"
    embed = discord.Embed(description=f"{user.mention} has a {ppsize} pp", color=0xC3B1E1)
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
    embed = discord.Embed(description=f"{user.mention} is {gayrate}% gay", color=0xC3B1E1)
    embed.set_author(name=f"{user}", icon_url=user.avatar.url if user.avatar else None)
    await ctx.send(embed=embed)

@bot.command()
async def touch(ctx, user : discord.Member | None = None):
    if not user:
        user = ctx.author
    embed = discord.Embed(description=f"{ctx.author.mention} touched {user.mention}", color=0xC3B1E1)
    embed.set_image(url="https://media.discordapp.net/attachments/1125755890704863312/1223572603046985789/makesweet-x0u4zi.gif?ex=66f530c9&is=66f3df49&hm=9c877be4ca80702f0be44890c4fbf88824d1a8ec964de276f6889e5aadf13e2e&")
    embed.set_author(name=f"{ctx.author}", icon_url=ctx.author.avatar.url if ctx.author.avatar else None)
    await ctx.send(embed=embed)

@bot.command(aliases=["kms","suicide","killme","endme","die","murder","uicide"])
async def kickme(ctx):
    start = time.time()
    inv = os.environ.get("INVITE")
    await ctx.author.send(f"yoo why you leave the party?? come back!\n{inv}")
    async def he_left():
        embed = discord.Embed(description=f"{ctx.author.mention} killed themselves", color=0xC3B1E1)
        embed.set_author(name=f"{ctx.author}", icon_url=ctx.author.avatar.url if ctx.author.avatar else None)
        await ctx.send(embed=embed)
    asyncio.gather(ctx.author.kick(reason="He asked for it."),he_left())
    print(time.time() - start)

@bot.command()
async def roulette(ctx, user : discord.Member | None = None):
    if not user:
        user = ctx.author
    embed = discord.Embed(color=0xC3B1E1)
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
                embed = discord.Embed(title=result['title'], url=result['movie_url'], color=0xC3B1E1)
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



@bot.command()
async def boobs(ctx, user : discord.Member = None):
    if not user:
        user = ctx.author
    embed = discord.Embed(description=f"{user.mention}'s chesticles",color=0xC3B1E1)
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
    embed = discord.Embed(color=0xC3B1E1, description = f"{member.mention}'s avatar was searched by {ctx.author.mention}")
    embed.set_image(url = member.avatar.url)
    embed.set_author(name=member,icon_url = member.avatar.url)
    await ctx.send(embed = embed)

class Timer:
    def __init__(self, ctx, time):
        self.ctx = ctx
        self.time = time
    async def start_timer(self):
        await self.ctx.send(embed = discord.Embed(description = f"Timer started for {self.time} seconds by {self.ctx.author.mention}", color = 0xC3B1E1))
        self.task = asyncio.create_task(self.countdown())
    async def countdown(self):
        await asyncio.sleep(self.time)
        await self.ctx.send(f"{self.ctx.author.mention}", embed = discord.Embed(description = f"Timer ended by {self.ctx.author.mention}", color = 0xC3B1E1))

@bot.command()
async def timer(ctx, time):
    if not time.isdigit():
        await ctx.send("That aint a number")
        return
    timer = Timer(ctx, int(time))
    await timer.start_timer()

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
        super().__init__(title = "idk", timeout=120)
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
        word = interaction.data["components"][0]["components"][0]["value"]
        if len(word)!=5:
            await interaction.response.send_message("The word must be 5 letters long")
            return
        temp : discord.Message = bot.games[self.ctx.author]['message']
        to_check = bot.games[self.ctx.author]['word']
        msg = bot.games[self.ctx.author]['tries']
        attempts = bot.games[self.ctx.author]['attempts']
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
            await temp.edit(embed = discord.Embed(description=f'{msg[-11:-6]}\n{msg[-6:]}\nYou win, the word was ||**{to_check}**||, in **{7-attempts} tries**\nYou won {wins} coins!', color = 0xC3B1E1), view = discord.ui.View())
            await interaction.response.defer()
            if self.ctx.author.id not in bot.playing or bot.playing[self.ctx.author.id] != self.ctx.message.id:
                return
            del bot.playing[self.ctx.author.id]
            return
        if attempts == 0:
            wins=rights*100 + unplaced*20
            old_money = session.query(Economy).filter_by(id = self.ctx.author.id).first()
            if not old_money:
                old_money = Economy(id = self.ctx.author.id, cash=0)
                session.add(old_money)
            old_money.cash += wins
            session.commit()
            await temp.edit(embed = discord.Embed(description=f'Last attempt : {msg[-11:-6]}\n{msg[-6:]}\nGame over, the word was ||**{to_check}**||\nYou won {wins} coins!', color = 0xC3B1E1), view = discord.ui.View())
            await interaction.response.defer()
            if self.ctx.author.id not in bot.playing or bot.playing[self.ctx.author.id] != self.ctx.message.id:
                return
            del bot.playing[self.ctx.author.id]
            return

        bot.games[self.ctx.author]['tries'] = msg
        view = discord.ui.View(timeout=None)
        button = discord.ui.Button(label = "Next Try", style=discord.ButtonStyle.green)
        button.callback = lambda interaction : interaction.response.send_modal(Game(self.ctx))
        view.add_item(button)
        embed = discord.Embed(description=msg, title="Wordle", color=0xC3B1E1)
        embed.set_author(name=self.ctx.author, icon_url=self.ctx.author.avatar.url if self.ctx.author.avatar else None)
        embed.set_footer(text=f"{attempts} tries remaining")
        await temp.edit(embed = embed, view = view)
        bot.games[self.ctx.author]['attempts']-=1
        await interaction.response.defer()

class Wrd(discord.ui.View):
    def __init__(self , ctx : discord.Message, butt = "Start Game"):
        super().__init__(timeout=180)
        bot.games[ctx.author] = {"word" : random.choice(bot.words), "tries" : "", "attempts" : 6}
        print(bot.games[ctx.author]['word'])
        self.ctx : discord.ext.command.Context =ctx
        self.author = ctx.author
        button = discord.ui.Button(label = f"{butt}", style = discord.ButtonStyle.green)
        button.callback = self.startgame
        self.game = Game(ctx)
        self.add_item(button)

    async def on_timeout(self):
        if self.ctx.author.id not in bot.playing or bot.playing[self.ctx.author.id] != self.ctx.message.id:
            return
        embed = embed = discord.Embed(description="Timed out", color=0xff0000)
        embed.set_author(name=self.ctx.author, icon_url=self.ctx.author.avatar.url if self.ctx.author.avatar else None)
        embed.set_footer(text="Game timed out")
        await bot.games[self.ctx.author]['message'].edit(embed = embed, view = discord.ui.View())
        del bot.playing[self.ctx.author.id]

    async def startgame(self, interaction : discord.Interaction):
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("start a new game by doing $wordle", ephemeral=True)
            return
        await interaction.response.send_modal(self.game)

@bot.command()
async def wordle(ctx : discord.ext.commands.Context):
    if ctx.author.id in bot.playing:
        await ctx.send(f"You are already in a game {ctx.author.mention}, either finish that, or wait 2 minutes")
        return
    wordle = Wrd(ctx)
    embed = discord.Embed(description="Start the game", title="Wordle", color=0xC3B1E1)
    embed.set_author(name=ctx.author, icon_url=ctx.author.avatar.url if ctx.author.avatar else None)
    embed.set_footer(text=f"6 tries remaining")
    bot.playing[ctx.author.id] = ctx.message.id
    message = await ctx.send(embed = embed, view = wordle)
    bot.games[ctx.author]["message"] = message

@bot.command(aliases=['cash', 'bal'])
async def money(ctx, dude : discord.Member | None = None):
    if not dude:
        dude = ctx.author
    id = dude.id
    user = session.query(User).filter_by(id = id).first()
    money = user.economy
    bank = user.bank
    if not money:
        money = Economy(id = id, cash=0)
        session.add(money)
    embed = discord.Embed(color=0xC3B1E1, title="Balance")
    embed.add_field(name="Cash", value=f"{money.cash}")
    embed.add_field(name="Bank", value=f"{bank.cash}")
    embed.set_author(name=dude.name, icon_url=dude.avatar.url if dude.avatar else None)
    await ctx.send(embed=embed)

@bot.command(aliases=["leaderboard", "top", "baltop"])
async def lb(ctx):
    users = session.query(User).join(Economy).join(Bank).order_by(-Economy._cash - Bank._cash).all()
    lbs = []
    own = 0
    owncash = 0
    for idx,user in enumerate(users):
        if len(lbs)<10:
            lbs.append(f'{idx+1}. <@{user.id}>  -  `{user.economy.cash} + {user.bank.cash} = {user.economy.cash + user.bank.cash}`')
        if user.id == ctx.author.id:
            own = idx
            owncash = user.economy
    if own>=10:
        lbs.extend(['.']*2)
        lbs.append(f'{own+1}. {ctx.author.mention}  -  `{owncash.cash}`')

    embed = discord.Embed(title = "Leaderboard", color = 0xC3B1E1, description='\n'.join(lbs))
    embed.set_author(name=  ctx.author.name, icon_url= ctx.author.avatar.url if ctx.author.avatar else None)
    embed.set_footer(text="Earn more coins by playing $wordle")
    await ctx.send(embed = embed)

@bot.command(aliases=['donate', 'gib', 'transfer'])
async def give(ctx, to : discord.Member | None = None, amount : int = 0):
    if ctx.author.id in bot.playing:
        await ctx.send(f"Cant transfer money while in game {ctx.author.mention}, either finish that, or wait 2 minutes")
        return
    amount = max(amount, 0)
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
    await ctx.send(embed = discord.Embed(color = 0xC3B1E1, description=f"Successfully sent {amount} from {ctx.author.mention} to {to.mention}"))

@bot.command()
async def beg(ctx):
    if ctx.author.id not in bot.beg_cooldowns or time.time() - bot.beg_cooldowns[ctx.author.id] >90:
        val = random.choices(bot.nums, weights=bot.weights)[0]
        asyncio.create_task(ctx.send(f'You found {val} coins!'))
        old = session.query(Economy).filter_by(id = ctx.author.id).first()
        old.cash += val
        session.commit()
        bot.beg_cooldowns[ctx.author.id] = time.time()
        return
    await ctx.send(f'Wait {90-int(time.time() - bot.beg_cooldowns[ctx.author.id])} seconds')

class Bj(discord.ui.View):
    suits = ['♠', '♥', '♦', '♣']

    def __init__(self, ctx: discord.Message):
        super().__init__(timeout=120)
        self.ctx = ctx
        hit_button = discord.ui.Button(label="Hit", style=discord.ButtonStyle.primary)
        hit_button.callback = self.hit
        stand_button = discord.ui.Button(label="Stand", style=discord.ButtonStyle.red)
        stand_button.callback = self.stand
        self.add_item(hit_button)
        self.add_item(stand_button)

    async def on_timeout(self):
        if self.ctx.author.id not in bot.playing or bot.playing[self.ctx.author.id] != self.ctx.message.id:
            return
        del bot.playing[self.ctx.author.id]
        store = bot.black[self.ctx.author.id]
        amount = store['amount']
        old_money = session.query(Economy).filter_by(id = self.ctx.author.id).first()
        embed = discord.Embed(
            title="Blackjack",
            description=f"Time Out",
        )
        embed.set_author(name=self.ctx.author.name, icon_url=self.ctx.author.avatar.url if self.ctx.author.avatar else None)
        embed.set_footer(text=f"Bet: {amount}")
        embed.description += f'\nBalance: {old_money.cash} - {amount}'
        old_money.cash -= amount
        embed.color = 0xff0000
        await store['message'].edit(embed=embed, view=discord.ui.View())
        session.commit()

    def card_name(self, card_value, suit):
        if card_value == 1:
            name = 'Ace'
        elif card_value == 11:
            name = 'Jack'
        elif card_value == 12:
            name = 'Queen'
        elif card_value == 13:
            name = 'King'
        else:
            name = str(card_value)
        return f'{name} {suit} |'

    async def hit(self, interaction: discord.Interaction):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message('Not your game, lil bro.', ephemeral=True)
            return

        store = bot.black[self.ctx.author.id]
        amount = store['amount']

        user_cards = store['user_cards']
        dealer_cards = store['dealer_cards']

        new_card_value = random.randint(1, 13)
        new_card_suit = random.choice(self.suits)
        user_cards.append((new_card_value, new_card_suit))

        aces = sum(1 for val, suit in user_cards if val == 1)
        sm = 0
        for val, suit in user_cards:
            if val > 1:
                sm += min(val, 10)
        while aces:
            if aces - 1 + sm + 11 > 21:
                sm += aces
                break
            else:
                aces -= 1
                sm += 11
        user_hand = ' '.join(self.card_name(val, suit) for val, suit in user_cards)
        dealer_hand = ' '.join(self.card_name(val, suit) if val != "?" else "?" for val, suit in dealer_cards)

        embed = discord.Embed(
            title="Blackjack",
            description=f"Your hand: {user_hand}\nDealer's cards: {dealer_hand}",
            color=0xC3B1E1
        )
        embed.set_author(name=self.ctx.author.name, icon_url=self.ctx.author.avatar.url if self.ctx.author.avatar else None)
        embed.set_footer(text=f"Bet: {amount}")

        old_money = session.query(Economy).filter_by(id=self.ctx.author.id).first()
        if sm > 21:
            embed.title = "You Bust"
            embed.description += f'\nBalance: {old_money.cash} - {amount}'
            old_money.cash -= amount
            embed.color = 0xff0000
            await store['message'].edit(embed=embed, view=discord.ui.View())
            session.commit()
            if self.ctx.author.id not in bot.playing or bot.playing[self.ctx.author.id] != self.ctx.message.id:
                return
            del bot.playing[self.ctx.author.id]
        else:
            await store['message'].edit(embed=embed, view=Bj(self.ctx))
        await interaction.response.defer()

    async def stand(self, interaction: discord.Interaction):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message('Not your game, lil bro.', ephemeral=True)
            return

        store = bot.black[self.ctx.author.id]
        user_cards = store['user_cards']
        dealer_cards = store['dealer_cards']
        amount = store['amount']

        dealer_cards.pop()
        next_card_value = random.randint(1, 13)
        next_card_suit = random.choice(self.suits)
        dealer_cards.append((next_card_value, next_card_suit))

        sm = 0
        aces = 0
        for val, suit in dealer_cards:
            if val == 1:
                aces += 1
            else:
                sm += min(10, val)

        while sm < 17:
            new_card_value = random.randint(1, 13)
            new_card_suit = random.choice(self.suits)
            dealer_cards.append((new_card_value, new_card_suit))
            if new_card_value == 1:
                aces += 1
            else:
                sm += min(10, new_card_value)

        while aces:
            if aces - 1 + sm + 11 > 21:
                sm += aces
                break
            else:
                aces -= 1
                sm += 11

        user_total = 0
        aces = 0
        for card_value, _ in user_cards:
            if card_value == 1:
                aces += 1
            else:
                user_total += min(10, card_value)

        while aces:
            if aces - 1 + user_total + 11 > 21:
                user_total += aces
                break
            else:
                aces -= 1
                user_total += 11
        user_hand = ' '.join(self.card_name(val, suit) for val, suit in user_cards)
        dealer_hand = ' '.join(self.card_name(val, suit) for val, suit in dealer_cards)

        embed = discord.Embed(
            title="Blackjack",
            description=f"Your hand: {user_hand}\nDealer's cards: {dealer_hand}",
            color=0xC3B1E1
        )
        embed.set_author(name=self.ctx.author.name, icon_url=self.ctx.author.avatar.url if self.ctx.author.avatar else None)
        embed.set_footer(text=f"Bet: {amount}")

        old_bal = session.query(Economy).filter_by(id=self.ctx.author.id).first()

        if sm > 21:
            embed.title = "Dealer Busts! You Win!"
            embed.description += f'\nBalance: {old_bal.cash} + {amount}'
            embed.color = 0xC3B1E1
            old_bal.cash += amount
        elif sm > user_total:
            embed.title = "Dealer Wins!"
            embed.description += f'\nBalance: {old_bal.cash} - {amount}'
            embed.color = 0xff0000
            old_bal.cash -= amount
        elif sm == user_total:
            embed.title = "It's a Draw!"
            embed.description += f'\nBalance: {old_bal.cash} + 0'
            embed.color = 0xffff00
        else:
            embed.title = "You Win!"
            embed.description += f'\nBalance: {old_bal.cash} + {amount}'
            embed.color = 0xC3B1E1
            old_bal.cash += amount

        session.commit()
        asyncio.create_task(store['message'].edit(embed=embed, view=discord.ui.View()))
        await interaction.response.defer()
        if self.ctx.author.id not in bot.playing or bot.playing[self.ctx.author.id] != self.ctx.message.id:
            return
        del bot.playing[self.ctx.author.id]

@bot.command(aliases=['blackjack'])
async def bj(ctx: discord.ext.commands.Context, amount: int | str= 100):
    if ctx.author.id in bot.playing:
        await ctx.send(f"You are already in a game {ctx.author.mention}, either finish that, or wait 2 minutes")
        return
    if amount == "all":
        amount = session.query(Economy).filter_by(id = ctx.author.id).first().cash
    if not isinstance(amount,int) and not amount.isdigit():
        await ctx.send("Enter a number or all")
    amount = max(-amount, amount)
    if amount<100:
        await ctx.send("The minimum bet is 100")
        return
    if session.query(Economy).filter_by(id=ctx.author.id).first().cash < amount:
        await ctx.send(f"You don't have {amount} money boy")
        return
    bot.playing[ctx.author.id]= ctx.message.id
    view = Bj(ctx)
    user_cards = [(random.randint(1, 13), random.choice(Bj.suits)), (random.randint(1, 13), random.choice(Bj.suits))]
    dealer_cards = [(random.randint(1, 13), random.choice(Bj.suits)), ("?", "?")]

    user_hand = ' '.join(view.card_name(val, suit) for val, suit in user_cards)
    dealer_hand = ' '.join(view.card_name(val, suit) if val != "?" else "?" for val, suit in dealer_cards)

    embed = discord.Embed(
        title='Blackjack',
        description=f"Your hand: {user_hand}\nDealer's cards: {dealer_hand}",
        color=0xC3B1E1
    )
    embed.set_author(name=ctx.author.name, icon_url=ctx.author.avatar.url if ctx.author.avatar else None)
    embed.set_footer(text=f"Bet: {amount}")

    msg = await ctx.send(embed=embed, view=view)

    bot.black[ctx.author.id] = {
        'message': msg,
        'amount': amount,
        'user_cards': user_cards,
        'dealer_cards': dealer_cards
    }

class Challenge(discord.ui.Modal):
    def __init__(self,ctx):
        super().__init__( title="Race", timeout=10)
        self.ctx=ctx
        self.store = bot.race[ctx.author.id]
        self.text = discord.ui.TextInput(label=self.store['para'])
        self.add_item(self.text)
    async def on_timeout(self):
        if self.ctx.author.id not in bot.playing or bot.playing[self.ctx.author.id] != self.ctx.message.id:
            return
        del bot.playing[self.ctx.author.id]
        msg = self.store['message']
        old_bal = session.query(Economy).filter_by(id = self.ctx.author.id).first()
        embed = discord.Embed(title = "Typing race", color = 0xff0000)
        embed.set_author(name = self.ctx.author.name, icon_url=self.ctx.author.avatar.url if self.ctx.author.avatar else None)
        embed.description = f" You couldnt type {self.store['para']} in time\n"
        embed.add_field(name="New Balance", value=f"{old_bal.cash} - 100")
        old_bal.cash -=100
        session.commit()
        await msg.edit(embed = embed, view = discord.ui.View())

    async def on_submit(self, interaction : discord.Interaction):
        if interaction.user.id!=self.ctx.author.id:
            await interaction.response.send_message("Not your race", ephemeral=True)
            return
        word = self.text.value
        tm = time.time() - self.store['start']
        embed = discord.Embed(title = "Typing race", color = 0xC3B1E1)
        embed.set_author(name = self.ctx.author.name, icon_url=self.ctx.author.avatar.url if self.ctx.author.avatar else None)
        user = session.query(User).filter_by(id = self.ctx.author.id).first()
        if word == self.store['para']:
            user.bestrace.time = min(user.bestrace.time, tm)
            new = 100*math.ceil(10 - tm)
            embed.description = f"{word}\nTyped in {tm} seconds"
            embed.add_field(name="New Balance", value=f"{user.economy.cash} + {new}")
            user.economy.cash += new
            await self.store['message'].edit(embed = embed, view = discord.ui.View())
        else:
            embed.color = 0xff0000
            embed.description = f"You typed - {word}\nActual words - {self.store['para']}\n Typed in {time.time() - self.store['start']} seconds"
            embed.add_field(name="New Balance", value=f"{user.economy.cash} - 100")
            user.economy.cash -=100
            await self.store['message'].edit(embed = embed, view = discord.ui.View())
        if self.ctx.author.id not in bot.playing or bot.playing[self.ctx.author.id] != self.ctx.message.id:
            return
        del bot.playing[self.ctx.author.id]
        session.commit()
        await interaction.response.defer()
        bot.race_cooldowns[self.ctx.author.id] = time.time()

class Race(discord.ui.View):
    def __init__(self, ctx):
        super().__init__(timeout = 120)
        self.ctx = ctx
        button = discord.ui.Button(label = 'Start Challenge', style=discord.ButtonStyle.red)
        button.callback = self.start_race
        self.add_item(button)

    async def on_timeout(self):
        if self.ctx.author.id not in bot.playing or bot.playing[self.ctx.author.id] != self.ctx.message.id:
            return
        del bot.playing[self.ctx.author.id]
    async def start_race(self, interaction : discord.Interaction):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("Not your race lil bro", ephemeral=True)
            return
        bot.race[self.ctx.author.id]['start'] = time.time()
        await interaction.response.send_modal(Challenge(self.ctx))

@bot.command()
async def race(ctx):
    diff = 31
    if ctx.author.id in bot.race_cooldowns:
        diff = time.time() - bot.race_cooldowns[ctx.author.id]
    if diff<30:
        await ctx.send(f"Too soon. Wait {30 - int(diff)} seconds")
        return
    if ctx.author.id in bot.playing:
        await ctx.send(f"You are already in a game {ctx.author.mention}, either finish that, or wait 2 minutes")
        return
    if session.query(Economy).filter_by(id = ctx.author.id).first().cash <100:
        await ctx.send("You need at least 100 coins to race")
        return
    embed = discord.Embed(title = "Typing race", color = 0xC3B1E1, description="Clcik the button to start")
    embed.set_author(name = ctx.author.name, icon_url=ctx.author.avatar.url if ctx.author.avatar else None)
    view = Race(ctx)
    bot.race[ctx.author.id] = {
        'para' : ' '.join(random.choices(bot.words, k=5))
    }
    bot.race[ctx.author.id]['message'] = await ctx.send(embed = embed, view = view)
    bot.playing[ctx.author.id] = ctx.message.id
    bot.race_cooldowns[ctx.author.id] = time.time()

@bot.command()
@commands.check_any(commands.is_owner(), is_guild_owner())
async def add(ctx, user: discord.User, amount: int):
    if not user:
        user = ctx.author
    if amount<0:
        await ctx.send("You cant add negative money")
        return
    session.query(Economy).filter_by(id = user.id).first().cash += amount
    session.commit()

@bot.command()
@commands.check_any(commands.is_owner(), is_guild_owner())
async def remove(ctx, user: discord.User, amount: int):
    if not user:
        user = ctx.author
    if amount<0:
        await ctx.send("You cant remove negative money")
        return
    session.query(Economy).filter_by(id = user.id).first().cash -= amount
    session.commit()

@bot.command(aliases = ['tall'])
async def height(ctx, user : discord.Member = None):
    if not user:
        user = ctx.author
    lower = 1
    upper = 8 if "woman" not in {role.name.lower() for role in ctx.guild.get_member(user.id).roles} else 3
    msg = f"```     O     \n    \\|/   \n" + random.randint(lower,upper)*"     |\n" + "    / \\```"
    embed = discord.Embed(description=msg, color=0xC3B1E1, title=f"{user.name}'s Height")
    embed.set_author(name=f"{user}", icon_url=user.avatar.url if user.avatar else None)
    await ctx.send(embed=embed)

async def get_links(title : str):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'DNT': '1',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
    }

    async with aiohttp.ClientSession() as sn:
        global search_url
        async with sn.get(search_url + title, headers=headers, timeout=10) as response:
            store = json.loads(await response.text())
            links = [i['more_info']['song_pids'] for i in  store['albums']['data']]
            for idx,i in enumerate(links):
                if ',' in i:
                    links[idx] = i.split(',')[0]
                    links.append(i.split(', ')[1])
            return links

def decrypt_url(url):
    des_cipher = des(b"38346591", ECB, b"\0\0\0\0\0\0\0\0",
                     pad=None, padmode=PAD_PKCS5)
    enc_url = base64.b64decode(url.strip())
    dec_url = des_cipher.decrypt(enc_url, padmode=PAD_PKCS5).decode('utf-8')
    dec_url = dec_url.replace("_96.mp4", "_320.mp4")
    return dec_url
async def get_plays(pid : str):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'DNT': '1',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
    }

    async with aiohttp.ClientSession() as sn:
        global song_url
        async with sn.get(song_url + pid, headers=headers, timeout=10) as response:
            try:
                store = json.loads(await response.text())
                encrypted_url = store[pid]['encrypted_media_url']
                temp =  decrypt_url(encrypted_url)
                bot.links.append(temp)
                return temp
            except:
                pass

class MusicPlayer(discord.ui.View):
    def __init__(self, ctx: discord.ext.commands.Context, songname: str, num: int = 0):
        super().__init__(timeout=300)
        self.ctx = ctx
        self.num = num
        self.songname = songname
        play_button = discord.ui.Button(label="Play", style=discord.ButtonStyle.green)
        next_button = discord.ui.Button(label="⏭️", style=discord.ButtonStyle.secondary)
        prev_button = discord.ui.Button(label="⏮️", style=discord.ButtonStyle.secondary)
        stop_button = discord.ui.Button(label="Stop", style=discord.ButtonStyle.red)
        play_button.callback = self.play
        next_button.callback = self.next
        prev_button.callback = self.prev
        stop_button.callback = self.stop
        self.add_item(play_button)
        self.add_item(next_button)
        self.add_item(prev_button)
        self.add_item(stop_button)

    async def play(self, interaction: discord.Interaction):
        if not interaction.user.voice:
            await interaction.response.send_message("You are not in a voice channel")
            return
        new_embed = discord.Embed(description=f"Playing {bot.links[self.num]}", title=self.songname, color=0xC3B1E1)
        await bot.song_msg.edit(embed=new_embed)

        if bot.vc.is_playing():
            bot.vc.stop()

        bot.vc.play(discord.FFmpegPCMAudio(bot.links[self.num]))
        await interaction.response.defer()

    async def next(self, interaction: discord.Interaction):
        self.num += 1
        if self.num >= len(bot.links) or self.num < 0:
            await interaction.response.send_message("No more songs")
            self.num -=1
            return
        await self.play(interaction)

    async def prev(self, interaction: discord.Interaction):
        self.num -= 1
        if self.num >= len(bot.links) or self.num < 0:
            await interaction.response.send_message("No more songs")
            self.num +=1
            return

        await self.play(interaction)

    async def stop(self, interaction: discord.Interaction):
        if bot.vc.is_playing():
            bot.vc.stop()
            await interaction.response.send_message("Stopped")
        else:
            await interaction.response.send_message("No audio is currently playing")

@bot.command(aliases = ["search", "s"])
async def search_song(ctx : discord.ext.commands.Context, *song : str):
    start = time.time()
    if bot.vc and bot.vc.is_playing():
        await ctx.send("Already connected to a voice channel")
        return
    if not ctx.author.voice:
        await ctx.send("You are not in a voice channel")
        return
    embed = discord.Embed(description="Searching", title=" ".join(song), color=0xC3B1E1)
    bot.links = []
    bot.song_msg = await ctx.send(embed=embed)
    bot.vc = await ctx.author.voice.channel.connect()
    links = await get_links(" ".join(song))
    await asyncio.gather(*(get_plays(link) for link in links))
    new_embed = discord.Embed(description=f"Results : {bot.links[0]}", title=" ".join(song), color=0xC3B1E1)
    await bot.song_msg.edit(embed = new_embed, view = MusicPlayer(ctx,' '.join(song),0))

@bot.command(aliases = ["stop"])
async def leave(ctx : discord.ext.commands.Context):
    if not ctx.voice_client:
        await ctx.send("you aint in the party")
        return
    if not ctx.author.voice.channel == ctx.voice_client.channel:
        await ctx.send("not playing in your vc")
        return
    await ctx.voice_client.disconnect()

@bot.command(aliases = ["deposit", "dep"])
async def bank_add(ctx, amount : int | str = 100):
    user : User= session.query(User).filter_by(id=ctx.author.id).first()
    if amount == "all":
        amount = user.economy.cash
    amount = max(-amount, amount)
    cash = user.economy
    bank = user.bank
    if amount > cash.cash:
        await ctx.send("You dont have that much money")
        return
    bank.cash += amount
    cash.cash -= amount
    session.commit()
    embed = discord.Embed(color = 0xC3B1E1, description=f"Added {amount} to your bank")
    embed.add_field(name = "Bank", value = f"{bank.cash-amount} + {amount} = {bank.cash}")
    embed.add_field(name = "Cash", value = f"{cash.cash+amount} - {amount} = {cash.cash}")
    embed.set_author(name = ctx.author.name, icon_url = ctx.author.avatar.url if ctx.author.avatar else None)
    await ctx.send(embed = embed)

@bot.command(aliases = ["with"])
async def withdraw(ctx, amount : int | str = 100):
    user : User= session.query(User).filter_by(id=ctx.author.id).first()
    if amount == "all":
        amount = user.bank.cash
    amount = max(-amount, amount)
    user : User= session.query(User).filter_by(id=ctx.author.id).first()
    cash = user.economy
    bank = user.bank
    if amount > bank.cash:
        await ctx.send("You dont have that much money in the bank")
        return
    bank.cash -= amount
    cash.cash += amount
    session.commit()
    embed = discord.Embed(color = 0xC3B1E1, description=f"Withdrew {amount} from your bank")
    embed.add_field(name = "Bank", value = f"{bank.cash+amount} - {amount} = {bank.cash}")
    embed.add_field(name = "Cash", value = f"{cash.cash-amount} + {amount} = {cash.cash}")
    embed.set_author(name = ctx.author.name, icon_url = ctx.author.avatar.url if ctx.author.avatar else None)
    await ctx.send(embed = embed)

@bot.command()
async def level(ctx, user : discord.Member | None = None):
    if not user:
        user = ctx.author
    level = session.query(Level).filter_by(id = user.id).first()
    embed = discord.Embed(title = "Level", description=f"You are at level {level.level}", color = 0xC3B1E1)
    embed.add_field(name = "Messages" , value = f"{int((level.level)**1.5) * 20 - level.current} / {int(level.level**1.5) * 20 }")
    embed.add_field(name = "Next reward", value=f"{(level.level+1)**2 * 500}")
    embed.set_author(name = user.name, icon_url=user.avatar.url if user.avatar else None)
    await ctx.send(embed = embed)

@bot.command(aliases = ['rank'])
async def levellb(ctx):
    rankings = session.query(User).join(Level).order_by(-Level.level+0.00001*Level.current).all()
    user1 = session.query(User).filter_by(id = ctx.author.id).first()
    msg = []

    rank = 1
    for user in rankings:
        if len(msg)>=10:
            break
        msg.append(f"{rank}. <@{user.id}> - `Level {user.level.level}`")
    user_rank = rankings.index(user1)
    if user_rank >= 10:
        msg.extend(['.','.',f"{user_rank +1 }. {ctx.author.mention} - `Level {user1.level.level}`"])
    embed = discord.Embed(title = "Messages leaderboard", description='\n'.join(msg), color = 0xC3B1E1)
    await ctx.send(embed = embed)

@bot.command()
async def job(ctx, user : discord.Member | None = None):
    if not user:
        user = ctx.author
    existing = session.query(User).filter_by(id = user.id).first()
    embed = discord.Embed(title = "Job status", description=f"{user.mention} works as a {existing.job.name}", color = 0xC3B1E1)
    embed.add_field(name="Salary", value = f"{existing.job.salary}")
    embed.set_author(name = user.name, icon_url=user.avatar.url if user.avatar else None)
    await ctx.send(embed = embed)

@bot.command(aliases = ["jobs"])
async def joblist(ctx):
    embed = discord.Embed(title = "Available jobs", color = 0xC3B1E1,description="These are the jobs you can take up")
    for job, info in sorted(bot.jobs.items(), key = lambda x: x[1].get("salary")):
        embed.add_field(name=job.capitalize(), value=f"Salary : {info.get("salary")}\nLevel required : {info.get("min")}")
    await ctx.send(embed = embed)

@bot.command()
async def apply(ctx, name : str = ""):
    name = name.lower()
    if name not in bot.jobs:
        await ctx.send("Enter a valid job to apply for, check using $joblist")
        return
    user = session.query(User).filter_by(id = ctx.author.id).first()
    level = user.level.level
    if bot.jobs[name]["min"] > level:
        await ctx.send("You arent high enough of a level to join yet")
        return
    user.job.name = name
    user.job.salary = bot.jobs[name]["salary"]
    session.commit()
    embed = discord.Embed(color = 0xC3B1E1, title = "Applied successfully", description=f"{ctx.author.mention} now works as a {user.job.name}")
    embed.add_field(name = "Salary", value = f"{user.job.salary} coins")
    await ctx.send(embed = embed)

@bot.command(aliases = ["times" , "races"])
async def timelb(ctx):
    rankings = session.query(User).join(Bestrace).order_by(Bestrace.time).all()
    user1 = session.query(User).filter_by(id = ctx.author.id).first()
    msg = []

    rank = 1
    for user in rankings:
        if len(msg)>=10:
            break
        msg.append(f"{rank}. <@{user.id}> - `{user.bestrace.time:.2f}`")
    user_rank = rankings.index(user1)
    if user_rank >= 10:
        msg.extend(['.','.',f"{user_rank +1 }. {ctx.author.mention} - `{user1.bestrace.time:.2f}`"])
    embed = discord.Embed(title = "Race Leaderboard", description='\n'.join(msg), color = 0xFDFD96)
    await ctx.send(embed = embed)
if __name__ == '__main__':
    bot.run(os.getenv("TOKEN"))
