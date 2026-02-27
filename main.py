import discord
from discord import app_commands
from discord.ext import commands
import random
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
import sqlite3

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

DB_FILE = "economy.db"

# ER:LC-inspired jobs with weekly base pay (higher = better "paychecks" in game)
JOBS = {
    "Unemployed": 500,
    "Civilian": 800,
    "Postal Worker": 1800,
    "Farmer": 1500,
    "Gas Station Worker": 2200,
    "Hospital Worker": 2500,
    "Construction Worker": 2800,
    "DOT": 3200,
    "Firefighter": 3500,
    "Police": 4000,
    "Sheriff": 4200,
    "Judge": 5000  # premium vibes
}

def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            coins INTEGER DEFAULT 0,
            job TEXT DEFAULT 'Unemployed',
            last_work TEXT,
            last_daily TEXT,
            last_weekly TEXT
        )
    ''')
    conn.commit()
    conn.close()

def get_user(user_id: int):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = c.fetchone()
    conn.close()
    return user

def create_user(user_id: int):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (user_id, coins, job) VALUES (?, 0, 'Unemployed')", (user_id,))
    conn.commit()
    conn.close()

def update_coins(user_id: int, amount: int):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("UPDATE users SET coins = coins + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()

def update_job(user_id: int, job: str):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("UPDATE users SET job = ? WHERE user_id = ?", (job, user_id))
    conn.commit()
    conn.close()

def update_last_work(user_id: int, timestamp: str):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("UPDATE users SET last_work = ? WHERE user_id = ?", (timestamp, user_id))
    conn.commit()
    conn.close()

def update_last_daily(user_id: int, timestamp: str):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("UPDATE users SET last_daily = ? WHERE user_id = ?", (timestamp, user_id))
    conn.commit()
    conn.close()

def update_last_weekly(user_id: int, timestamp: str):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("UPDATE users SET last_weekly = ? WHERE user_id = ?", (timestamp, user_id))
    conn.commit()
    conn.close()

@bot.event
async def on_ready():
    init_db()
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(e)

def seconds_to_hhmmss(seconds):
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h}h {m}m {s}s" if h else f"{m}m {s}s"

@bot.tree.command(name="balance", description="Check your or someone else's balance")
@app_commands.describe(member="The member to check (optional)")
async def balance(interaction: discord.Interaction, member: discord.Member = None):
    target = member or interaction.user
    user = get_user(target.id)

    if not user:
        create_user(target.id)
        coins = 0
        job = "Unemployed"
    else:
        coins = user["coins"]
        job = user["job"]

    embed = discord.Embed(
        title=f"{target.name}'s Balance",
        description=f"**{coins:,}** coins 💰\n**Job:** {job}",
        color=discord.Color.gold()
    )
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="setjob", description="Choose your ERLC-style job for weekly income")
@app_commands.describe(job="Your job (e.g. Police, Firefighter, Postal Worker, Farmer)")
async def setjob(interaction: discord.Interaction, job: str):
    job = job.title()  # Capitalize nicely
    if job not in JOBS:
        available = ", ".join(sorted(JOBS.keys()))
        await interaction.response.send_message(
            f"Invalid job! Available: **{available}**\n(You can use 'Unemployed' or any listed.)",
            ephemeral=True
        )
        return

    user_id = interaction.user.id
    create_user(user_id)  # ensure exists
    update_job(user_id, job)

    await interaction.response.send_message(
        f"Job set to **{job}**!\nYou'll earn higher weekly paychecks based on this role. Use `/weekly` to claim.",
        ephemeral=False
    )

@bot.tree.command(name="weekly", description="Claim your weekly paycheck from your ERLC job (once per 7 days)")
async def weekly(interaction: discord.Interaction):
    user_id = interaction.user.id
    user = get_user(user_id)

    if not user:
        create_user(user_id)
        user = get_user(user_id)

    job = user["job"]
    base_pay = JOBS.get(job, 500)

    # Add random bonus like in-game activity/tasks
    bonus = random.randint(0, base_pay // 2)
    total = base_pay + bonus

    last_weekly_str = user["last_weekly"]
    can_claim = True
    if last_weekly_str:
        last_weekly = datetime.fromisoformat(last_weekly_str)
        if datetime.now() < last_weekly + timedelta(days=7):
            remaining = (last_weekly + timedelta(days=7) - datetime.now()).total_seconds()
            await interaction.response.send_message(
                f"Next paycheck available in **{seconds_to_hhmmss(int(remaining))}** ⏳",
                ephemeral=True
            )
            can_claim = False

    if can_claim:
        update_coins(user_id, total)
        update_last_weekly(user_id, datetime.now().isoformat())

        await interaction.response.send_message(
            f"**{job} Paycheck** deposited! 💼\n"
            f"Base: **{base_pay:,}** + bonus **{bonus:,}** = **{total:,}** coins\n"
            f"New balance: **{user['coins'] + total:,}**\nCome back in 7 days!"
        )

@bot.tree.command(name="work", description="Work and earn some quick coins (1 hour cooldown)")
async def work(interaction: discord.Interaction):
    user_id = interaction.user.id
    user = get_user(user_id)

    if not user:
        create_user(user_id)
        user = get_user(user_id)

    last_work_str = user["last_work"]
    if last_work_str:
        last_work = datetime.fromisoformat(last_work_str)
        if datetime.now() < last_work + timedelta(hours=1):
            remaining = (last_work + timedelta(hours=1) - datetime.now()).total_seconds()
            await interaction.response.send_message(
                f"You can work again in **{seconds_to_hhmmss(int(remaining))}** ⏳",
                ephemeral=True
            )
            return

    earnings = random.randint(50, 200)  # small boost
    update_coins(user_id, earnings)
    update_last_work(user_id, datetime.now().isoformat())

    await interaction.response.send_message(
        f"You earned **{earnings}** coins from a quick shift! 💼 Current: **{user['coins'] + earnings:,}**"
    )

@bot.tree.command(name="daily", description="Claim your daily reward (once per day)")
async def daily(interaction: discord.Interaction):
    user_id = interaction.user.id
    user = get_user(user_id)

    if not user:
        create_user(user_id)
        user = get_user(user_id)

    last_daily_str = user["last_daily"]
    if last_daily_str:
        last_daily = datetime.fromisoformat(last_daily_str)
        if datetime.now().date() == last_daily.date():
            await interaction.response.send_message(
                "You've already claimed today! Come back tomorrow 🌞",
                ephemeral=True
            )
            return

    reward = random.randint(200, 600)
    update_coins(user_id, reward)
    update_last_daily(user_id, datetime.now().isoformat())

    await interaction.response.send_message(
        f"Daily reward: **{reward}** coins 🎁\nNew balance: **{user['coins'] + reward:,}**"
    )

bot.run(TOKEN)
