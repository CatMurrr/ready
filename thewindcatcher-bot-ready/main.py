import os
import discord
from discord.ext import commands
from flask import Flask
import threading

# ----------------- Discord бот -----------------
TOKEN = os.getenv("TOKEN")  # Бот токен из Koyeb env

intents = discord.Intents.default()
intents.messages = True
bot = commands.Bot(command_prefix='/', intents=intents)

@bot.event
async def on_ready():
    print(f'Дух леса пробудился. Бот {bot.user} онлайн!')

@bot.command()
async def привет(ctx):
    await ctx.send(f'Привет, {ctx.author.name}!')

# ----------------- Flask сервер для Koyeb -----------------
app = Flask('')

@app.route('/')
def home():
    return "alive"

def run():
    app.run(host='0.0.0.0', port=8080)

threading.Thread(target=run).start()

# ----------------- Запуск Discord бота -----------------
bot.run(TOKEN)
