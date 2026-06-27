import discord
from discord.ext import commands
from discord import ui, app_commands
import os
import random
import string
import json
import subprocess
from dotenv import load_dotenv
import asyncio
import datetime
import docker
import time
import logging
import traceback
import aiohttp
import socket
import re
import psutil
import platform
import shutil
from typing import Optional, Literal
import sqlite3
import pickle
import base64
import threading
from flask import Flask, render_template, request, jsonify, session
from flask_socketio import SocketIO, emit
import paramiko

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('Vantix_bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('VantixBot')

load_dotenv()

TOKEN = os.getenv('DISCORD_TOKEN')
ADMIN_IDS = {int(id_) for id_ in os.getenv('ADMIN_IDS', '1210291131301101618').split(',') if id_.strip()}
ADMIN_ROLE_ID = int(os.getenv('ADMIN_ROLE_ID', '1376177459870961694'))
WATERMARK = "Vantixhost VPS Service"
WELCOME_MESSAGE = "Welcome To Vantixhost! Get Started With Us!"
MAX_VPS_PER_USER = int(os.getenv('MAX_VPS_PER_USER', '3'))
DEFAULT_OS_IMAGE = os.getenv('DEFAULT_OS_IMAGE', 'ubuntu:22.04')
DOCKER_NETWORK = os.getenv('DOCKER_NETWORK', 'bridge')
MAX_CONTAINERS = int(os.getenv('MAX_CONTAINERS', '100'))
DB_FILE = 'Vantix.db'

# Dockerfile template for custom VM-like images
DOCKERFILE_TEMPLATE = """
FROM {base_image}
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && \\
    apt-get install -y systemd systemd-sysv dbus sudo \\
                       curl gnupg2 apt-transport-https ca-certificates \\
                       software-properties-common \\
                       docker.io openssh-server tmate && \\
    apt-get clean && rm -rf /var/lib/apt/lists/*

RUN echo "root:{root_password}" | chpasswd
RUN useradd -m -s /bin/bash {username} && \\
    echo "{username}:{user_password}" | chpasswd && \\
    usermod -aG sudo {username}

RUN mkdir /var/run/sshd && \\
    sed -i 's/#PermitRootLogin prohibit-password/PermitRootLogin yes/' /etc/ssh/sshd_config && \\
    sed -i 's/#PasswordAuthentication yes/PasswordAuthentication yes/' /etc/ssh/sshd_config

RUN systemctl enable ssh && \\
    systemctl enable docker

RUN echo '{welcome_message}' > /etc/motd && \\
    echo 'echo "{welcome_message}"' >> /home/{username}/.bashrc && \\
    echo '{watermark}' > /etc/machine-info && \\
    echo 'vantix-{vps_id}' > /etc/hostname

RUN apt-get update && \\
    apt-get install -y neofetch htop nano vim wget git tmux net-tools dnsutils iputils-ping && \\
    apt-get clean && \\
    rm -rf /var/lib/apt/lists/*

STOPSIGNAL SIGRTMIN+3
CMD ["/sbin/init"]
"""

class Database:
    """Handles all data persistence using SQLite3"""
    def __init__(self, db_file):
        self.conn = sqlite3.connect(db_file, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self._create_tables()

    def _create_tables(self):
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS vps_instances (
                vps_id TEXT PRIMARY KEY,
                container_id TEXT,
                memory INTEGER,
                cpu TEXT,
                username TEXT,
                password TEXT,
                root_password TEXT,
                created_by TEXT,
                created_at TEXT,
                os_image TEXT
            )
        ''')
        self.conn.commit()

    def add_vps(self, vps_id, container_id, memory, cpu, username, password, root_password, created_by, os_image):
        self.cursor.execute('''
            INSERT INTO vps_instances VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (vps_id, container_id, memory, cpu, username, password, root_password, str(created_by), str(datetime.datetime.now()), os_image))
        self.conn.commit()

    def get_user_vps_count(self, user_id):
        self.cursor.execute('SELECT COUNT(*) FROM vps_instances WHERE created_by = ?', (str(user_id),))
        return self.cursor.fetchone()[0]

    def get_vps(self, vps_id):
        self.cursor.execute('SELECT * FROM vps_instances WHERE vps_id = ?', (vps_id,))
        return self.cursor.fetchone()

    def remove_vps(self, vps_id):
        self.cursor.execute('DELETE FROM vps_instances WHERE vps_id = ?', (vps_id,))
        self.conn.commit()

# Initialize Database and Docker
db = Database(DB_FILE)
try:
    docker_client = docker.from_env()
except Exception as e:
    logger.critical(f"Failed to connect to Docker daemon: {e}")
    exit(1)

class VantixBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        await self.tree.sync()
        logger.info("Slash commands synced successfully.")

bot = VantixBot()

def generate_random_string(length=10):
    return ''.join(random.choices(string.ascii_letters + string.digits), k=length)

@bot.event
async def on_ready():
    logger.info(f"Logged in as {bot.user} (ID: {bot.user.id})")
    await bot.change_presence(activity=discord.Game(name=WATERMARK))

## --- DISCORD SLASH COMMANDS ---

@bot.tree.command(name="create", description="Deploy a new VantixHost high-performance VPS instance")
@app_commands.describe(os="Select your target OS environment")
async def create(interaction: discord.Interaction, os: Literal['ubuntu', 'debian'] = 'ubuntu'):
    await interaction.response.defer(ephemeral=True)
    
    user_id = interaction.user.id
    if db.get_user_vps_count(user_id) >= MAX_VPS_PER_USER:
        await interaction.followup.send(f"❌ limit reached! You can only have {MAX_VPS_PER_USER} VPS instances.")
        return

    vps_id = f"vtx{generate_random_string(5).lower()}"
    username = "vantix"
    user_pass = generate_random_string(10)
    root_pass = generate_random_string(12)
    base_img = "ubuntu:22.04" if os == 'ubuntu' else "debian:stable"

    # Write out build context dynamically
    build_path = f"./build_{vps_id}"
    os.makedirs(build_path, exist_ok=True)
    
    dockerfile_content = DOCKERFILE_TEMPLATE.format(
        base_image=base_img,
        root_password=root_pass,
        username=username,
        user_password=user_pass,
        welcome_message=WELCOME_MESSAGE,
        watermark=WATERMARK,
        vps_id=vps_id
    )
    
    with open(f"{build_path}/Dockerfile", "w") as f:
        f.write(dockerfile_content)

    await interaction.followup.send("⚙️ Customizing OS environment & compiling packages...")

    try:
        # Build the custom isolated rootfs image
        image, _ = docker_client.images.build(path=build_path, rm=True)
        
        # CRITICAL FIX FOR DOCKER NOT SUPPORTED INSIDE CONTAINER:
        # We mount /lib/modules and pass privileged=True so systemd and inner Docker works cleanly.
        container = docker_client.containers.run(
            image.id,
            name=vps_id,
            detach=True,
            privileged=True,
            volumes={
                '/lib/modules': {'bind': '/lib/modules', 'mode': 'ro'},
                '/var/run/docker.sock': {'bind': '/var/run/docker.sock', 'mode': 'rw'} # Optional: fast inner docker share
            },
            tmpfs={'/run': '', '/run/lock': ''}
        )

        db.add_vps(vps_id, container.id, 2048, "2", username, user_pass, root_pass, user_id, base_img)
        shutil.rmtree(build_path) # cleanup build folder

        embed = discord.Embed(title=f"🚀 VantixHost Instance Online", color=0x2f3136)
        embed.add_field(name="VPS ID", value=f"`{vps_id}`", inline=True)
        embed.add_field(name="OS Platform", value=base_img.upper(), inline=True)
        embed.add_field(name="Root User", value="`root`", inline=True)
        embed.add_field(name="Root Password", value=f"||{root_pass}||", inline=False)
        embed.add_field(name="Standard User", value=f"`{username}` / ||{user_pass}||", inline=False)
        embed.set_footer(text=WATERMARK)
        
        await interaction.followup.send(embed=embed)

    except Exception as e:
        logger.error(f"Error during deployment sequence: {traceback.format_exc()}")
        await interaction.followup.send(f"❌ Failed to construct environment: `{str(e)}`")

@bot.tree.command(name="terminate", description="Permanently delete a VantixHost instance")
async def terminate(interaction: discord.Interaction, vps_id: str):
    await interaction.response.defer(ephemeral=True)
    vps_data = db.get_vps(vps_id)

    if not vps_data:
        await interaction.followup.send("❌ Instance non-existent in Vantix registration.")
        return

    # Check ownership or admin status
    if str(interaction.user.id) != vps_data[7] and interaction.user.id not in ADMIN_IDS:
        await interaction.followup.send("❌ Unauthorized ownership validation failure.")
        return

    try:
        container = docker_client.containers.get(vps_id)
        container.remove(force=True)
    except Exception:
        pass # Handle if it was missing from runtime but present in DB

    db.remove_vps(vps_id)
    await interaction.followup.send(f"💥 Instantly purged machine `{vps_id}` cleanly from system clusters.")

if __name__ == "__main__":
    if TOKEN:
        bot.run(TOKEN)
    else:
        logger.critical("No DISCORD_TOKEN defined inside environment profiles.")
