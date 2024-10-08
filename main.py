import asyncio
import os
import random
import re
import time
from collections import deque

import aiohttp
import discord
import yt_dlp
from aiohttp import ClientError
from discord.ext import commands
from discord.utils import get

intents = discord.Intents.all()
bot = commands.Bot(command_prefix = "$", intents=intents)
from urllib.request import Request, urlopen
import os 
from dotenv import load_dotenv

load_dotenv()
intents = discord.Intents.all()
bot = commands.Bot(command_prefix = "$", intents=intents)
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

    async with aiohttp.ClientSession() as session:
        for attempt in range(max_retries):
            try:
                async with session.get(url, headers=headers, timeout=10) as response:
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

@bot.event
async def on_ready():
    print(f"Bot is ready as {bot.user}")
    bot.changelogs = deque(maxlen=50)
    bot.logs = deque(maxlen=50)
    bot.song_queue = deque(maxlen=20)
    await bot.change_presence(activity=discord.Game(name="Ur mother"))
    bot.muted_role = get(bot.guilds[0].roles, name="muted") 
    if not bot.muted_role:
        bot.muted_role = await bot.guilds[0].create_role(name="muted")
        await asyncio.gather(*(channel.set_permissions(bot.muted_role, speak=False, send_messages=False) for channel in bot.guilds[0].channels))
    print("Muted role is set up.")
    for guild in bot.guilds:
        bot.loop.create_task(periodic_member_count_update(guild))

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
    embed = discord.Embed(description=f"**Before**: {before.content}\n **After**: {after.content}", color=0x00ff00)
    embed.set_author(name=f"{before.author}", icon_url=before.author.avatar.url if before.author.avatar else None)
    embed.set_footer(text=f"Edited in #{before.channel}")
    bot.changelogs.append(embed)

@bot.event
async def on_message_delete(message):
    if message.author == bot.user:
        return
    embed = discord.Embed(description=f"**Message**: {message.content}", color=0x00ff00)
    embed.set_author(name=f"{message.author}", icon_url=message.author.avatar.url if message.author.avatar else None)
    embed.set_footer(text=f"Deleted in #{message.channel}")
    bot.logs.append(embed)

@bot.event
async def on_member_join(member : discord.Member):
    gen = await member.guild.fetch_channel(channels["general"])
    async def give_role():
        role = get(member.guild.roles, name="diddy's victim")
        await member.add_roles(role)
    async def hello_there():
        embed = discord.Embed(description=f"{member.mention} has joined the server", color=discord.Color.random())
        embed.set_author(name=f"{member}", icon_url=member.avatar.url if member.avatar else None)
        embed.set_footer(text=f"Member count: {member.guild.member_count}")
        await gen.send(embed=embed)
    asyncio.gather(hello_there() , give_role())


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
    if len(bot.logs) < nums:
        await ctx.send("Not enough messages to snipe")
        return
    await ctx.send(embed=bot.logs[-nums])

@bot.command(aliases=["esnipe"])
async def changelog(ctx, nums = 1):
    if len(bot.changelogs) < nums:
        await ctx.send("Not enough messages to snipe")
        return
    await ctx.send(embed=bot.changelogs[-nums])

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
    async def send_msg():
        embed = discord.Embed(description=f"{to_kick.mention} has been kicked by {ctx.author.mention}", color=0x00ff00)
        await ctx.send(embed=embed)
    asyncio.gather( to_kick.kick() , send_msg())

@bot.command()
@commands.has_permissions(administrator=True)
async def ban(ctx, to_ban : discord.Member, reason : str | None = None):
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
async def avatar(ctx, user : discord.Member | None = None):
    if not user:
        user = ctx.author
    embed = discord.Embed(color=0x00ff00)
    embed.set_author(name=f"{user}", icon_url=user.avatar.url if user.avatar else None)
    embed.set_image(url=user.avatar.url if user.avatar else None)
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
        await msg.edit(content=f"Added to queue: [{info.get('title', 'Unknown Title')}]({youtube_url})")
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
            await msg.edit(content=f"Added to queue: [{info.get('title', 'Unknown Title')}]")
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
    start = time.time()
    nums = int(nums)
    nums = min(100,nums)
    before = bot.logs
    await ctx.channel.purge(limit = nums, check=lambda msg: msg.author == member)
    bot.logs = before

bot.run(token=os.getenv("TOKEN"))
