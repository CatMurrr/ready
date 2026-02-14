# main.py
import os
import discord
from discord.ext import commands, tasks
import aiosqlite
import random
import datetime
from flask import Flask
import threading

# ---------------- Flask mini-server для Koyeb ----------------
app = Flask("")

@app.route("/")
def home():
    return "alive"

def run_flask():
    app.run(host="0.0.0.0", port=8080)

threading.Thread(target=run_flask).start()

# ---------------- Discord ----------------
TOKEN = os.getenv("TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID", 0))  # ID сервера из ENV

ROLE_MALE = "ᯓ★котᯓ★"
ROLE_FEMALE = "ᯓ❀кошкаᯓ❀"
ROLE_MOTHER = "── .✦Роженица˙𐃷˙"

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# ---------------- Database ----------------
DB_FILE = "thewindcatcher.db"

async def init_db():
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY,
            strength INTEGER DEFAULT 0,
            orientation INTEGER DEFAULT 0,
            medicine INTEGER DEFAULT 0,
            hunger INTEGER DEFAULT 100,
            thirst INTEGER DEFAULT 100,
            mood INTEGER DEFAULT 100
        )
        """)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS config(
            type TEXT PRIMARY KEY,
            channel INTEGER
        )
        """)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS hunt(
            prey INTEGER DEFAULT 6,
            last_spawn TEXT
        )
        """)
        await db.execute("INSERT OR IGNORE INTO hunt(rowid,prey,last_spawn) VALUES(1,6,?)",
                         (datetime.datetime.utcnow().isoformat(),))
        await db.commit()

async def get_user(uid):
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute("SELECT * FROM users WHERE id=?", (uid,)) as cur:
            row = await cur.fetchone()
        if not row:
            await db.execute("INSERT INTO users(id) VALUES(?)", (uid,))
            await db.commit()
            return await get_user(uid)
        return row

async def update(uid, field, value):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(f"UPDATE users SET {field}=? WHERE id=?", (value, uid))
        await db.commit()

# ---------------- Helpers ----------------
def cap(v): return max(0, min(300, v))
def percent(v): return max(0, min(100, v))
def gender(member, male, female):
    return female if any(r.name==ROLE_FEMALE for r in member.roles) else male

async def check_channel(interaction, type_name):
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute("SELECT channel FROM config WHERE type=?", (type_name,)) as cur:
            row = await cur.fetchone()
    if not row or row[0] != interaction.channel.id:
        await interaction.response.send_message("Дух не чувствует силы этого места...", ephemeral=True)
        return False
    return True

# ---------------- Command: setup channels ----------------
@bot.event
async def on_message(message):
    if message.guild and message.guild.id == GUILD_ID:
        if bot.user in message.mentions and "ред" in message.content:
            parts = message.content.split()
            if len(parts) >= 3 and message.channel_mentions:
                key = parts[1]
                ch = message.channel_mentions[0]
                async with aiosqlite.connect(DB_FILE) as db:
                    await db.execute("INSERT OR REPLACE INTO config(type,channel) VALUES(?,?)", (key,ch.id))
                    await db.commit()
                await message.channel.send(f"Дух запомнил это место для: {key}")
    await bot.process_commands(message)

# ---------------- Commands ----------------
@bot.tree.command()
async def принюхаться(inter: discord.Interaction):
    user = await get_user(inter.user.id)
    gain = random.randint(1,15)
    await update(inter.user.id,"orientation",cap(user[2]+gain))
    authors = []
    async for msg in inter.channel.history(limit=100):
        if msg.author.bot is False and msg.author not in authors:
            authors.append(msg.author)
        if len(authors) >= 5:
            break
    names = ", ".join(a.display_name for a in authors)
    await inter.response.send_message(f"{inter.user.mention} втягивает воздух. Следы ведут к: {names}. (+{gain} ориентирования)")

@bot.tree.command()
async def гоняться_за_листьями(inter: discord.Interaction):
    user = await get_user(inter.user.id)
    gain = random.randint(1,15)
    await update(inter.user.id,"strength",cap(user[1]+gain))
    await inter.response.send_message(f"{inter.user.mention} носится за листьями. (+{gain} силы)")

@bot.tree.command()
async def ловить_шмеля(inter: discord.Interaction):
    user = await get_user(inter.user.id)
    gain = random.randint(1,15)
    await update(inter.user.id,"strength",cap(user[1]+gain))
    await update(inter.user.id,"mood",percent(user[6]+10))
    await inter.response.send_message(f"{inter.user.mention} ловит шмеля. (+{gain} силы, +10% настроения)")

# ---------------- Котята ----------------
@bot.tree.command()
async def попить_молока(inter: discord.Interaction):
    if not await check_channel(inter,"котята"): return
    user = await get_user(inter.user.id)
    await update(inter.user.id,"hunger",percent(user[4]+20))
    await inter.response.send_message(f"{inter.user.mention} лаком{gender(inter.user,'ится','ится')} тёплым молоком. (+20% сытости)")

@bot.tree.command()
async def кусать_хвостик_роженицы(inter: discord.Interaction):
    if not await check_channel(inter,"котята"): return
    mothers = [m for m in inter.guild.members if any(r.name==ROLE_MOTHER for r in m.roles)]
    if not mothers:
        await inter.response.send_message("В лагере нет рожениц...")
        return
    target = random.choice(mothers)
    gain = random.randint(1,5)
    user = await get_user(inter.user.id)
    await update(inter.user.id,"strength",cap(user[1]+gain))
    await update(inter.user.id,"mood",percent(user[6]+10))
    await inter.response.send_message(f"{inter.user.mention} кусает за хвост {target.mention}. (+{gain} силы, +10% настроения)")

# ---------------- Запуск бота ----------------
@bot.event
async def on_ready():
    await init_db()
    print(f"Бот {bot.user} онлайн")
    await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
