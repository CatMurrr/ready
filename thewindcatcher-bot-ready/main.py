import os
import discord
from discord.ext import commands
import aiosqlite
import random
import datetime
import asyncio
from flask import Flask
import threading

# ---------------- Flask (Koyeb keepalive) ----------------
app = Flask("")

@app.route("/")
def home():
    return "alive"

def run_flask():
    app.run(host="0.0.0.0", port=8080)

threading.Thread(target=run_flask, daemon=True).start()

# ---------------- Config ----------------
TOKEN = os.getenv("TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID"))

ROLE_MALE = "ᯓ★котᯓ★"
ROLE_FEMALE = "ᯓ❀кошкаᯓ❀"
ROLE_MOTHER = "── .✦Роженица˙𐃷˙"

DB = "thewindcatcher.db"

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

GUILD = discord.Object(id=GUILD_ID)

# ---------------- Utils ----------------

def cap300(v): return max(0, min(300, v))
def cap100(v): return max(0, min(100, v))

def is_female(member):
    return any(r.name == ROLE_FEMALE for r in member.roles)

def gender_word(member, male, female):
    return female if is_female(member) else male

async def get_user(uid):
    async with aiosqlite.connect(DB) as db:
        async with db.execute("SELECT * FROM users WHERE id=?", (uid,)) as c:
            row = await c.fetchone()
        if not row:
            await db.execute("INSERT INTO users(id) VALUES(?)", (uid,))
            await db.commit()
            return await get_user(uid)
        return row

async def update(uid, field, value):
    async with aiosqlite.connect(DB) as db:
        await db.execute(f"UPDATE users SET {field}=? WHERE id=?", (value, uid))
        await db.commit()

async def get_channel(type_name):
    async with aiosqlite.connect(DB) as db:
        async with db.execute("SELECT channel FROM config WHERE type=?", (type_name,)) as c:
            r = await c.fetchone()
            if r:
                return r[0]
    return None

async def set_channel(type_name, channel_id):
    async with aiosqlite.connect(DB) as db:
        await db.execute("INSERT OR REPLACE INTO config(type,channel) VALUES(?,?)",
                         (type_name, channel_id))
        await db.commit()

# ---------------- Database ----------------

async def init_db():
    async with aiosqlite.connect(DB) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY,
            strength INTEGER DEFAULT 0,
            orientation INTEGER DEFAULT 0,
            medicine INTEGER DEFAULT 0,
            hunger INTEGER DEFAULT 100,
            thirst INTEGER DEFAULT 100,
            mood INTEGER DEFAULT 100,
            last_low TEXT
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
        await db.execute("""
        CREATE TABLE IF NOT EXISTS herbs(
            available INTEGER DEFAULT 5,
            last_spawn TEXT
        )
        """)
        await db.execute("INSERT OR IGNORE INTO hunt(rowid,prey,last_spawn) VALUES(1,6,?)",
                         (datetime.datetime.utcnow().isoformat(),))
        await db.execute("INSERT OR IGNORE INTO herbs(rowid,available,last_spawn) VALUES(1,5,?)",
                         (datetime.datetime.utcnow().isoformat(),))
        await db.commit()

# ---------------- Bot ----------------

class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        await init_db()
        self.loop.create_task(monitor())
        self.loop.create_task(spawn_prey())
        self.loop.create_task(spawn_herbs())
        await self.tree.sync(guild=GUILD)

bot = MyBot()

# ---------------- Channel Setup via mention ----------------

@bot.event
async def on_message(message):
    if bot.user in message.mentions:
        parts = message.content.lower().split()
        if "котята" in parts:
            await set_channel("котята", message.channel.id)
        if "охота" in parts:
            await set_channel("охота", message.channel.id)
        if "лагерь" in parts:
            await set_channel("лагерь", message.channel.id)
        if "состояние" in parts:
            await set_channel("состояние", message.channel.id)
        if "секретик" in parts:
            await set_channel("секретик", message.channel.id)
        await message.channel.send("Дух запомнил это место.")
    await bot.process_commands(message)

# ---------------- SAFE COMMANDS ----------------

@bot.tree.command(guild=GUILD)
async def принюхаться(inter: discord.Interaction):
    gain = random.randint(1,15)
    user = await get_user(inter.user.id)
    await update(inter.user.id,"orientation",cap300(user[2]+gain))
    names = [m.display_name async for m in inter.channel.history(limit=5)]
    text = ", ".join(names[:5])
    await inter.response.send_message(
        f"{inter.user.mention} втягивает воздух. В памяти — {text}. (+{gain} ориентирования)"
    )

@bot.tree.command(guild=GUILD)
async def прислушаться(inter: discord.Interaction):
    gain = random.randint(1,15)
    user = await get_user(inter.user.id)
    await update(inter.user.id,"orientation",cap300(user[2]+gain))
    msgs = [m.content async for m in inter.channel.history(limit=10) if m.content]
    sample = random.choice(msgs)[:60] if msgs else "тишина..."
    await inter.response.send_message(
        f"{inter.user.mention} прислушивается. В шорохах слышится: «{sample}» (+{gain} ориентирования)"
    )

@bot.tree.command(guild=GUILD)
async def гоняться_за_листьями(inter: discord.Interaction):
    gain = random.randint(1,15)
    user = await get_user(inter.user.id)
    await update(inter.user.id,"strength",cap300(user[1]+gain))
    await inter.response.send_message(
        f"{inter.user.mention} {gender_word(inter.user,'разгоняется','разгоняется')} по поляне, подбрасывая листья. (+{gain} силы)"
    )

@bot.tree.command(guild=GUILD)
async def ловить_шмеля(inter: discord.Interaction):
    gain = random.randint(1,15)
    user = await get_user(inter.user.id)
    await update(inter.user.id,"strength",cap300(user[1]+gain))
    await update(inter.user.id,"mood",cap100(user[6]+10))
    await inter.response.send_message(
        f"{inter.user.mention} ловко щёлкает лапой. Шмель жужжит последний раз. (+{gain} силы, +10% настроения)"
    )

# ---------------- STATUS ----------------

@bot.tree.command(guild=GUILD)
async def состояние(inter: discord.Interaction):
    if inter.channel.id != await get_channel("состояние"):
        return await inter.response.send_message("Дух молчит...",ephemeral=True)
    user = await get_user(inter.user.id)
    await inter.response.send_message(
        f"{inter.user.mention}\n"
        f"Сытость: {user[4]}%\n"
        f"Жажда: {user[5]}%\n"
        f"Настроение: {user[6]}%"
    )

@bot.tree.command(guild=GUILD)
async def скиллы(inter: discord.Interaction):
    if inter.channel.id != await get_channel("состояние"):
        return await inter.response.send_message("Дух молчит...",ephemeral=True)
    user = await get_user(inter.user.id)
    await inter.response.send_message(
        f"{inter.user.mention}\n"
        f"Сила: {user[1]}/300\n"
        f"Ориентирование: {user[2]}/300\n"
        f"Медицина: {user[3]}/300"
    )

# ---------------- MONITOR ----------------

async def monitor():
    await bot.wait_until_ready()
    while True:
        async with aiosqlite.connect(DB) as db:
            async with db.execute("SELECT id,hunger,thirst,mood,last_low FROM users") as c:
                rows = await c.fetchall()

        channel_id = await get_channel("состояние")
        if channel_id:
            ch = bot.get_channel(channel_id)
            for r in rows:
                uid,h,t,m,last = r
                if h<10 or t<10 or m<10:
                    user = bot.get_user(uid)
                    if user:
                        await ch.send(f"{user.mention} дух тревожится. Параметры критичны.")
        await asyncio.sleep(10800)

# ---------------- SPAWN ----------------

async def spawn_prey():
    await bot.wait_until_ready()
    while True:
        async with aiosqlite.connect(DB) as db:
            await db.execute("UPDATE hunt SET prey=6,last_spawn=? WHERE rowid=1",
                             (datetime.datetime.utcnow().isoformat(),))
            await db.commit()
        ch_id = await get_channel("охота")
        if ch_id:
            ch = bot.get_channel(ch_id)
            await ch.send("Кто-то шуршит в кустах...")
        await asyncio.sleep(3600)

async def spawn_herbs():
    await bot.wait_until_ready()
    while True:
        async with aiosqlite.connect(DB) as db:
            await db.execute("UPDATE herbs SET available=5,last_spawn=? WHERE rowid=1",
                             (datetime.datetime.utcnow().isoformat(),))
            await db.commit()
        await asyncio.sleep(86400)

# ---------------- READY ----------------

@bot.event
async def on_ready():
    print(f"Бот {bot.user} запущен.")
    await bot.tree.sync(guild=GUILD)

bot.run(TOKEN)
