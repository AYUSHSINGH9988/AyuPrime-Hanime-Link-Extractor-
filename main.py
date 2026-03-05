import os
import json
import subprocess
import requests
import re
import uuid
import urllib.request
import zipfile
import stat
import asyncio  
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pyrogram import Client, filters, enums
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from motor.motor_asyncio import AsyncIOMotorClient

# 🔥 THE MASTER FIX FOR ASYNC LOOP 🔥
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

# ==========================================
# 🛡️ PROXY & YOUTUBE BROWSER HEADERS
# ==========================================
PROXY_URL = "http://dLAG1sTQ6:qKE6euVsA@138.249.190.195:62694"
PROXIES_DICT = {
    "http": PROXY_URL,
    "https": PROXY_URL
}

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
YT_HEADERS = (
    f'--user-agent "{USER_AGENT}" '
    f'--add-header "Accept-Language:en-US,en;q=0.9" '
    f'--add-header "Sec-Fetch-Mode:navigate" '
    f'--add-header "Sec-Fetch-Site:cross-site"'
)

# ==========================================
# 🌐 HEALTH CHECK FIX 
# ==========================================
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b"M3U8 Link Extractor Bot is ALIVE with Queue System!")

def keep_alive():
    port = int(os.environ.get("PORT", 8000))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

# ==========================================
# 🤖 BOT & MONGODB CONFIGURATION 
# ==========================================
API_ID = 33675350
API_HASH = "2f97c845b067a750c9f36fec497acf97"
BOT_TOKEN = "8798570619:AAE0Bz4umU7JMDn61AcssHwntSRyjNjzu-Q"  

MONGO_URL = "mongodb+srv://salonisingh6265_db_user:U50ONNZZFUbh0iQI@cluster0.41mb27f.mongodb.net/?appName=Cluster0"
mongo_client = AsyncIOMotorClient(MONGO_URL)
db = mongo_client["UniversalBotDB"]
link_cache = db["M3U8_Links"]

app = Client("link_extractor_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

SUPPORTED_SITES = ["hanime.tv", "hstream.moe", "oppai.stream", "hentaihaven.com", "ohentai.org", "hentaimama.io"]
PENDING_RESULTS = {}
task_queue = asyncio.Queue()

# ==========================================
# 🌟 SMART SCANNERS & PARSERS
# ==========================================
async def get_video_info_async(url):
    try:
        cookie_flag = '--cookies cookies.txt' if os.path.exists('cookies.txt') else ''
        cmd = f'yt-dlp --proxy "{PROXY_URL}" {cookie_flag} {YT_HEADERS} -j "{url}"'
        proc = await asyncio.create_subprocess_shell(cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, _ = await proc.communicate()
        if proc.returncode != 0: return None, None, None
        
        data = json.loads(stdout.decode('utf-8'))
        title = "".join([c for c in data.get('title', 'Extracted_Video') if c.isalnum() or c==' ']).strip()
        thumbnail = data.get('thumbnail', '')
        m3u8_link = data.get('url', '')
        return title, thumbnail, m3u8_link
    except: return None, None, None

async def parse_episodes_from_url_silent(url):
    episodes_to_download = []
    try:
        if "hanime.tv" in url:
            slug = url.split('/hentai/')[-1].split('?')[0]
            api_url = f"https://hanime.tv/api/v8/video?id={slug}"
            r = requests.get(api_url, headers={'User-Agent': 'Mozilla/5.0'}, proxies=PROXIES_DICT)
            if r.status_code == 200:
                franchise_videos = r.json().get('hentai_franchise_hentai_videos', [{'slug': slug}])
                for vid in franchise_videos: episodes_to_download.append({'slug': vid['slug']})
        else:
            match = re.search(r'(-|_)(\d+)/?$', url)
            if match:
                base_url = url[:match.start(1)] 
                sep = match.group(1) 
                headers = {'User-Agent': 'Mozilla/5.0'}
                for i in range(1, 20): 
                    test_url = f"{base_url}{sep}{i}"
                    try:
                        r = requests.get(test_url, headers=headers, timeout=5, proxies=PROXIES_DICT)
                        if r.status_code == 200: episodes_to_download.append({'url': test_url, 'title': f"Auto-Discovered Ep {i}"})
                        else: break 
                    except: break
            
            if len(episodes_to_download) <= 1:
                cookie_flag = '--cookies cookies.txt' if os.path.exists('cookies.txt') else ''
                cmd = f'yt-dlp --proxy "{PROXY_URL}" {cookie_flag} {YT_HEADERS} -j --flat-playlist "{url}"'
                proc = await asyncio.create_subprocess_shell(cmd, stdout=asyncio.subprocess.PIPE)
                stdout, _ = await proc.communicate()
                lines = stdout.decode('utf-8').strip().split('\n')
                for line in lines:
                    if not line.strip(): continue
                    try:
                        data = json.loads(line)
                        ep_url = data.get('url') or data.get('webpage_url')
                        if ep_url: episodes_to_download.append({'url': ep_url, 'title': data.get('title', 'Episode')})
                    except: pass
                
                if not episodes_to_download:
                    episodes_to_download = [{'url': url, 'title': 'Single Episode'}]
    except: pass
    return episodes_to_download

# Centralized MongoDB & Extraction Logic
async def get_m3u8(url):
    cached = await link_cache.find_one({"url": url})
    if cached:
        return cached["title"], cached.get("thumbnail", ""), cached["m3u8_link"], True
    
    title, thumb, m3u8 = await get_video_info_async(url)
    if m3u8 and m3u8.startswith("http"):
        await link_cache.insert_one({"url": url, "title": title, "m3u8_link": m3u8, "thumbnail": thumb})
    return title, thumb, m3u8, False
# ==========================================
# 🚦 SILENT QUEUE WORKER 
# ==========================================
async def queue_worker():
    while True:
        q_data = await task_queue.get()
        urls = q_data['urls']
        action = q_data['action']
        original_msg = q_data['original_msg']

        try:
            for s_idx, series_url in enumerate(urls):
                episodes = await parse_episodes_from_url_silent(series_url)
                if not episodes: continue
                
                count = len(episodes)
                final_text = f"🎬 **Queue Complete - {'Direct Links' if action == 'dir' else 'Uploader Format'} ({count} Episodes)**\n\n"
                
                for ep_idx, vid in enumerate(episodes):
                    vid_url = vid.get('url') or f"https://hanime.tv/videos/hentai/{vid.get('slug')}"
                    title, thumb, m3u8_link, is_cached = await get_m3u8(vid_url)
                    
                    if m3u8_link:
                        if action == "dir":
                            final_text += f"🎬 {title}\n`{m3u8_link}`\n\n"
                        else:
                            # 🔥 NEW UPLOADER FORMAT INJECTED
                            final_text += f"🎬 {title}\n`{m3u8_link} -n {title}.mp4`\n\n"
                    
                    # 🔥 5 SECOND SLEEP (Only if not in DB)
                    if not is_cached and ep_idx < len(episodes) - 1:
                        await asyncio.sleep(5)
                
                # Send result for this series
                if len(final_text) > 4000:
                    file_name = f"Queue_Series_{s_idx+1}.txt"
                    with open(file_name, "w", encoding="utf-8") as f: f.write(final_text.replace("`", ""))
                    await original_msg.reply_document(document=file_name, caption=f"✅ **Series {s_idx+1} Extracted ({count} eps)!**")
                    os.remove(file_name)
                else:
                    await original_msg.reply_text(final_text)

                # 🔥 10 SECOND SLEEP BETWEEN SERIES
                if s_idx < len(urls) - 1:
                    await asyncio.sleep(10)
                    
            await original_msg.reply_text("✅ **All Queued Links Successfully Extracted!**")
        except Exception as e:
            print(f"Queue Error: {e}")
        finally:
            task_queue.task_done()

# ==========================================
# 🤖 BOT COMMANDS & HANDLERS
# ==========================================
@app.on_message(filters.command("start"))
async def start(client, message):
    await message.reply_text(
        "✨ **Welcome to the Link Extractor Bot!** ✨\n\n"
        "**Commands:**\n"
        "👉 Send any link directly for a **Single Video**.\n"
        "👉 Use `/batch <link>` for **Playlist/Series** extraction.\n"
        "👉 Use `/queue <link1> <link2>...` to silently extract multiple series."
    )

@app.on_message(filters.command("queue"))
async def handle_queue(client, message: Message):
    raw_text = message.text.replace("/queue", "").strip()
    if not raw_text: return await message.reply_text("❌ **Oops! URLs missing.**\nFormat: `/queue link1 link2`")
    
    urls = [u.strip() for u in re.split(r'\s+', raw_text) if u.startswith("http")]
    if not urls: return await message.reply_text("❌ **No valid HTTP links found.**")

    req_id = str(uuid.uuid4())[:8]
    PENDING_RESULTS[req_id] = {"type": "queue", "urls": urls, "original_msg": message}
    
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔗 Direct Links", callback_data=f"dir_{req_id}")],
        [InlineKeyboardButton("📥 Uploader Format (-n)", callback_data=f"upl_{req_id}")]
    ])
    await message.reply_text(f"🚦 **Queue Ready! ({len(urls)} Links)**\nKaunsa format chahiye?", reply_markup=buttons)

@app.on_message(filters.command("batch"))
async def handle_batch(client, message: Message):
    if len(message.command) < 2: return await message.reply_text("❌ **Format:** `/batch <link>`")
    url = message.command[1]
    if not any(site in url for site in SUPPORTED_SITES): return

    status = await message.reply_text("⏳ **Finding all episodes...** 🕵️‍♂️")
    episodes = await parse_episodes_from_url_silent(url)
    
    if episodes:
        req_id = str(uuid.uuid4())[:8]
        PENDING_RESULTS[req_id] = {"type": "batch", "episodes": episodes, "original_msg": message, "status_msg": status}
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔗 Direct Links", callback_data=f"dir_{req_id}")],
            [InlineKeyboardButton("📥 Uploader Format (-n)", callback_data=f"upl_{req_id}")]
        ])
        await status.edit_text(f"✅ **Extracted {len(episodes)} Episodes!**\nKaunsa format chahiye?", reply_markup=buttons)
    else: await status.edit_text("❌ **No multiple episodes found.**")

@app.on_message(filters.text & ~filters.command(["start", "batch", "queue"]))
async def handle_message(client, message: Message):
    url = message.text
    if not any(site in url for site in SUPPORTED_SITES): return

    status = await message.reply_text("⏳ **Checking & Extracting...** 🕵️‍♂️")
    title, thumb, m3u8_link, is_cached = await get_m3u8(url)
    
    if m3u8_link:
        req_id = str(uuid.uuid4())[:8]
        PENDING_RESULTS[req_id] = {"type": "single", "title": title, "m3u8": m3u8_link, "thumb": thumb}
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔗 Direct Link", callback_data=f"dir_{req_id}")],
            [InlineKeyboardButton("📥 Uploader Format (-n)", callback_data=f"upl_{req_id}")]
        ])
        if is_cached: await status.edit_text("⚡ **Link Found in Database!**")
        await status.edit_text(f"🎬 **Title:** `{title}`\n\nKaunsa format chahiye?", reply_markup=buttons)
    else: await status.edit_text("❌ **Extraction Failed.**")

@app.on_callback_query()
async def callback_handler(client, query):
    action, req_id = query.data.split("_")
    if req_id not in PENDING_RESULTS: return await query.answer("❌ Link Expired!", show_alert=True)
        
    data = PENDING_RESULTS[req_id]
    
    # 🚦 QUEUE HANDLING
    if data["type"] == "queue":
        await query.message.edit_text("✅ **Links added to Background Queue!** Bot will process them silently. 🤫")
        await task_queue.put({"urls": data["urls"], "action": action, "original_msg": data["original_msg"]})
        del PENDING_RESULTS[req_id]
        return

    await query.message.edit_text("⏳ **Generating your format...**")
    
    # 🎬 SINGLE HANDLING
    if data["type"] == "single":
        title, m3u8, thumb = data["title"], data["m3u8"], data["thumb"]
        if action == "dir": text = f"🎬 **Title:** `{title}`\n\n🔗 **Direct Link:**\n`{m3u8}`"
        else: text = f"🎬 **Title:** `{title}`\n\n📥 **Uploader Format:**\n`{m3u8} -n {title}.mp4`"
            
        if thumb:
            await query.message.reply_photo(photo=thumb, caption=text)
            await query.message.delete()
        else: await query.message.edit_text(text)
            
    # 📚 BATCH HANDLING
    elif data["type"] == "batch":
        episodes = data["episodes"]
        count = len(episodes)
        final_text = f"🎬 **Batch Complete - {'Direct Links' if action == 'dir' else 'Uploader Format'} ({count} Episodes)**\n\n"
        
        for ep_idx, vid in enumerate(episodes):
            vid_url = vid.get('url') or f"https://hanime.tv/videos/hentai/{vid.get('slug')}"
            ep_title, _, ep_m3u8, is_cached = await get_m3u8(vid_url)
            
            if ep_m3u8:
                if action == "dir": final_text += f"🎬 {ep_title}\n`{ep_m3u8}`\n\n"
                else: final_text += f"🎬 {ep_title}\n`{ep_m3u8} -n {ep_title}.mp4`\n\n"
            
            if not is_cached and ep_idx < len(episodes) - 1: await asyncio.sleep(5)
                
        if len(final_text) > 4000:
            file_name = "Batch_Links.txt"
            with open(file_name, "w", encoding="utf-8") as f: f.write(final_text.replace("`", "")) 
            await query.message.reply_document(document=file_name, caption=f"✅ **Extracted {count} episodes!**")
            os.remove(file_name)
            await query.message.delete()
        else: await query.message.edit_text(final_text)
            
    del PENDING_RESULTS[req_id]

if __name__ == "__main__":
    print("🤖 Extractor Bot with Silent Queue is Alive...")
    keep_alive()
    loop.create_task(queue_worker())
    app.run()
