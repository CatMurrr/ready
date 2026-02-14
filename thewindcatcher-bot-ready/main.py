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
GUILD_ID = int(os.getenv("GUILD_ID"))

ROLE_MALE = "ᯓ★котᯓ★"
ROLE_FEMALE = "ᯓ❀кошкаᯓ❀"
ROLE_MOTHER = "── .✦Роженица˙𐃷˙"

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.message_content = True

DB_FILE = "thewindcatcher.db"
GUILD = discord.Object(id=GUILD_ID)

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

# ---------------- Database ----------------
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
        await db.commit()

# ---------------- Bot ----------------
class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        await init_db()
        print("База данных готова")

        self.loop.create_task(monitor_status())

        # синхронизация ТОЛЬКО для этого сервера
        await self.tree.sync(guild=GUILD)
        print("Команды синхронизированы")

bot = MyBot()

# ---------------- Monitor ----------------
async def monitor_status():
    await bot.wait_until_ready()
    while not bot.is_closed():
        async with aiosqlite.connect(DB_FILE) as db:
            async with db.execute("SELECT id,hunger,thirst,mood FROM users") as cur:
                rows = await cur.fetchall()

        for uid, hunger, thirst, mood in rows:
            if hunger < 10 or thirst < 10 or mood < 10:
                user = bot.get_user(uid)
                if user:
                    print(f"⚠ {user} критические параметры")

        await asyncio.sleep(10800)

# ---------------- RP команды ----------------
@bot.tree.command(guild=GUILD)
async def принюхаться(inter: discord.Interaction):
    user = await get_user(inter.user.id)
    gain = random.randint(1, 15)
    await update(inter.user.id, "orientation", cap(user[2] + gain))
    await inter.response.send_message(
        f"{inter.user.mention} втягивает воздух. (+{gain} ориентирования)"
    )

@bot.tree.command(guild=GUILD)
async def прислушаться(inter: discord.Interaction):
    user = await get_user(inter.user.id)
    gain = random.randint(1, 15)
    await update(inter.user.id, "orientation", cap(user[2] + gain))
    await inter.response.send_message(
        f"{inter.user.mention} прислушивается. (+{gain} ориентирования)"
    )

@bot.tree.command(guild=GUILD)
async def гоняться_за_листьями(inter: discord.Interaction):
    user = await get_user(inter.user.id)
    gain = random.randint(1, 15)
    await update(inter.user.id, "strength", cap(user[1] + gain))
    await inter.response.send_message(
        f"{inter.user.mention} носится за листьями. (+{gain} силы)"
    )

@bot.tree.command(guild=GUILD)
async def ловить_шмеля(inter: discord.Interaction):
    user = await get_user(inter.user.id)
    gain = random.randint(1, 15)
    await update(inter.user.id, "strength", cap(user[1] + gain))
    await update(inter.user.id, "mood", percent(user[6] + 10))
    await inter.response.send_message(
        f"{inter.user.mention} ловит шмеля. (+{gain} силы, +10% настроения)"
    )

@bot.tree.command(guild=GUILD)
async def попить_молока(inter: discord.Interaction):
    user = await get_user(inter.user.id)
    await update(inter.user.id, "hunger", percent(user[4] + 20))
    await inter.response.send_message(
        f"{inter.user.mention} пьёт молоко. (+20% сытости)"
    )

@bot.tree.command(guild=GUILD)
async def собрание(inter: discord.Interaction):
    await inter.response.send_message("@everyone Собрание племени начинается!")

@bot.tree.command(guild=GUILD)
async def навык(
    inter: discord.Interaction,
    target: discord.Member,
    amount: int,
    skill: str
):
    allowed = ["strength", "orientation", "medicine", "hunger", "thirst", "mood"]

    if skill not in allowed:
        await inter.response.send_message("Неизвестный навык.")
        return

    user = await get_user(target.id)
    index = allowed.index(skill) + 1
    current = user[index]

    max_val = 300 if skill in ["strength", "orientation", "medicine"] else 100
    new_val = max(0, min(max_val, current + amount))

    await update(target.id, skill, new_val)
    await inter.response.send_message(
        f"{target.display_name} — {skill} изменён на {new_val}"
    )

# ---------------- Ready ----------------
@bot.event
async def on_ready():
    print(f"Бот {bot.user} онлайн на сервере {GUILD_ID}")

bot.run(TOKEN)
