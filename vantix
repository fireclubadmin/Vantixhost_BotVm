import discord
from discord.ext import commands
from discord import app_commands
import docker
import random
import string
import os

class VPSBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)

    async def on_ready(self):
        print(f"🚀 Bot logged in as {self.user.name}")
        try:
            synced = await self.tree.sync()
            print(f"🔄 Synced {len(synced)} slash commands globally.")
        except Exception as e:
            print(f"❌ Failed to sync commands: {e}")

bot = VPSBot()
try:
    docker_client = docker.from_env()
except Exception as e:
    print(f"⚠️ Docker client initialization warning (Ensure Docker is running): {e}")

def generate_password(length=12):
    return ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(length))

# --- INTERACTIVE MENU INTERFACES ---
class ConnectionMenu(discord.ui.View):
    def __init__(self, ip, port, password):
        super().__init__(timeout=None)
        self.ip = ip
        self.port = port
        self.password = password

    @discord.ui.button(label="💻 Standard SSH Cmd", style=discord.ButtonStyle.primary, emoji="📟")
    async def ssh_cmd(self, interaction: discord.Interaction, button: discord.ui.Button):
        cmd = f"ssh root@{self.ip} -p {self.port}"
        await interaction.response.send_message(
            f"**Copy/Paste Terminal Command:**\n```bash\n{cmd}\n```\n*Password when prompted:* `{self.password}`", 
            ephemeral=True
        )

    @discord.ui.button(label="📱 Termux Mobile Cmd", style=discord.ButtonStyle.success, emoji="📲")
    async def termux_cmd(self, interaction: discord.Interaction, button: discord.ui.Button):
        cmd = f"pkg install openssh -y && ssh root@{self.ip} -p {self.port}"
        await interaction.response.send_message(
            f"**Copy & Paste into Termux:**\n```bash\n{cmd}\n```\n*Password:* `{self.password}`", 
            ephemeral=True
        )

    @discord.ui.button(label="⚡ Setup Tmate (Share)", style=discord.ButtonStyle.secondary, emoji="🚀")
    async def tmate_cmd(self, interaction: discord.Interaction, button: discord.ui.Button):
        setup_info = "To instantly share this terminal screen over web/ssh, paste this inside your VPS shell:\n"
        setup_info += "```bash\napt-get update && apt-get install tmate -y && tmate\n```"
        await interaction.response.send_message(setup_info, ephemeral=True)


# --- SLASH COMMANDS ---

# 1. CREATE COMMAND
@bot.tree.command(name="create_vps", description="Provision a brand-new customized VPS container.")
@app_commands.describe(
    name="Hostname/Identifier", 
    ram="Memory limit (e.g. 1g, 512m)", 
    cpu="Core count limit (e.g., 1, 2)",
    disk="Simulated disk quota tag", 
    owner="Mention the target user receiving ownership"
)
async def create_vps(interaction: discord.Interaction, name: str, ram: str, cpu: int, disk: str, owner: discord.User):
    await interaction.response.defer(ephemeral=False)
    
    clean_name = "".join(c for c in name if c.isalnum() or c in ('-', '_')).lower()
    root_password = generate_password()
    
    # Map external communication port dynamically 
    vps_ssh_port = random.randint(20000, 30000)
    server_public_ip = "YOUR_SERVER_PUBLIC_IP" # Replace with your node's real IP address

    try:
        # Enforce CPU quota metrics (100000 CPU period base per core scaling)
        cpu_quota = cpu * 100000
        
        # Provision the container environment seamlessly bypassing overlay lock limits
        container = docker_client.containers.run(
            image="ubuntu:22.04",
            name=clean_name,
            detach=True,
            tty=True,
            stdin_open=True,
            hostname=clean_name,
            mem_limit=ram,
            cpu_period=100000,
            cpu_quota=cpu_quota,
            ports={'22/tcp': vps_ssh_port},
            labels={
                "owner_id": str(owner.id),
                "disk_quota": disk,
                "ssh_port": str(vps_ssh_port)
            },
            command=f"/bin/bash -c 'apt-get update && apt-get install -y openssh-server && sed -i \"s/#PermitRootLogin prohibit-password/PermitRootLogin yes/\" /etc/ssh/sshd_config && echo \"root:{root_password}\" | chpasswd && service ssh start && bash'"
        )

        # Main Public Response Channel Card
        public_embed = discord.Embed(title="🌐 New Virtual Server Deployed", color=discord.Color.blue())
        public_embed.add_field(name="Instance", value=f"`{clean_name}`", inline=True)
        public_embed.add_field(name="Assigned Owner", value=owner.mention, inline=True)
        public_embed.add_field(name="Specs Allocated", value=f"💾 RAM: `{ram}` | ⚙️ CPU Cores: `{cpu}` | 🗄️ Disk: `{disk}`", inline=False)
        public_embed.set_footer(text="Credentials and connection links have been securely DMed to the owner!")
        await interaction.followup.send(embed=public_embed)

        # Private Owner Credentials DM Card
        dm_embed = discord.Embed(title="🔑 Your VPS Private Configuration Panel", color=discord.Color.green())
        dm_embed.add_field(name="VPS ID/Name", value=f"`{clean_name}`", inline=False)
        dm_embed.add_field(name="Host IP Address", value=f"`{server_public_ip}`", inline=True)
        dm_embed.add_field(name="SSH Connection Port", value=f"`{vps_ssh_port}`", inline=True)
        dm_embed.add_field(name="Default Login User", value="`root`", inline=True)
        dm_embed.add_field(name="Root Account Password", value=f"`{root_password}`", inline=True)
        dm_embed.set_footer(text="Interact with the terminal macro keys below to quickly copy connectivity parameters.")

        view = ConnectionMenu(server_public_ip, vps_ssh_port, root_password)
        await owner.send(embed=dm_embed, view=view)

    except Exception as e:
        await interaction.followup.send(f"❌ Automation deployment configuration failure: `{str(e)}`", ephemeral=True)


# 2. REGEN SSH COMMAND
@bot.tree.command(name="regen_ssh", description="Reset root credentials and regenerate connectivity layout.")
@app_commands.describe(name="Target hostname/identifier")
async def regen_ssh(interaction: discord.Interaction, name: str):
    await interaction.response.defer(ephemeral=True)
    try:
        container = docker_client.containers.get(name)
        owner_id = container.labels.get("owner_id")
        ssh_port = container.labels.get("ssh_port")
        
        if str(interaction.user.id) != owner_id and not interaction.user.guild_permissions.administrator:
            await interaction.followup.send("❌ Access Denied: You are not recognized as the instance owner.", ephemeral=True)
            return

        new_password = generate_password()
        server_public_ip = "YOUR_SERVER_PUBLIC_IP"

        # Dynamically overwrite root target within active container context
        container.exec_run(f"/bin/bash -c 'echo \"root:{new_password}\" | chpasswd && service ssh restart'")

        dm_embed = discord.Embed(title="🔄 SSH Account Credentials Regenerated Successfully", color=discord.Color.orange())
        dm_embed.add_field(name="VPS ID Target", value=f"`{name}`", inline=False)
        dm_embed.add_field(name="New Root Password", value=f"`{new_password}`", inline=False)

        view = ConnectionMenu(server_public_ip, ssh_port, new_password)
        await interaction.user.send(embed=dm_embed, view=view)
        await interaction.followup.send("✅ Credentials regenerated. View the updated details inside your private DM thread.", ephemeral=True)

    except Exception as e:
        await interaction.followup.send(f"❌ Critical system rotation issue encountered: `{str(e)}`", ephemeral=True)


# 3. DELETE COMMAND
@bot.tree.command(name="delete_vps", description="Purge and terminate a running virtual machine container context.")
@app_commands.describe(name="Target hostname/identifier to delete")
async def delete_vps(interaction: discord.Interaction, name: str):
    await interaction.response.defer()
    
    if not interaction.user.guild_permissions.administrator:
        await interaction.followup.send("❌ Error: Restricted execution. Administrative elevated access rights are required.", ephemeral=True)
        return

    try:
        container = docker_client.containers.get(name)
        container.stop()
        container.remove()
        await interaction.followup.send(f"🗑️ VPS environment instance `{name}` has been successfully terminated and cleaned from memory.")
    except Exception as e:
        await interaction.followup.send(f"❌ Failed to drop targeted node container instance: `{str(e)}`")


# 4. HELP COMMAND
@bot.tree.command(name="help", description="Review accessible terminal sub-system control routines.")
async def help_cmd(interaction: discord.Interaction):
    embed = discord.Embed(title="⚙️ Virtualization Orchestrator Help Menu", color=discord.Color.purple())
    embed.add_field(name="`/create_vps [name] [ram] [cpu] [disk] [@owner]`", value="Deploys an application-bounded environment and forwards remote credentials via direct message securely.", inline=False)
    embed.add_field(name="`/regen_ssh [name]`", value="Resets access passwords, restarts SSH daemons, and sends refreshed copy-paste configurations.", inline=False)
    embed.add_field(name="`/delete_vps [name]`", value="🛑 *Admin Only.* Terminates container structures and flushes active localized file volumes.", inline=False)
    embed.add_field(name="`/help`", value="Brings up this interface overview card block.", inline=False)
    await interaction.response.send_message(embed=embed)

# Replace with your true token string
BOT_TOKEN = "YOUR_DISCORD_BOT_TOKEN_HERE"
      bot.run(BOT_TOKEN)
