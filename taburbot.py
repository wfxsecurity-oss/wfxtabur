import discord
from discord.ext import commands
import json
import os
import time
from datetime import datetime
import redis

# --- Redis Veritabanı Bağlantısı ---
REDIS_URL = os.environ.get("REDIS_URL")

if REDIS_URL:
    r = redis.Redis.from_url(REDIS_URL, decode_responses=True)
else:
    r = redis.Redis(host="localhost", port=6379, db=0, decode_responses=True)

def veri_yukle():
    data = r.get("bot_verileri")
    if not data:
        varsayilan = {"users": {}, "records": {}}
        veri_kaydet(varsayilan)
        return varsayilan
    return json.loads(data)

def veri_kaydet(data):
    r.set("bot_verileri", json.dumps(data, ensure_ascii=False))

# --- Gerekli Tanımlamalar ---
LOG_CHANNEL_ID = 1538484766129655818
YETKILI_PUAN = 1529948882837049486     
YETKILI_SIFIRLA = 1398636525910102076  
GUILD_ID = 1398636278001434634  # Sunucu ID'si

RANKS = {
    1415343719300993045: 'OF-6 Tuğgeneral',
    1415343720479461487: 'OF-7 Tümgeneral',
    1415343721402208346: 'OF-8 Korgeneral',
    1415343721423175770: 'OF-9 Orgeneral',
    1529208424016117830: 'Büyük Konsey',
    1529208202477047959: 'Ankara Heyeti',
    1529208215420539004: 'Ordu Komutanı',
    1529208057081364590: 'Askeri Kurultay'
}

RANK_CONFIG = [
    {"role_id": 1415343719300993045, "name": "OF6", "tenzil": 5, "terfi_yok_ust": 9, "bir_x_terfi_ust": 18},
    {"role_id": 1415343720479461487, "name": "OF7", "tenzil": 5.5, "terfi_yok_ust": 10, "bir_x_terfi_ust": 20},
    {"role_id": 1415343721402208346, "name": "OF8", "tenzil": 6, "terfi_yok_ust": 11, "bir_x_terfi_ust": 22},
    {"role_id": 1415343721423175770, "name": "OF9", "tenzil": 7, "terfi_yok_ust": 12, "bir_x_terfi_ust": 24},
    {"role_id": 1529208424016117830, "name": "Büyük Konsey", "tenzil": 8, "terfi_yok_ust": 12, "bir_x_terfi_ust": 24},
    {"role_id": 1529208202477047959, "name": "Ankara Heyeti", "tenzil": 8, "terfi_yok_ust": 14, "bir_x_terfi_ust": 26},
    {"role_id": 1529208215420539004, "name": "Ordu Komutanı", "tenzil": 8, "terfi_yok_ust": 14, "bir_x_terfi_ust": 28},
    {"role_id": 1529208057081364590, "name": "Askeri Kurultay", "tenzil": 12, "two_tier": True},
]

def get_rank_status(role_id: int, points: float):
    cfg = next((c for c in RANK_CONFIG if c["role_id"] == role_id), None)
    if not cfg:
        return None
    if cfg.get("two_tier"):
        return "Tenzil" if points < cfg["tenzil"] else "Terfi yok, Tenzil yok"
    if points < cfg["tenzil"]:
        return "Tenzil"
    if points < cfg["terfi_yok_ust"]:
        return "Terfi yok, Tenzil yok"
    if points < cfg["bir_x_terfi_ust"]:
        return "1x Terfi"
    return "2x Terfi"

# --- Bot Sınıfı Yapılandırması ---
class CustomBot(commands.Bot):
    async def setup_hook(self):
        # 1. Komut Gruplarını Ekle
        toplu_group.add_command(toplu_puan_group)
        self.tree.add_command(puan_group)
        self.tree.add_command(tutanak_group)
        self.tree.add_command(toplu_group)
        self.tree.add_command(sayim_yap) # /sayım-yap komutunu ekle

        # 2. Belirtilen Sunucuya Senkronize Et
        guild = discord.Object(id=GUILD_ID)
        self.tree.copy_global_to(guild=guild)
        synced = await self.tree.sync(guild=guild)
        print(f"Slash komutları anında senkronize edildi: {len(synced)} komut.")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = CustomBot(command_prefix="!", intents=intents)

# --- Log Gönderme Fonksiyonu ---
async def send_log(title, actor, target_id, reason, color):
    channel = bot.get_channel(LOG_CHANNEL_ID)
    if not channel:
        return
    
    embed = discord.Embed(title=title, color=color)
    embed.add_field(name="Tarih", value=f"<t:{int(time.time())}:F>", inline=False)
    
    actor_text = actor.mention if actor else "Bilinmiyor"
    target_text = f"<@{target_id}>" if target_id else "Toplu İşlem"
    
    embed.add_field(name="İşlemi Yapan", value=actor_text, inline=True)
    embed.add_field(name="İşlem Uygulanan", value=target_text, inline=True)
    embed.add_field(name="Sebep", value=reason, inline=False)
    
    await channel.send(embed=embed)

# --- Yetki Kontrolü ---
def check_puan_yetki(interaction: discord.Interaction):
    if interaction.user.guild_permissions.administrator: 
        return True
    role_ids = [role.id for role in interaction.user.roles]
    return YETKILI_PUAN in role_ids

def check_sifirla_yetki(interaction: discord.Interaction):
    role_ids = [role.id for role in interaction.user.roles]
    return YETKILI_SIFIRLA in role_ids

@bot.event
async def on_ready():
    print(f'{bot.user} olarak giriş yapıldı! Bot ve Redis veritabanı aktif.')

# ================================
# /PUAN GRUBU
# ================================
puan_group = discord.app_commands.Group(name="puan", description="Puan işlemleri")

@puan_group.command(name="ekle", description="Personele puan ekler")
@discord.app_commands.describe(member="Puan eklenecek personel", miktar="Eklenecek puan miktarı", sebep="İşlem sebebi")
async def puan_ekle(interaction: discord.Interaction, member: discord.Member, miktar: int, sebep: str = "Belirtilmedi"):
    if not check_puan_yetki(interaction):
        return await interaction.response.send_message("Bu komutu kullanmak için gerekli role sahip değilsin.", ephemeral=True)
    if miktar <= 0:
        return await interaction.response.send_message("Lütfen 0'dan büyük bir puan girin.", ephemeral=True)

    data = veri_yukle()
    user_id_str = str(member.id)
    
    if user_id_str not in data["users"]:
        data["users"][user_id_str] = 0
    
    data["users"][user_id_str] += miktar
    veri_kaydet(data)

    await interaction.response.send_message(f"{member.mention} kişisine başarıyla **{miktar}** puan eklendi.")
    await send_log("🟢 Puan Eklendi", interaction.user, member.id, sebep, discord.Color.green())

@puan_group.command(name="sil", description="Personele puan siler")
@discord.app_commands.describe(member="Puanı silinecek personel", miktar="Silinecek puan miktarı", sebep="İşlem sebebi")
async def puan_sil(interaction: discord.Interaction, member: discord.Member, miktar: int, sebep: str = "Belirtilmedi"):
    if not check_puan_yetki(interaction):
        return await interaction.response.send_message("Bu komutu kullanmak için gerekli role sahip değilsin.", ephemeral=True)
    if miktar <= 0:
        return await interaction.response.send_message("Lütfen 0'dan büyük bir puan girin.", ephemeral=True)

    data = veri_yukle()
    user_id_str = str(member.id)
    
    if user_id_str not in data["users"] or data["users"][user_id_str] <= 0:
        return await interaction.response.send_message("Bu kullanıcının sistemde puanı bulunmuyor.", ephemeral=True)

    if data["users"][user_id_str] >= miktar:
        data["users"][user_id_str] -= miktar
    else:
        data["users"][user_id_str] = 0
    
    veri_kaydet(data)

    await interaction.response.send_message(f"{member.mention} kişisinden başarıyla **{miktar}** puan silindi.")
    await send_log("🔴 Puan Silindi", interaction.user, member.id, sebep, discord.Color.red())

@puan_group.command(name="sorgu", description="Personelin puanını sorgular")
@discord.app_commands.describe(member="Puanı sorgulanacak personel (Boş bırakırsanız kendiniz olursunuz)")
async def puan_sorgu(interaction: discord.Interaction, member: discord.Member = None):
    target = member or interaction.user
    data = veri_yukle()
    points = data["users"].get(str(target.id), 0)
    
    await interaction.response.send_message(f"{target.mention} adlı kullanıcının güncel puanı: **{points}**")


# ================================
# /TUTANAK GRUBU
# ================================
tutanak_group = discord.app_commands.Group(name="tutanak", description="Tutanak işlemleri")

@tutanak_group.command(name="ekle", description="Personele tutanak ekler")
@discord.app_commands.describe(member="Tutanağın tutulacağı personel", sebep="Tutanak sebebi")
async def tutanak_ekle(interaction: discord.Interaction, member: discord.Member, sebep: str):
    if not check_puan_yetki(interaction):
        return await interaction.response.send_message("Tutanak eklemek için yetkiniz yok.", ephemeral=True)

    data = veri_yukle()
    record_id = str(len(data["records"]) + 1)
    tarih = datetime.now().strftime("%d.%m.%Y %H:%M")

    data["records"][record_id] = {
        "user_id": str(member.id),
        "author_id": str(interaction.user.id),
        "reason": sebep,
        "date": tarih
    }
    veri_kaydet(data)

    await interaction.response.send_message(f"{member.mention} kişisine başarıyla tutanak eklendi. (ID: {record_id})")
    await send_log("📄 Tutanak Eklendi", interaction.user, member.id, sebep, discord.Color.orange())

@tutanak_group.command(name="görüntüle", description="Personelin tutanaklarını görüntüler")
@discord.app_commands.describe(member="Tutanakları gösterilecek personel")
async def tutanak_goruntule(interaction: discord.Interaction, member: discord.Member = None):
    target = member or interaction.user
    data = veri_yukle()
    
    user_records = {rid: rdata for rid, rdata in data["records"].items() if rdata["user_id"] == str(target.id)}

    if not user_records:
        return await interaction.response.send_message(f"{target.mention} kişisine ait herhangi bir tutanak bulunamadı.", ephemeral=True)

    embed = discord.Embed(title=f"{target.display_name} - Tutanak Kayıtları", color=discord.Color.dark_theme())
    for rid, rdata in user_records.items():
        embed.add_field(
            name=f"Tutanak ID: {rid} | Tarih: {rdata['date']}",
            value=f"**Tutanak Tutan:** <@{rdata['author_id']}>\n**Sebep:** {rdata['reason']}",
            inline=False
        )
    await interaction.response.send_message(embed=embed)

@tutanak_group.command(name="sil", description="ID'ye göre tutanak siler")
@discord.app_commands.describe(record_id="Silinecek tutanağın ID numarası")
async def tutanak_sil(interaction: discord.Interaction, record_id: int):
    if not check_puan_yetki(interaction):
        return await interaction.response.send_message("Tutanak silmek için yetkiniz yok.", ephemeral=True)

    data = veri_yukle()
    rid_str = str(record_id)

    if rid_str not in data["records"]:
        return await interaction.response.send_message("Belirtilen ID ile eşleşen bir tutanak bulunamadı.", ephemeral=True)

    record = data["records"].pop(rid_str)
    veri_kaydet(data)

    await interaction.response.send_message(f"**{record_id}** ID'li tutanak başarıyla silindi.")
    await send_log("🗑️ Tutanak Silindi", interaction.user, int(record["user_id"]), f"Silinen Tutanak ID: {record_id} (Eski Sebep: {record['reason']})", discord.Color.red())


# ================================
# /TOPLU GRUBU
# ================================
toplu_group = discord.app_commands.Group(name="toplu", description="Toplu işlemler")
toplu_puan_group = discord.app_commands.Group(name="puan", description="Toplu puan işlemleri")

@toplu_puan_group.command(name="sıfırla", description="Herkesin puanını sıfırlar")
async def toplu_sifirla(interaction: discord.Interaction):
    if not check_sifirla_yetki(interaction):
        return await interaction.response.send_message("Bu komutu kullanmak için yetkiniz yok.", ephemeral=True)

    data = veri_yukle()
    data["users"] = {}
    veri_kaydet(data)

    await interaction.response.send_message("Sunucudaki herkesin puanı başarıyla sıfırlandı.")
    await send_log("🔄 Toplu Puan Sıfırlama", interaction.user, None, "Tüm personelin puanları sıfırlandı.", discord.Color.purple())

@toplu_puan_group.command(name="sorgu", description="Tüm personelin puan dökümünü çıkarır")
async def toplu_sorgu(interaction: discord.Interaction):
    await interaction.response.defer()
    
    data = veri_yukle()
    users = data["users"]

    if not users:
        return await interaction.followup.send("Sistemde puanı bulunan kimse yok.")

    sorted_users = sorted(users.items(), key=lambda x: x[1], reverse=True)

    dokum = ""
    for user_id_str, points in sorted_users:
        if points <= 0:
            continue
        
        user_id = int(user_id_str)
        member = interaction.guild.get_member(user_id)
        role_name = "Sivil / Rütbe Yok"

        if member:
            member_role_ids = [r.id for r in member.roles]
            for r_id, r_name in RANKS.items():
                if r_id in member_role_ids:
                    role_name = r_name
                    break
        else:
            role_name = "Ayrılmış Kullanıcı"

        dokum += f"<@{user_id}> | **Rütbe:** {role_name} | **Puan:** {points}\n"

    if not dokum:
        return await interaction.followup.send("Sistemde 0'dan büyük puanı olan kimse yok.")

    chunks = [dokum[i:i+1900] for i in range(0, len(dokum), 1900)]
    for i, chunk in enumerate(chunks):
        embed = discord.Embed(title=f"Toplu Personel Puan Dökümü ({i+1})", description=chunk, color=discord.Color.gold())
        await interaction.followup.send(embed=embed)


# ================================
# /SAYIM-YAP KOMUTU
# ================================
class SayimView(discord.ui.View):
    def __init__(self, guild: discord.Guild, author_id: int):
        super().__init__(timeout=180)
        self.guild = guild
        self.author_id = author_id
        self.page = 0
        self.total_pages = len(RANK_CONFIG)
        self.message: discord.Message | None = None
        self._update_button_states()

    def _update_button_states(self):
        self.prev_button.disabled = self.page == 0
        self.next_button.disabled = self.page >= self.total_pages - 1

    def build_embed(self) -> discord.Embed:
        cfg = RANK_CONFIG[self.page]
        role = self.guild.get_role(cfg["role_id"])
        members = role.members if role else []

        embed = discord.Embed(title=f"Sayım — {cfg['name']}", color=discord.Color.dark_theme())
        embed.set_footer(text=f"Kategori {self.page + 1}/{self.total_pages} — {len(members)} üye")

        if not members:
            embed.description = "Bu rolde üye bulunamadı."
            return embed

        data = veri_yukle()
        sorted_members = sorted(
            members,
            key=lambda m: data["users"].get(str(m.id), 0),
            reverse=True,
        )

        lines = []
        for m in sorted_members:
            points = data["users"].get(str(m.id), 0)
            status = get_rank_status(cfg["role_id"], points)
            lines.append(f"{m.display_name} — **{points}P** — {status}")

        desc = "\n".join(lines)
        if len(desc) > 4000:
            desc = desc[:4000] + "\n..."
        embed.description = desc
        return embed

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            return await interaction.response.send_message(
                "Bu butonları sadece komutu kullanan kişi kullanabilir.", ephemeral=True
            )
        self.page = max(0, self.page - 1)
        self._update_button_states()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            return await interaction.response.send_message(
                "Bu butonları sadece komutu kullanan kişi kullanabilir.", ephemeral=True
            )
        self.page = min(self.total_pages - 1, self.page + 1)
        self._update_button_states()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


@discord.app_commands.command(name="sayım-yap", description="Rütbe rollerine göre sayım yapar ve terfi/tenzil durumunu gösterir")
async def sayim_yap(interaction: discord.Interaction):
    await interaction.response.defer()
    if interaction.guild.chunked is False:
        await interaction.guild.chunk()

    view = SayimView(interaction.guild, interaction.user.id)
    embed = view.build_embed()
    message = await interaction.followup.send(embed=embed, view=view)
    view.message = message


# --- Bot Çalıştırma ---
TOKEN = os.environ.get("DISCORD_TOKEN")

if TOKEN:
    bot.run(TOKEN)
else:
    print("HATA: DISCORD_TOKEN ortam değişkeni bulunamadı! Lütfen Railway Variables kısmına ekleyin.")
