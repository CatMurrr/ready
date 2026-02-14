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

# ---------------- Бот ----------------
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

# ---------------- RP-команды ----------------
# Безопасные команды
@bot.tree.command(guild=discord.Object(id=GUILD_ID))
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

@bot.tree.command(guild=discord.Object(id=GUILD_ID))
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

@bot.tree.command(guild=discord.Object(id=GUILD_ID))
async def гоняться_за_листьями(inter: discord.Interaction):
    user = await get_user(inter.user.id)
    gain = random.randint(1, 15)
    await update(inter.user.id, "strength", cap(user[1]+gain))
    await inter.response.send_message(
        f"{inter.user.mention} носится за листьями. (+{gain} силы)"
    )

@bot.tree.command(guild=discord.Object(id=GUILD_ID))
async def ловить_шмеля(inter: discord.Interaction):
    user = await get_user(inter.user.id)
    gain = random.randint(1, 15)
    await update(inter.user.id, "strength", cap(user[1]+gain))
    await update(inter.user.id, "mood", percent(user[6]+10))
    await inter.response.send_message(
        f"{inter.user.mention} ловит шмеля. (+{gain} силы, +10% настроения)"
    )

# ---------------- Котячьи команды ----------------
@bot.tree.command(guild=discord.Object(id=GUILD_ID))
async def попить_молока(inter: discord.Interaction):
    if not await check_channel(inter, "котята"): return
    user = await get_user(inter.user.id)
    await update(inter.user.id, "hunger", percent(user[4]+20))
    await inter.response.send_message(
        f"{inter.user.mention} лаком{gender(inter.user,'ится','ится')} тёплым молоком. (+20% сытости)"
    )

# ---------------- Охотничьи команды ----------------
# Сделать рывок
@bot.tree.command(guild=discord.Object(id=GUILD_ID))
async def сделать_рывок(inter: discord.Interaction):
    if not await check_channel(inter, "охота"): return
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute("SELECT prey FROM hunt WHERE rowid=1") as cur:
            prey_left = (await cur.fetchone())[0]
    user = await get_user(inter.user.id)
    chance = 30
    success = random.randint(1,100) <= chance
    if success:
        gain = random.randint(20,555)
        prey_left -= 1
        await inter.response.send_message(f"{inter.user.mention} резко дергается вперед. (+{gain} силы)")
    else:
        gain = random.randint(0,10)
        await inter.response.send_message(f"{inter.user.mention} делает рывок, но добыча ускользает. (+{gain} силы)")
    await update(inter.user.id,"strength", cap(user[1]+gain))
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("UPDATE hunt SET prey=? WHERE rowid=1", (prey_left,))
        await db.commit()

# ---------------- Лагерь ----------------
@bot.tree.command(guild=discord.Object(id=GUILD_ID))
async def состояние(inter: discord.Interaction):
    if not await check_channel(inter, "состояние"): return
    user = await get_user(inter.user.id)
    await inter.response.send_message(
        f"{inter.user.mention} — Состояние: Сила {user[1]}, Ориентирование {user[2]}, Медицина {user[3]}, Сытость {user[4]}%, Жажда {user[5]}%, Настроение {user[6]}%"
    )

# ---------------- Админ ----------------
@bot.tree.command(guild=discord.Object(id=GUILD_ID))
async def навык(inter: discord.Interaction, target: discord.Member, amount: int, skill: str):
    if not await check_channel(inter, "секретик"): return
    user = await get_user(target.id)
    skill_field = skill.lower()
    if skill_field not in ["strength","orientation","medicine","hunger","thirst","mood"]:
        await inter.response.send_message("Неизвестный навык.")
        return
    new_val = max(0, min(300 if skill_field in ["strength","orientation","medicine"] else 100, getattr(user, skill_field,0)+amount))
    await update(target.id, skill_field, new_val)
    await inter.response.send_message(f"{target.display_name} — {skill_field} изменен на {new_val}")

# ---------------- Мониторинг ----------------
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

bot.loop.create_task(monitor_status())

# ---------------- Запуск ----------------
@bot.event
async def on_ready():
    await init_db()
    print(f"Бот {bot.user} онлайн на сервере {GUILD_ID}")

    # ⚡ Очистка старых команд только на этом сервере
    await bot.tree.clear_commands(guild=discord.Object(id=GUILD_ID))
    await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
    print("RP-команды синхронизированы и старые команды удалены")

bot.run(TOKEN)
