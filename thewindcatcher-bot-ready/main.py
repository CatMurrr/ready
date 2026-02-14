import os
import discord
from discord.ext import commands
import aiosqlite
import random
import datetime
import asyncio
from flask import Flask
import threading

# ---------------- KEEPALIVE ----------------
app = Flask("")

@app.route("/")
def home():
    return "alive"

def run():
    app.run(host="0.0.0.0", port=8080)

threading.Thread(target=run, daemon=True).start()

# ---------------- CONFIG ----------------
TOKEN = os.getenv("TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID"))

ROLE_MALE = "ᯓ★котᯓ★"
ROLE_FEMALE = "ᯓ❀кошкаᯓ❀"
ROLE_MOTHER = "── .✦Роженица˙𐃷˙"

DB = "thewindcatcher.db"
GUILD = discord.Object(id=GUILD_ID)

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

# ---------------- UTILS ----------------
def cap300(v): return max(0, min(300, v))
def cap100(v): return max(0, min(100, v))

def is_female(member):
    return any(r.name == ROLE_FEMALE for r in member.roles)

def g(member, male, female):
    return female if is_female(member) else male

async def db_exec(q, p=()):
    async with aiosqlite.connect(DB) as db:
        await db.execute(q, p)
        await db.commit()

async def db_fetch(q, p=()):
    async with aiosqlite.connect(DB) as db:
        async with db.execute(q, p) as c:
            return await c.fetchall()

async def get_user(uid):
    rows = await db_fetch("SELECT * FROM users WHERE id=?", (uid,))
    if not rows:
        await db_exec("INSERT INTO users(id) VALUES(?)", (uid,))
        return await get_user(uid)
    return rows[0]

# ---------------- DATABASE ----------------
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
            low_since TEXT
        )""")

        await db.execute("""
        CREATE TABLE IF NOT EXISTS config(
            type TEXT PRIMARY KEY,
            channel TEXT
        )""")

        await db.execute("""
        CREATE TABLE IF NOT EXISTS hunt(
            prey INTEGER DEFAULT 6,
            last_spawn TEXT
        )""")

        await db.execute("""
        CREATE TABLE IF NOT EXISTS herbs(
            available INTEGER DEFAULT 5,
            last_spawn TEXT
        )""")

        await db.execute("INSERT OR IGNORE INTO hunt(rowid,prey,last_spawn) VALUES(1,6,?)",
                         (datetime.datetime.utcnow().isoformat(),))
        await db.execute("INSERT OR IGNORE INTO herbs(rowid,available,last_spawn) VALUES(1,5,?)",
                         (datetime.datetime.utcnow().isoformat(),))
        await db.commit()

# ---------------- MULTI-CHANNEL SETUP ----------------
async def add_channel(type_name, cid):
    rows = await db_fetch("SELECT channel FROM config WHERE type=?", (type_name,))
    channels = set(map(int, rows[0][0].split(","))) if rows else set()
    channels.add(cid)
    await db_exec("INSERT OR REPLACE INTO config(type,channel) VALUES(?,?)", 
                  (type_name, ",".join(map(str, channels))))

async def remove_channel(type_name, cid):
    rows = await db_fetch("SELECT channel FROM config WHERE type=?", (type_name,))
    if not rows: return
    channels = set(map(int, rows[0][0].split(",")))
    channels.discard(cid)
    if channels:
        await db_exec("INSERT OR REPLACE INTO config(type,channel) VALUES(?,?)",
                      (type_name, ",".join(map(str, channels))))
    else:
        await db_exec("DELETE FROM config WHERE type=?", (type_name,))

async def get_channels(type_name):
    rows = await db_fetch("SELECT channel FROM config WHERE type=?", (type_name,))
    return set(map(int, rows[0][0].split(","))) if rows else set()

async def require_channel(inter, type_name):
    allowed = await get_channels(type_name)
    if inter.channel.id not in allowed:
        mentions = " ".join(f"<#{c}>" for c in allowed) if allowed else "не назначено"
        await inter.response.send_message(f"Дух молчит. Команда доступна только в: {mentions}", ephemeral=True)
        return False
    return True

# ---------------- BOT ----------------
class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        await init_db()
        self.loop.create_task(monitor_status())
        self.loop.create_task(spawn_prey())
        self.loop.create_task(spawn_herbs())
        await self.tree.sync(guild=GUILD)

bot = MyBot()

# ---------------- CHANNEL SETUP ----------------
@bot.event
async def on_message(msg):
    if bot.user in msg.mentions:
        text = msg.content.lower()
        # команды редактирования каналов
        if "ред" in text:
            parts = text.split()
            if len(parts) >= 4:
                type_name = parts[0]
                channel = msg.channel_mentions[0].id if msg.channel_mentions else None
                if channel:
                    await add_channel(type_name, channel)
                    await msg.channel.send(f"Дух запомнил {type_name}-канал <#{channel}>.")
        else:
            # обычная установка каналов через упоминание
            if "котята" in text: await add_channel("kittens", msg.channel.id)
            if "охота" in text: await add_channel("hunt", msg.channel.id)
            if "лагерь" in text: await add_channel("camp", msg.channel.id)
            if "состояние" in text: await add_channel("status", msg.channel.id)
            if "секретик" in text: await add_channel("admin", msg.channel.id)
            await msg.channel.send("Дух запомнил это место.")
    await bot.process_commands(msg)

# ---------------- SAFE COMMANDS ----------------
@bot.tree.command(guild=GUILD)
async def принюхаться(inter: discord.Interaction):
    gain = random.randint(1,15)
    u = await get_user(inter.user.id)
    await db_exec("UPDATE users SET orientation=? WHERE id=?", (cap300(u[2]+gain), inter.user.id))
    names = []
    async for m in inter.channel.history(limit=20):
        if m.author != bot.user:
            names.append(m.author.display_name)
    names = list(dict.fromkeys(names))[:5]
    await inter.response.send_message(f"{inter.user.mention} втягивает воздух. В памяти — {', '.join(names)}. (+{gain} ориентирования)")

# ---------------- KITTENS ----------------
@bot.tree.command(guild=GUILD)
async def попить_молока(inter: discord.Interaction):
    if not await require_channel(inter, "kittens"): return
    u = await get_user(inter.user.id)
    await db_exec("UPDATE users SET hunger=? WHERE id=?", (cap100(u[4]+20), inter.user.id))
    await inter.response.send_message(f"{inter.user.mention} лакает молоко. (+20% сытости)")

@bot.tree.command(guild=GUILD)
async def кусать_хвостик_роженицы(inter: discord.Interaction):
    if not await require_channel(inter, "kittens"): return
    mothers = [m for m in inter.guild.members if any(r.name == ROLE_MOTHER for r in m.roles)]
    if not mothers: return await inter.response.send_message("Рожениц рядом нет.")
    target = random.choice(mothers)
    gain = random.randint(1,5)
    u = await get_user(inter.user.id)
    await db_exec("UPDATE users SET strength=?, mood=? WHERE id=?", (cap300(u[1]+gain), cap100(u[6]+10), inter.user.id))
    await inter.response.send_message(f"{inter.user.mention} внезапно кусает за хвост {target.mention}! (+{gain} силы)")

@bot.tree.command(guild=GUILD)
async def поваляться_на_подстилке(inter: discord.Interaction):
    if not await require_channel(inter, "kittens"): return
    u = await get_user(inter.user.id)
    await db_exec("UPDATE users SET mood=? WHERE id=?", (cap100(u[6]+10), inter.user.id))
    await inter.response.send_message(f"{inter.user.mention} уютно устраивается. (+10% настроения)")

# ---------------- HUNT ----------------
async def hunt_attempt(inter, chance, success_range, fail_range, mood_change=0):
    if not await require_channel(inter, "hunt"): return
    prey = await db_fetch("SELECT prey FROM hunt WHERE rowid=1")
    if prey[0][0] <= 0: return await inter.response.send_message("Добычи больше нет.")
    success = random.randint(1,100) <= chance
    u = await get_user(inter.user.id)
    if success:
        gain = random.randint(*success_range)
        await db_exec("UPDATE hunt SET prey=prey-1 WHERE rowid=1")
        text = "Добыча поймана!"
    else:
        gain = random.randint(*fail_range)
        text = "Добыча ускользает..."
    new_strength = cap300(u[1]+gain if u[1]<300 else u[1])
    new_mood = cap100(u[6]+mood_change if success else u[6]-abs(mood_change))
    await db_exec("UPDATE users SET strength=?, mood=? WHERE id=?", (new_strength, new_mood, inter.user.id))
    await inter.response.send_message(f"{inter.user.mention} {text} (+{gain} силы)")

@bot.tree.command(guild=GUILD)
async def сделать_рывок(inter: discord.Interaction): await hunt_attempt(inter,30,(20,55),(0,10),5)
@bot.tree.command(guild=GUILD)
async def выследить_добычу(inter: discord.Interaction): await hunt_attempt(inter,40,(15,25),(0,10),5)
@bot.tree.command(guild=GUILD)
async def наступить_на_ветку(inter: discord.Interaction): await hunt_attempt(inter,5,(5,10),(0,3),-10)

# ---------------- CAMP ----------------
@bot.tree.command(guild=GUILD)
async def собрание(inter: discord.Interaction):
    if not await require_channel(inter, "camp"): return
    await inter.response.send_message("@everyone Начинается собрание племени.")

@bot.tree.command(guild=GUILD)
async def взять_лакомство(inter: discord.Interaction):
    if not await require_channel(inter, "camp"): return
    u = await get_user(inter.user.id)
    await db_exec("UPDATE users SET hunger=? WHERE id=?", (cap100(u[4]+30), inter.user.id))
    await inter.response.send_message(f"{inter.user.mention} перекусывает. (+30% сытости)")

@bot.tree.command(guild=GUILD)
async def попить_воды(inter: discord.Interaction):
    if not await require_channel(inter, "camp"): return
    u = await get_user(inter.user.id)
    await db_exec("UPDATE users SET thirst=? WHERE id=?", (cap100(u[5]+40), inter.user.id))
    await inter.response.send_message(f"{inter.user.mention} утоляет жажду. (+40%)")

# ---------------- STATUS ----------------
@bot.tree.command(guild=GUILD)
async def состояние(inter: discord.Interaction):
    if not await require_channel(inter, "status"): return
    u = await get_user(inter.user.id)
    await inter.response.send_message(f"{inter.user.mention}\nСытость: {u[4]}%\nЖажда: {u[5]}%\nНастроение: {u[6]}%")

@bot.tree.command(guild=GUILD)
async def скиллы(inter: discord.Interaction):
    if not await require_channel(inter, "status"): return
    u = await get_user(inter.user.id)
    await inter.response.send_message(f"{inter.user.mention}\nСила: {u[1]}/300\nОриентирование: {u[2]}/300\nМедицина: {u[3]}/300")

# ---------------- SPAWN TASKS ----------------
async def spawn_prey():
    await bot.wait_until_ready()
    while True:
        await db_exec("UPDATE hunt SET prey=6 WHERE rowid=1")
        chans = await get_channels("hunt")
        for ch in chans:
            c = bot.get_channel(ch)
            if c: await c.send("Кто-то шуршит в кустах...")
        await asyncio.sleep(3600)

async def spawn_herbs():
    await bot.wait_until_ready()
    while True:
        await db_exec("UPDATE herbs SET available=5 WHERE rowid=1")
        await asyncio.sleep(86400)

# ---------------- MONITOR ----------------
async def monitor_status():
    await bot.wait_until_ready()
    while True:
        chans = await get_channels("status")
        for ch in chans:
            c = bot.get_channel(ch)
            if not c: continue
            rows = await db_fetch("SELECT id,hunger,thirst,mood FROM users")
            for uid,h,t,m in rows:
                if h<10 or t<10 or m<10:
                    user = bot.get_user(uid)
                    if user: await c.send(f"{user.mention} параметры критичны!")
        await asyncio.sleep(10800)

# ---------------- READY ----------------
@bot.event
async def on_ready():
    print("Дух племени пробудился.")
    await bot.tree.sync(guild=GUILD)

bot.run(TOKEN)
