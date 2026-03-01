import os
import json
import subprocess
import requests
import re
import urllib.request
import zipfile
import stat
import asyncio
import uuid
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

# 🔥 THE MASTER FIX FOR PYTHON 3.14 🔥
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

from pyrogram import Client, filters, enums
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

# ==========================================
# 🌐 KOYEB / RENDER HEALTH CHECK FIX 
# ==========================================
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b"Bot is ALIVE as a Pure Link Extractor!")

def keep_alive():
    port = int(os.environ.get("PORT", 8000))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

# ==========================================
# ⚙️ PURE PYTHON DENO AUTO-INSTALLER (Required for Hanime Signatures)
# ==========================================
try:
    deno_dir = os.path.expanduser("~/.deno/bin")
    deno_path = os.path.join(deno_dir, "deno")
    if not os.path.exists(deno_path):
        os.makedirs(deno_dir, exist_ok=True)
        url = "https://github.com/denoland/deno/releases/latest/download/deno-x86_64-unknown-linux-gnu.zip"
        zip_file = os.path.join(deno_dir, "deno.zip")
        urllib.request.urlretrieve(url, zip_file)
        with zipfile.ZipFile(zip_file, 'r') as zip_ref:
            zip_ref.extractall(deno_dir)
        st = os.stat(deno_path)
        os.chmod(deno_path, st.st_mode | stat.S_IEXEC)
        os.remove(zip_file)
    if deno_dir not in os.environ.get("PATH", ""):
        os.environ["PATH"] = f"{deno_dir}:{os.environ.get('PATH', '')}"
except Exception as e: pass

# ==========================================
# 🤖 BOT CONFIGURATION (NO MONGODB!)
# ==========================================
API_ID = 33675350
API_HASH = "2f97c845b067a750c9f36fec497acf97"
BOT_TOKEN = "8798570619:AAE0Bz4umU7JMDn61AcssHwntSRyjNjzu-Q"

app = Client("universal_extractor_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

PENDING_TASKS = {} 

def get_user_id(message: Message):
    if message.from_user: return message.from_user.id
    elif message.sender_chat: return message.sender_chat.id
    return message.chat.id

# ==========================================
# 🌟 ASYNC INFO EXTRACTOR
# ==========================================
async def get_video_info_async(url):
    try:
        cmd = f'yt-dlp -j "{url}"'
        proc = await asyncio.create_subprocess_shell(cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, _ = await proc.communicate()
        
        if not stdout: return None, {}
            
        data = json.loads(stdout.decode('utf-8'))
        title = data.get('title', 'Extracted_Video')
        
        formats_dict = {}
        if 'formats' in data:
            for f in data.get('formats', []):
                height = f.get('height')
                vcodec = f.get('vcodec')
                f_url = f.get('url')
                if height and isinstance(height, int) and vcodec != 'none':
                    formats_dict[height] = f_url
        else:
            formats_dict['default'] = data.get('url', url)
            
        return title, formats_dict
    except Exception as e:
        return None, {}

SUPPORTED_SITES = ["hanime.tv", "hstream.moe", "oppai.stream", "hentaihaven.com", "ohentai.org", "hentaimama.io"]

async def render_playlist_keyboard(message, task_id):
    task = PENDING_TASKS.get(task_id)
    if not task: return
    
    groups = task.get("groups", [])
    selected = task["selected"]
    buttons = []
    
    for i, grp in enumerate(groups):
        prefix = "✅" if i in selected else "❌"
        title = grp['title'][:25] + ".." if len(grp['title']) > 25 else grp['title']
        count = len(grp['episodes'])
        buttons.append([InlineKeyboardButton(f"{prefix} {title} ({count} Eps)", callback_data=f"tgl_{task_id}_{i}")])

    buttons.append([
        InlineKeyboardButton("✅ Select All", callback_data=f"tglall_{task_id}"),
        InlineKeyboardButton("❌ Unselect All", callback_data=f"tglno_{task_id}")
    ])
    buttons.append([InlineKeyboardButton("➡️ Generate Links", callback_data=f"tgldone_{task_id}")])

    total_eps = sum(len(g['episodes']) for g in groups)
    await message.edit_text(
        f"📋 **Playlist Detected!**\n\nFound **{len(groups)} Series** (Total: {total_eps} Episodes).\nSelect the ones you want to extract:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

# ==========================================
# 🤖 BOT COMMANDS
# ==========================================
@app.on_message(filters.command("start"))
async def start(client, message):
    await message.reply_text(
        "✨ **Universal Link Extractor is Live!**\n\n"
        "**Features:**\n"
        "👉 Bhejo direct link (ya `/dl <link>`) to get direct `.m3u8` URLs.\n"
        "👉 Bhejo `/batch <playlist>` to extract all links into a `.txt` file."
    )

@app.on_message((filters.text | filters.command("dl")) & ~filters.command(["start", "batch"]))
async def handle_message(client, message: Message):
    if message.command and message.command[0] == "dl":
        if len(message.command) < 2: return await message.reply_text("❌ **Format:** `/dl <link>`")
        url = message.text.split(maxsplit=1)[1].strip()
    else:
        url = message.text.strip()
        if message.chat.type != enums.ChatType.PRIVATE and not url.startswith("http"): return
            
    if not url.startswith("http"): return 

    status = await message.reply_text("⏳ **Extracting Direct Links...** 🕵️‍♂️")
    
    title, formats = await get_video_info_async(url)
    
    if title and formats:
        msg = f"🎬 **{title}**\n\n"
        
        # Sort qualities descending (e.g., 1080, 720)
        qualities = [k for k in formats.keys() if isinstance(k, int)]
        qualities.sort(reverse=True)
        
        for q in qualities:
            msg += f"🎥 **{q}p:**\n`{formats[q]}`\n\n"
            
        if 'default' in formats and not qualities:
            msg += f"🔗 **Direct Link:**\n`{formats['default']}`\n\n"
            
        if len(msg) > 4000:
            with open("direct_links.txt", "w", encoding="utf-8") as f: f.write(msg.replace('`', '').replace('**', ''))
            await message.reply_document("direct_links.txt", caption=f"🎬 **{title}**")
            os.remove("direct_links.txt")
            await status.delete()
        else:
            await status.edit_text(msg)
    else: 
        await status.edit_text("❌ **Extraction Failed.**\nShayad link expire ho gaya hai ya site supported nahi hai.")

@app.on_message(filters.command("batch"))
async def handle_batch(client, message: Message):
    raw_text = message.text.replace("/batch", "").strip()
    if not raw_text: return await message.reply_text("❌ **Oops! URL missing.**")
    urls = [u for u in raw_text.split() if u.startswith("http")]
    if not urls: return await message.reply_text("❌ **No valid HTTP links found.**")

    status = await message.reply_text("⏳ **Scanning Playlist...** 🕵️‍♂️")

    try:
        url = urls[0]
        
        # SCENARIO: HANIME CUSTOM PLAYLISTS & CHANNELS
        if "hanime.tv" in url and ("playlist_id=" in url or "/channels/" in url or "/playlists/" in url):
            headers = {'User-Agent': 'Mozilla/5.0'}
            r = requests.get(url, headers=headers)
            groups_dict = {}
            matches = re.findall(r'"name":"([^"]+)"\s*,\s*"slug":"([a-z0-9\-]+)"', r.text)
            
            for title, slug in matches:
                if len(slug) < 4 or ("-" not in slug and not any(char.isdigit() for char in slug)): continue
                ep_url = f"https://hanime.tv/videos/hentai/{slug}"
                base_match = re.match(r'^(.*?)(?:-\d+)?$', slug)
                base_slug = base_match.group(1) if base_match else slug
                
                if base_slug not in groups_dict:
                    clean_title = re.sub(r'\s*\d+$', '', title).strip()
                    groups_dict[base_slug] = {'title': clean_title, 'episodes': []}
                    
                if not any(e['url'] == ep_url for e in groups_dict[base_slug]['episodes']):
                    groups_dict[base_slug]['episodes'].append({'url': ep_url, 'title': title})

            groups_list = list(groups_dict.values())
            if groups_list:
                task_id = str(uuid.uuid4())[:8]
                PENDING_TASKS[task_id] = {"groups": groups_list, "selected": list(range(len(groups_list))), "user_id": get_user_id(message)}
                await render_playlist_keyboard(status, task_id)
            else: await status.edit_text("❌ **No videos found in this Playlist/Channel.**")
            return

        # SCENARIO: NORMAL HANIME SERIES
        elif len(urls) == 1 and "hanime.tv" in url:
            slug = url.split('/hentai/')[-1].split('?')[0]
            api_url = f"https://hanime.tv/api/v8/video?id={slug}"
            r = requests.get(api_url, headers={'User-Agent': 'Mozilla/5.0'})
            if r.status_code == 200:
                franchise_videos = r.json().get('hentai_franchise_hentai_videos', [{'slug': slug}])
                # Auto-extract for franchise (No UI needed, just dump links)
                await status.edit_text("⏳ **Extracting links for Series...**")
                text_content = ""
                for vid in franchise_videos:
                    vid_url = f"https://hanime.tv/videos/hentai/{vid['slug']}"
                    title, formats = await get_video_info_async(vid_url)
                    if title:
                        text_content += f"🎬 Title: {title}\n"
                        qualities = [k for k in formats.keys() if isinstance(k, int)]
                        qualities.sort(reverse=True)
                        for q in qualities: text_content += f"🎥 {q}p: {formats[q]}\n"
                        text_content += "-"*40 + "\n\n"
                
                if text_content:
                    file_name = f"Series_Links_{uuid.uuid4().hex[:6]}.txt"
                    with open(file_name, "w", encoding="utf-8") as f: f.write(text_content)
                    await message.reply_document(file_name, caption="✅ **Here are all the direct links!**")
                    os.remove(file_name)
                    await status.delete()
                else: await status.edit_text("❌ Failed to extract.")
            else: await status.edit_text("❌ **API ne response nahi diya.**")

    except Exception as e: await status.edit_text(f"❌ **Error:**\n`{str(e)}`")

# ==========================================
# 🎛️ PLAYLIST UI INTERACTION HANDLERS 
# ==========================================
@app.on_callback_query(filters.regex(r"^tgl_(.+)_(.+)$"))
async def toggle_video(client, query):
    task_id = query.matches[0].group(1)
    idx = int(query.matches[0].group(2))
    if task_id not in PENDING_TASKS: return await query.answer("❌ Session expired!", show_alert=True)
    if query.from_user.id != PENDING_TASKS[task_id]["user_id"]: return await query.answer("❌ Ye button tumhare liye nahi hai bhai!", show_alert=True)
    
    selected = PENDING_TASKS[task_id]["selected"]
    if idx in selected: selected.remove(idx)
    else: selected.append(idx)
    await render_playlist_keyboard(query.message, task_id)

@app.on_callback_query(filters.regex(r"^tglall_(.+)$"))
async def toggle_all(client, query):
    task_id = query.matches[0].group(1)
    if task_id not in PENDING_TASKS: return
    PENDING_TASKS[task_id]["selected"] = list(range(len(PENDING_TASKS[task_id]["groups"])))
    await render_playlist_keyboard(query.message, task_id)

@app.on_callback_query(filters.regex(r"^tglno_(.+)$"))
async def toggle_none(client, query):
    task_id = query.matches[0].group(1)
    if task_id not in PENDING_TASKS: return
    PENDING_TASKS[task_id]["selected"] = []
    await render_playlist_keyboard(query.message, task_id)

@app.on_callback_query(filters.regex(r"^tgldone_(.+)$"))
async def done_selection(client, query):
    task_id = query.matches[0].group(1)
    if task_id not in PENDING_TASKS: return await query.answer("❌ Session expired!", show_alert=True)
    if query.from_user.id != PENDING_TASKS[task_id]["user_id"]: return await query.answer("❌ Ye button tumhare liye nahi hai bhai!", show_alert=True)
    
    task = PENDING_TASKS.pop(task_id)
    selected_indices = task["selected"]
    if not selected_indices: return await query.answer("⚠️ Bhai, kam se kam 1 series toh select karo!", show_alert=True)
    
    final_episodes = []
    for i in sorted(selected_indices): final_episodes.extend(task["groups"][i]["episodes"])
    
    await query.message.edit_text(f"⏳ **Scraping Direct Links for {len(final_episodes)} episodes... Please wait.**")
    
    text_content = ""
    for vid in final_episodes:
        vid_url = vid['url']
        title, formats = await get_video_info_async(vid_url)
        if title:
            text_content += f"🎬 Title: {title}\n"
            qualities = [k for k in formats.keys() if isinstance(k, int)]
            qualities.sort(reverse=True)
            for q in qualities: text_content += f"🎥 {q}p: {formats[q]}\n"
            text_content += "-"*40 + "\n\n"
        
    if text_content:
        file_name = f"Batch_Links_{task_id}.txt"
        with open(file_name, "w", encoding="utf-8") as f: f.write(text_content)
        await query.message.reply_document(file_name, caption=f"✅ **Extracted {len(final_episodes)} Videos Successfully!**")
        os.remove(file_name)
        await query.message.delete()
    else:
        await query.message.edit_text("❌ **Extraction completely failed.**")

if __name__ == "__main__":
    print("🤖 Universal Extractor is Alive (NO MONGODB, NO UPLOAD)!")
    keep_alive() 
    app.run()
      
