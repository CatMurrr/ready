import os
import discord
from discord.ext import commands, tasks
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
def is_female(member): return any(r.name == ROLE_FEMALE for r in member.roles)
def g(member, male, female): return female if is_female(member) else male

# ---------------- DATABASE SERVICE ----------------
class DBService:
    def __init__(self, db_path):
        self.db_path = db_path

    async def execute(self, query, params=()):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(query, params)
            await db.commit()

    async def fetch(self, query, params=()):
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(query, params) as c:
                return await c.fetchall()

db_service = DBService(DB)

# ---------------- USER SERVICE ----------------
class UserService:
    def __init__(self, db: DBService):
        self.db = db

    async def get_user(self, uid):
        rows = await self.db.fetch("SELECT * FROM users WHERE id=?", (uid,))
        if not rows:
            await self.db.execute("INSERT INTO users(id) VALUES(?)", (uid,))
            return await self.get_user(uid)
        return rows[0]

    async def update_user(self, uid, **kwargs):
        cols = ", ".join(f"{k}=?" for k in kwargs)
        vals = tuple(kwargs.values()) + (uid,)
        await self.db.execute(f"UPDATE users SET {cols} WHERE id=?", vals)

user_service = UserService(db_service)

# ---------------- CHANNEL SERVICE ----------------
class ChannelService:
    def __init__(self, db: DBService):
        self.db = db

    async def add_channel(self, type_name, channel_id):
        r = await self.db.fetch("SELECT channel FROM config WHERE type=?", (type_name,))
        if not r:
            await self.db.execute("INSERT INTO config(type,channel) VALUES(?,?)", (type_name, channel_id))
        else:
            existing = r[0][0]
            if isinstance(existing, int):
                if existing != channel_id:
                    await self.db.execute("UPDATE config SET channel=? WHERE type=?", (f"{existing},{channel_id}", type_name))
            else:
                channels = set(map(int, str(existing).split(",")))
                channels.add(channel_id)
                await self.db.execute("UPDATE config SET channel=? WHERE type=?", (",".join(map(str, channels)), type_name))

    async def get_channels(self, type_name):
        r = await self.db.fetch("SELECT channel FROM config WHERE type=?", (type_name,))
        if not r: return []
        ch = r[0][0]
        if isinstance(ch, int): return [ch]
        return list(map(int, str(ch).split(",")))

channel_service = ChannelService(db_service)

# ---------------- DATABASE INIT ----------------
async def init_db():
    await db_service.execute("""
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
    await db_service.execute("""
    CREATE TABLE IF NOT EXISTS config(
        type TEXT PRIMARY KEY,
        channel TEXT
    )""")
    await db_service.execute("""
    CREATE TABLE IF NOT EXISTS hunt(
        prey INTEGER DEFAULT 6,
        last_spawn TEXT
    )""")
    await db_service.execute("""
    CREATE TABLE IF NOT EXISTS herbs(
        available INTEGER DEFAULT 5,
        last_spawn TEXT
    )""")
    await db_service.execute("INSERT OR IGNORE INTO hunt(rowid,prey,last_spawn) VALUES(1,6,?)", (datetime.datetime.utcnow().isoformat(),))
    await db_service.execute("INSERT OR IGNORE INTO herbs(rowid,available,last_spawn) VALUES(1,5,?)", (datetime.datetime.utcnow().isoformat(),))

# ---------------- BOT ----------------
class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)
        self.user_service = user_service
        self.channel_service = channel_service

    async def setup_hook(self):
        await init_db()
        self.monitor_status.start()
        self.spawn_prey.start()
        self.spawn_herbs.start()
        await self.tree.sync(guild=GUILD)

bot = MyBot()

# ---------------- EVENTS ----------------
@bot.event
async def on_ready():
    print("Дух племени пробудился.")

@bot.event
async def on_message(msg):
    if bot.user in msg.mentions:
        text = msg.content.lower()
        if "котята" in text: await channel_service.add_channel("kittens", msg.channel.id)
        if "охота" in text: await channel_service.add_channel("hunt", msg.channel.id)
        if "лагерь" in text: await channel_service.add_channel("camp", msg.channel.id)
        if "состояние" in text: await channel_service.add_channel("status", msg.channel.id)
        if "секретик" in text: await channel_service.add_channel("admin", msg.channel.id)
        await msg.channel.send("Дух запомнил это место.")
    await bot.process_commands(msg)

# ---------------- HELPERS ----------------
async def require_channel(inter, type_name):
    channels = await channel_service.get_channels(type_name)
    if not channels:
        await inter.response.send_message(f"Дух молчит. Каналы для {type_name} не назначены.", ephemeral=True)
        return False
    if inter.channel.id not in channels:
        await inter.response.send_message(f"Дух молчит. Команда доступна только в назначенных каналах.", ephemeral=True)
        return False
    return True

# ---------------- SAFE COMMANDS ----------------
@bot.tree.command(guild=GUILD)
async def принюхаться(inter: discord.Interaction):
    gain = random.randint(1,15)
    u = await user_service.get_user(inter.user.id)
    await user_service.update_user(inter.user.id, orientation=cap300(u[2]+gain))
    names = []
    async for m in inter.channel.history(limit=20):
        if m.author != bot.user:
            names.append(m.author.display_name)
    names = list(dict.fromkeys(names))[:5]
    await inter.response.send_message(f"{inter.user.mention} втягивает воздух. В памяти — {', '.join(names)}. (+{gain} ориентирования)")

# ---------------- KITTENS COMMANDS ----------------
@bot.tree.command(guild=GUILD)
async def попить_молока(inter: discord.Interaction):
    if not await require_channel(inter, "kittens"): return
    u = await user_service.get_user(inter.user.id)
    await user_service.update_user(inter.user.id, hunger=cap100(u[4]+20))
    await inter.response.send_message(f"{inter.user.mention} лакает молоко. (+20% сытости)")

@bot.tree.command(guild=GUILD)
async def кусать_хвостик_роженицы(inter: discord.Interaction):
    if not await require_channel(inter, "kittens"): return
    guild = inter.guild
    mothers = [m for m in guild.members if any(r.name==ROLE_MOTHER for r in m.roles)]
    if not mothers: return await inter.response.send_message("Рожениц рядом нет.")
    target = random.choice(mothers)
    gain = random.randint(1,5)
    u = await user_service.get_user(inter.user.id)
    await user_service.update_user(inter.user.id, strength=cap300(u[1]+gain), mood=cap100(u[6]+10))
    await inter.response.send_message(f"{inter.user.mention} внезапно кусает за хвост {target.mention}! (+{gain} силы)")

@bot.tree.command(guild=GUILD)
async def поваляться_на_подстилке(inter: discord.Interaction):
    if not await require_channel(inter, "kittens"): return
    u = await user_service.get_user(inter.user.id)
    await user_service.update_user(inter.user.id, mood=cap100(u[6]+10))
    await inter.response.send_message(f"{inter.user.mention} уютно устраивается. (+10% настроения)")

# ---------------- HUNT COMMANDS ----------------
async def hunt_attempt(inter, chance, success_range, fail_range, mood_change=0):
    if not await require_channel(inter, "hunt"): return
    prey = await db_service.fetch("SELECT prey FROM hunt WHERE rowid=1")
    if prey[0][0]<=0:
        return await inter.response.send_message("Добычи больше нет.")
    success = random.randint(1,100) <= chance
    u = await user_service.get_user(inter.user.id)
    if success:
        gain = random.randint(*success_range)
        await db_service.execute("UPDATE hunt SET prey=prey-1 WHERE rowid=1")
        text = "Добыча поймана!"
    else:
        gain = random.randint(*fail_range)
        text = "Добыча ускользает..."
    new_strength = cap300(u[1]+gain if u[1]<300 else u[1])
    new_mood = cap100(u[6]+mood_change if success else u[6]-abs(mood_change))
    await user_service.update_user(inter.user.id, strength=new_strength, mood=new_mood)
    await inter.response.send_message(f"{inter.user.mention} {text} (+{gain} силы)")

@bot.tree.command(guild=GUILD)
async def сделать_рывок(inter: discord.Interaction): await hunt_attempt(inter,30,(20,55),(0,10),5)
@bot.tree.command(guild=GUILD)
async def выследить_добычу(inter: discord.Interaction): await hunt_attempt(inter,40,(15,25),(0,10),5)
@bot.tree.command(guild=GUILD)
async def наступить_на_ветку(inter: discord.Interaction): await hunt_attempt(inter,5,(5,10),(0,3),-10)

# ---------------- CAMP COMMANDS ----------------
@bot.tree.command(guild=GUILD)
async def собрание(inter: discord.Interaction):
    if not await require_channel(inter, "camp"): return
    await inter.response.send_message("@everyone Начинается собрание племени.")

@bot.tree.command(guild=GUILD)
async def взять_лакомство(inter: discord.Interaction):
    if not await require_channel(inter, "camp"): return
    u = await user_service.get_user(inter.user.id)
    await user_service.update_user(inter.user.id, hunger=cap100(u[4]+30))
    await inter.response.send_message(f"{inter.user.mention} перекусывает. (+30% сытости)")

@bot.tree.command(guild=GUILD)
async def попить_воды(inter: discord.Interaction):
    if not await require_channel(inter, "camp"): return
    u = await user_service.get_user(inter.user.id)
    await user_service.update_user(inter.user.id, thirst=cap100(u[5]+40))
    await inter.response.send_message(f"{inter.user.mention} утоляет жажду. (+40%)")

# ---------------- STATUS COMMANDS ----------------
@bot.tree.command(guild=GUILD)
async def состояние(inter: discord.Interaction):
    if not await require_channel(inter, "status"): return
    u = await user_service.get_user(inter.user.id)
    await inter.response.send_message(f"{inter.user.mention}\nСытость: {u[4]}%\nЖажда: {u[5]}%\nНастроение: {u[6]}%")

@bot.tree.command(guild=GUILD)
async def скиллы(inter: discord.Interaction):
    if not await require_channel(inter, "status"): return
    u = await user_service.get_user(inter.user.id)
    await inter.response.send_message(f"{inter.user.mention}\nСила: {u[1]}/300\nОриентирование: {u[2]}/300\nМедицина: {u[3]}/300")

# ---------------- ADMIN COMMANDS ----------------
@bot.tree.command(guild=GUILD)
async def навык(inter: discord.Interaction, user: discord.Member, value: int, skill: str):
    if not await require_channel(inter, "admin"): return
    u = await user_service.get_user(user.id)
    current = u[{'strength':1,'orientation':2,'medicine':3}[skill]]
    new_value = cap300(current + value)
    await user_service.update_user(user.id, **{skill:new_value})
    await inter.response.send_message(f"{user.mention} навык {skill} изменён на {new_value}")

@bot.tree.command(guild=GUILD)
async def состояние_админ(inter: discord.Interaction, user: discord.Member, value: int, param: str):
    if not await require_channel(inter, "admin"): return
    u = await user_service.get_user(user.id)
    idx_map = {'hunger':4,'thirst':5,'mood':6}
    current = u[idx_map[param]]
    new_value = cap100(current + value)
    await user_service.update_user(user.id, **{param:new_value})
    await inter.response.send_message(f"{user.mention} параметр {param} изменён на {new_value}")

# ---------------- SPAWN TASKS ----------------
@tasks.loop(hours=1)
async def spawn_prey():
    await db_service.execute("UPDATE hunt SET prey=6 WHERE rowid=1")
    channels = await channel_service.get_channels("hunt")
    for ch_id in channels:
        c = bot.get_channel(ch_id)
        if c: await c.send("Кто-то шуршит в кустах...")

@tasks.loop(hours=24)
async def spawn_herbs():
    await db_service.execute("UPDATE herbs SET available=5 WHERE rowid=1")

@tasks.loop(hours=3)
async def monitor_status():
    channels = await channel_service.get_channels("status")
    rows = await db_service.fetch("SELECT id,hunger,thirst,mood FROM users")
    for ch_id in channels:
        c = bot.get_channel(ch_id)
        if not c: continue
        for uid,h,t,m in rows:
            if h<10 or t<10 or m<10:
                user = bot.get_user(uid)
                if user:
                    await c.send(f"{user.mention} параметры критичны!")

# ---------------- RUN ----------------
bot.run(TOKEN)
