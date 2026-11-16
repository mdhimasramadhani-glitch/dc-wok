import time
import httpx

DISCORD_API_BASE = "https://discord.com/api/v9"

class DiscordRateLimitError(Exception):
    def __init__(self, retry_after: float, detail: str = "Rate limit / Slowmode Discord"):
        self.retry_after = max(5, int(retry_after) + 2)
        self.detail = detail
        super().__init__(detail)

def clean_token(token: str) -> str:
    t = token.strip().strip('"').strip("'")
    if t.lower().startswith("bearer "):
        t = t[7:].strip()
    if t.startswith("Bot "):
        t = t[4:].strip()
    return t

def _headers(token: str) -> dict:
    return {
        'Host': 'discord.com',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:159.0) Gecko/20100101 Firefox/159.0',
        'Accept': '*/*',
        'Accept-Language': 'en-US,en;q=0.9',
        'Content-Type': 'application/json',
        'X-Context-Properties': 'eyJsb2NhdGlvbiI6ImNoYXRfaW5wdXQifQ==',
        'Authorization': clean_token(token),
        'X-Super-Properties': 'eyJvcyI6IldpbmRvd3MiLCJicm93c2VyIjoiRmlyZWZveCIsImRldmljZSI6IiIsImRldmljZV9tb2RlbF9uYW1lIjoiIiwic3lzdGVtX2xvY2FsZSI6ImVuLVVTIiwiaGFzX2NsaWVudF9tb2RzIjpmYWxzZSwiYnJvd3Nlcl91c2VyX2FnZW50IjoiTW96aWxsYS81LjAgKFdpbmRvd3MgTlQgMTAuMDsgV2luNjQ7IHg2NDsgcnY6MTU5LjApIEdlY2tvLzIwMTAwMTAxIEZpcmVmb3gvMTU5LjAiLCJicm93c2VyX3ZlcnNpb24iOiIxNTkuMCIsIm9zX3ZlcnNpb24iOiIxMCIsInJlZmVycmVyIjoiaHR0cHM6Ly93d3cuZ29vZ2xlLmNvbS8iLCJyZWZlcnJpbmdfZG9tYWluIjoid3d3Lmdvb2dsZS5jb20iLCJzZWFyY2hfZW5naW5lIjoiZ29vZ2xlIiwicmVmZXJyZXJfY3VycmVudCI6IiIsInJlZmVycmluZ19kb21haW5fY3VycmVudCI6IiIsInJlbGVhc2VfY2hhbm5lbCI6InN0YWJsZSIsImNsaWVudF9idWlsZF9udW1iZXIiOjY1Mzk0NSwiY2xpZW50X2V2ZW50X3NvdXJjZSI6bnVsbCwiY2xpZW50X2xhdW5jaF9pZCI6Ijg3MjIwNmM0LWViNDItNDUyNi1hMzVlLTE3NWRmNjkzZmRhZCIsImxhdW5jaF9zaWduYXR1cmUiOiI5NjJkZTQwYS0zNzhjLTQyY2YtOGU2Ni1mODMyMTZiZTc1ZjMiLCJjbGllbnRfaGVhcnRiZWF0X3Nlc3Npb25faWQiOiIzN2QzZmVhOC01YTdjLTQ2YzItOWE0MS0zMDc3ZjJkYTFhMjAiLCJjbGllbnRfYXBwX3N0YXRlIjoiZm9jdXNlZCJ9',
        'X-Installation-ID': '1565200606665244765.OMrnIJF-or3X5_0V6V9XQ_BAqlU',
        'X-Discord-Locale': 'en-US',
        'X-Discord-Timezone': 'Asia/Jakarta',
        'X-Debug-Options': 'bugReporterEnabled',
        'Origin': 'https://discord.com',
        'Alt-Used': 'discord.com',
        'Connection': 'keep-alive',
        'Cookie': '__dcfduid=55a458009d5911f1a18021d5abf99da6; __sdcfduid=55a458019d5911f1a18021d5abf99da65da3d7ec06c14133693ab21e5f1a8808465245b05dd02458113f3c9fadd06ca8; __stripe_mid=13a9a830-b21e-4bf2-a4c6-bae7985198f1ddae26; dbind=1677808b-57ed-44b7-af3c-21d12a065351; cf_clearance=CrHHsa6TsElj6gqRmi1fKmIoQroR_G3E62FZoBFWxn0pIx1UV2Ab7ViGSYDUZr8OxCfkJKqbNwn85NZfUv02Lu69RzWaC2jOI8DfVTb1H91NjSixkVIC2lk_7qgqdDkiiEGV7_VtsIh5Jgf2-bc3DgVvaJwtWpXJ38yMmk2gRJx_4hBAijf-rnyd8Ph5bjx5WDUvk2Mrr0aS-RWQXbrGcHt6oNg8v-V5HwniwS4XHH7Gm4IlHDVva-F2lvDCL2js4gYXbQ4u1Hon27-yf8Ff5jX3dHgXGIrGXO94shqjM_exzgZH; _cfuvid=29TyNldsvpAxHqiCTDpwRsYQKiloVuNZ3sbPzIEzLZA-1794754703.6887379-1.0.1.1-Gz0pkW4KvYMjH8g5xvrWOf63DixttnZn2K_Ctsrp8w8',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-origin',
    }

async def fetch_user_profile(token: str) -> dict:
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{DISCORD_API_BASE}/users/@me", headers=_headers(token))
        if r.status_code != 200:
            print(f"[Discord Auth Error] {r.status_code}: {r.text}")
            r.raise_for_status()
        u = r.json()
        avatar = (
            f"https://cdn.discordapp.com/avatars/{u['id']}/{u['avatar']}.png"
            if u.get("avatar") else "https://cdn.discordapp.com/embed/avatars/0.png"
        )
        return {"discord_id": u["id"], "username": u["username"], "avatar_url": avatar}

async def fetch_joined_guilds(token: str) -> list:
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{DISCORD_API_BASE}/users/@me/guilds", headers=_headers(token))
        r.raise_for_status()
        return [{"id": g["id"], "name": g["name"], "icon": g.get("icon")} for g in r.json()]

async def fetch_guild_text_channels(token: str, guild_id: str, guild_name: str = "") -> list:
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{DISCORD_API_BASE}/guilds/{guild_id}/channels", headers=_headers(token))
        if r.status_code == 403:
            # Server komunitas besar membatasi endpoint daftar semua channel untuk member biasa
            return []
        r.raise_for_status()
        return [
            {"id": ch["id"], "name": ch["name"], "guild_name": guild_name}
            for ch in r.json() if ch.get("type") in (0, 5)
        ]

async def fetch_single_channel(token: str, channel_id: str, guild_name: str = "Direct Channel") -> dict:
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{DISCORD_API_BASE}/channels/{channel_id.strip()}", headers=_headers(token))
        r.raise_for_status()
        ch = r.json()
        return {
            "id": ch["id"],
            "name": ch.get("name") or f"channel-{channel_id.strip()}",
            "guild_name": guild_name
        }

async def send_channel_message(token: str, channel_id: str, content: str) -> str:
    payload = {
        "mobile_network_type": "unknown",
        "content": content,
        "nonce": str(int(time.time())),
        "tts": False,
        "flags": 0
    }
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{DISCORD_API_BASE}/channels/{channel_id}/messages",
            headers=_headers(token),
            json=payload
        )
        if r.status_code == 429:
            try:
                data = r.json()
            except Exception:
                data = {}
            retry_after = float(data.get("retry_after", 60))
            msg = data.get("message", "Slowmode / Rate Limit Discord")
            raise DiscordRateLimitError(retry_after, f"{msg} (tunggu {int(retry_after)} detik)")
        r.raise_for_status()
        return r.json()["id"]

async def delete_channel_message(token: str, channel_id: str, message_id: str) -> bool:
    async with httpx.AsyncClient() as client:
        r = await client.delete(
            f"{DISCORD_API_BASE}/channels/{channel_id}/messages/{message_id}",
            headers=_headers(token)
        )
        return r.status_code in (200, 204)