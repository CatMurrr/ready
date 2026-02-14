import os
import discord
from discord.ext import commands
import aiosqlite
import random
import datetime
from flask import Flask
import threading
import asyncio

# ---------------- Flask mini-server для Koyeb ----------------
app = Flask("")

@app.route("/")
def home():
    return "alive"

def run_flask():
    app.run(host="0.0.0.0", port=8080)

threading.Thread(target=run_flask, daemon=True).start()

# ---------------- Discord ----------------
TOKEN = os.getenv("TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID", 0))

ROLE_MALE = "ᯓ★котᯓ★"
ROLE_FEMALE = "ᯓ❀кошкаᯓ❀"
ROLE_MOTHER = "── .✦Роженица˙𐃷˙"

intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.members = True

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
        await db.execute("""
        CREATE TABLE IF NOT EXISTS admin_channels(
            type TEXT PRIMARY KEY,
            channel INTEGER
        )
        """)
        await db.commit()

# ---------------- Helpers ----------------
def cap(v): return max(0, min(300, v))
def percent(v): return max(0, min(100, v))
def gender(member, male, female):
    return female if any(r.name == ROLE_FEMALE for r in member.roles) else male

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

async def check_channel(interaction, type_name):
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute("SELECT channel FROM config WHERE type=?", (type_name,)) as cur:
            row = await cur.fetchone()
    if not row or row[0] != interaction.channel.id:
        await interaction.response.send_message("Дух не чувствует силы этого места...", ephemeral=True)
        return False
    return True

# ---------------- Авто-пинг ----------------
async def monitor_status():
    await bot.wait_until_ready()
    while not bot.is_closed():
        async with aiosqlite.connect(DB_FILE) as db:
            async with db.execute("SELECT id,hunger,thirst,mood FROM users") as cur:
                rows = await cur.fetchall()
        for r in rows:
            uid, hunger, thirst, mood = r
            if hunger < 10 or thirst < 10 or mood < 10:
                user = bot.get_user(uid)
                channel = None
                async with aiosqlite.connect(DB_FILE) as db:
                    async with db.execute("SELECT channel FROM config WHERE type='состояние'") as cur:
                        row = await cur.fetchone()
                        if row: 
                            channel = bot.get_channel(row[0])
                if user and channel:
                    await channel.send(f"{user.mention} срочно нужно повысить параметры!")
        await asyncio.sleep(10800)

# ---------------- Бот ----------------
class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        self.loop.create_task(monitor_status())
        await self.tree.sync(guild=discord.Object(id=GUILD_ID))
        print("RP-команды синхронизированы")

bot = MyBot()

# ---------------- RP-команды ----------------
# Безопасные команды
@bot.tree.command()
async def принюхаться(inter: discord.Interaction):
    user = await get_user(inter.user.id)
    gain = random.randint(1, 15)
    await update(inter.user.id, "orientation", cap(user[2]+gain))
    authors = []
    async for msg in inter.channel.history(limit=100):
        if not msg.author.bot and msg.author not in authors:
            authors.append(msg.author)
        if len(authors) >= 5:
            break
    names = ", ".join(a.display_name for a in authors)
    await inter.response.send_message(
        f"{inter.user.mention} втягивает воздух. Следы ведут к: {names}. (+{gain} ориентирования)"
    )

@bot.tree.command()
async def прислушаться(inter: discord.Interaction):
    user = await get_user(inter.user.id)
    gain = random.randint(1, 15)
    await update(inter.user.id, "orientation", cap(user[2]+gain))
    snippets = []
    async for msg in inter.channel.history(limit=100):
        if not msg.author.bot:
            words = msg.content.split()
            if words:
                snippets.append(random.choice(words))
        if len(snippets) >= 10:
            break
    text = " ".join(snippets)
    await inter.response.send_message(
        f"{inter.user.mention} прислушивается и слышит: «{text}». (+{gain} ориентирования)"
    )

@bot.tree.command()
async def гоняться_за_листьями(inter: discord.Interaction):
    user = await get_user(inter.user.id)
    gain = random.randint(1, 15)
    await update(inter.user.id, "strength", cap(user[1]+gain))
    await inter.response.send_message(f"{inter.user.mention} носится за листьями. (+{gain} силы)")

@bot.tree.command()
async def ловить_шмеля(inter: discord.Interaction):
    user = await get_user(inter.user.id)
    gain = random.randint(1, 15)
    await update(inter.user.id, "strength", cap(user[1]+gain))
    await update(inter.user.id, "mood", percent(user[6]+10))
    await inter.response.send_message(f"{inter.user.mention} ловит шмеля. (+{gain} силы, +10% настроения)")

# Котячьи команды
@bot.tree.command()
async def попить_молока(inter: discord.Interaction):
    if not await check_channel(inter, "котята"): return
    user = await get_user(inter.user.id)
    await update(inter.user.id, "hunger", percent(user[4]+20))
    await inter.response.send_message(f"{inter.user.mention} лаком{gender(inter.user,'ится','ится')} тёплым молоком. (+20% сытости)")

@bot.tree.command()
async def кусать_хвостик_роженицы(inter: discord.Interaction):
    if not await check_channel(inter, "котята"): return
    mothers = [m for m in inter.guild.members if any(r.name == ROLE_MOTHER for r in m.roles)]
    if not mothers:
        await inter.response.send_message("В лагере нет рожениц...")
        return
    target = random.choice(mothers)
    gain = random.randint(1, 5)
    user = await get_user(inter.user.id)
    await update(inter.user.id, "strength", cap(user[1]+gain))
    await update(inter.user.id, "mood", percent(user[6]+10))
    await inter.response.send_message(f"{inter.user.mention} кусает за хвост {target.mention}. (+{gain} силы, +10% настроения)")

@bot.tree.command()
async def поваляться_на_подстилке(inter: discord.Interaction):
    if not await check_channel(inter, "котята"): return
    user = await get_user(inter.user.id)
    await update(inter.user.id, "mood", percent(user[6]+10))
    await inter.response.send_message(f"{inter.user.mention} уютно повалялся на подстилке. (+10% настроения)")

# ---------------- Охотничьи команды ----------------
async def spawn_prey():
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute("SELECT last_spawn, prey FROM hunt WHERE rowid=1") as cur:
            row = await cur.fetchone()
        last_spawn = datetime.datetime.fromisoformat(row[0])
        prey = row[1]
        now = datetime.datetime.utcnow()
        if (now - last_spawn).total_seconds() >= 3600:
            await db.execute("UPDATE hunt SET prey=?, last_spawn=? WHERE rowid=1", (6, now.isoformat()))
            await db.commit()

@bot.tree.command()
async def сделать_рывок(inter: discord.Interaction):
    if not await check_channel(inter, "охота"): return
    await spawn_prey()
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute("SELECT prey FROM hunt WHERE rowid=1") as cur:
            prey_left = (await cur.fetchone())[0]
    user = await get_user(inter.user.id)
    chance = 30
    success = random.randint(1,100) <= chance
    if success:
        gain = random.randint(20,555)
        prey_left -= 1
        await inter.response.send_message(f"{inter.user.mention} резко дергается вперед. Добыча поймана. (+{gain} силы)")
    else:
        gain = random.randint(0,10)
        await inter.response.send_message(f"{inter.user.mention} делает рывок, но добыча ускользает. (+{gain} силы)")
    await update(inter.user.id,"strength", cap(user[1]+gain))
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("UPDATE hunt SET prey=? WHERE rowid=1", (prey_left,))
        await db.commit()

# Остальные охотничьи, лагерь и админ команды вставляются по той же схеме: @bot.tree.command()

# ---------------- Запуск ----------------
@bot.event
async def on_ready():
    await init_db()
    print(f"Бот {bot.user} онлайн на сервере {GUILD_ID}")

bot.run(TOKEN)
