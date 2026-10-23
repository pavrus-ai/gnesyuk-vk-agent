# -*- coding: utf-8 -*-
import os, json, datetime, requests, time, io, glob, random, urllib3
from PIL import Image
urllib3.disable_warnings()

VK_TOKEN = os.environ.get("VK_TOKEN", "").strip()
VK_USER_TOKEN = os.environ.get("VK_USER_TOKEN", "").strip()
VK_GROUP_ID = os.environ.get("VK_GROUP_ID", "").strip().lstrip("-")
VK_API = "https://api.vk.com/method/"
VK_V = "5.131"

COVERS_CACHE = "covers_cache.json"
PENDING_MUSIC = "pending_music.json"
MUSIC_FILE = "music.json"

SCHEDULE = os.environ.get("SCHEDULE", "").strip()
PUBLISH_CRON = "30 6 * * *"  # 09:30 МСК

def log(msg):
    print(msg, flush=True)

log("🎵 Музыкальный агент инициализирован (v3.20: исправлена логика барометра, убрана лишняя проверка)")

# ============================================================
# Транслитерация для авто-поиска обложек
# ============================================================
def transliterate_rus_to_lat(text):
    mapping = {
        'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'yo',
        'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
        'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
        'ф': 'f', 'х': 'kh', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'shch',
        'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya',
        ' ': '-', ':': '', "'": '', '"': '', '(': '', ')': '', '/': '-',
    }
    text = text.lower().strip()
    result = ''.join(mapping.get(c, c) for c in text)
    while '--' in result:
        result = result.replace('--', '-')
    return result.strip('-')

# ============================================================
# ВК API
# ============================================================
def vk_call(method, params=None, token=None, retries=1):
    p = dict(params or {})
    p["access_token"] = token or VK_TOKEN
    p["v"] = VK_V
    for attempt in range(retries):
        try:
            r = requests.post(VK_API + method, data=p, timeout=30).json()
        except Exception as e:
            log(f"⚠️ VK {method}: сеть {e}")
            time.sleep(5 * (attempt + 1))
            continue
        if "error" in r:
            err = r["error"]
            if err.get("error_code") == 9:
                delay = 15 * (attempt + 1)
                log(f"⏳ VK Flood control на {method}: жду {delay} сек...")
                time.sleep(delay)
                continue
            # Игнорируем ошибку 27 для барометра, если это fallback
            return None
        return r.get("response")
    return None

def flood_probe():
    """Проверяет возможность загрузки фото. Пробует user_token, затем group_token."""
    log("🌡 Проверяю барометр флуда для загрузки фото...")
    
    # 1. Пробуем пользовательский токен (он имеет приоритет для photos.*)
    if VK_USER_TOKEN:
        srv = vk_call("photos.getWallUploadServer", {"owner_id": "-" + VK_GROUP_ID}, token=VK_USER_TOKEN, retries=1)
        if srv and "upload_url" in srv:
            log("🌡 Барометр: ЗЁЛЕНЫЙ (через VK_USER_TOKEN)")
            return True, srv
            
    # 2. Если не вышло, пробуем групповой токен (вдруг у него есть права photos)
    if VK_TOKEN:
        srv = vk_call("photos.getWallUploadServer", {"owner_id": "-" + VK_GROUP_ID}, token=VK_TOKEN, retries=1)
        if srv and "upload_url" in srv:
            log("🌡 Барометр: ЗЁЛЕНЫЙ (через VK_TOKEN)")
            return True, srv
            
    log("🌡 Барометр: КРАСНЫЙ (флуд или нет прав на загрузку фото)")
    return False, None

def finish_upload(srv, img_bytes):
    try:
        r = requests.post(srv["upload_url"], files={"photo": ("cover.jpg", img_bytes, "image/jpeg")}, timeout=120).json()
    except Exception as e:
        log(f"⚠️ ВК upload: ошибка POST: {e}")
        return None
    if not (r.get("photo") and r.get("hash")):
        return None
    saved = vk_call("photos.saveWallPhoto", {"owner_id": "-" + VK_GROUP_ID, "photo": r["photo"], "server": r.get("server", ""), "hash": r.get("hash", "")}, token=VK_USER_TOKEN or VK_TOKEN, retries=2)
    if not saved:
        return None
    p = saved[0]
    att = f"photo{p['owner_id']}_{p['id']}"
    if p.get("access_key"):
        att += f"_{p['access_key']}"
    log(f"✅ ВК: обложка загружена → {att}")
    return att

def vk_post_wall(text, attachment=None):
    params = {"owner_id": "-" + VK_GROUP_ID, "message": text, "from_group": 1}
    if attachment:
        params["attachments"] = attachment
    
    # Публикация отлично работает с групповым токеном
    res = vk_call("wall.post", params, token=VK_TOKEN, retries=2)
    if not res and VK_USER_TOKEN:
        res = vk_call("wall.post", params, token=VK_USER_TOKEN, retries=2)
    
    if res:
        log(f"✅ ВК: пост опубликован: https://vk.com/wall-{VK_GROUP_ID}_{res.get('post_id')}")
        return res
    return None

# ============================================================
# Кэш и Pending
# ============================================================
def load_covers_cache():
    try:
        if os.path.exists(COVERS_CACHE): return json.load(open(COVERS_CACHE, encoding="utf-8"))
    except Exception: pass
    return {}

def save_covers_cache(cache):
    try:
        json.dump(cache, open(COVERS_CACHE, "w", encoding="utf-8"), ensure_ascii=False)
    except Exception: pass

def get_cover_from_cache(album_title):
    cache = load_covers_cache()
    if album_title in cache:
        log(f"✅ Обложка «{album_title}» взята из кэша")
        return cache[album_title]
    return None

def save_cover_to_cache(album_title, att):
    cache = load_covers_cache()
    cache[album_title] = att
    save_covers_cache(cache)

def save_pending(track_info, att, cover_path=None):
    try:
        data = {"track": track_info, "att": att, "cover_path": cover_path, "created": datetime.datetime.now().isoformat()}
        json.dump(data, open(PENDING_MUSIC, "w", encoding="utf-8"), ensure_ascii=False)
        log("💾 pending_music.json создан: трек ждёт публикации")
    except Exception as e:
        log(f"⚠️ pending music: {e}")

def load_pending():
    try:
        if os.path.exists(PENDING_MUSIC): return json.load(open(PENDING_MUSIC, encoding="utf-8"))
    except Exception: pass
    return None

def clear_pending():
    try:
        if os.path.exists(PENDING_MUSIC):
            os.remove(PENDING_MUSIC)
            log("🧹 pending_music.json удалён")
    except Exception: pass

# ============================================================
# Загрузка музыки
# ============================================================
def load_music():
    try:
        return json.load(open(MUSIC_FILE, encoding="utf-8"))
    except Exception as e:
        log(f"❌ Ошибка загрузки {MUSIC_FILE}: {e}")
        return None

def get_random_track(music_data):
    tracks = []
    default_artist = music_data.get("metadata", {}).get("artist", "").strip()
    
    for album in music_data.get("albums", []):
        for track in album.get("tracks", []):
            tracks.append({"type": "album", "album_title": album.get("title", ""), "track_title": track.get("title", ""), "artist": default_artist, "audio_id": track.get("audio_id", ""), "genre": album.get("genre", "")})
    for ep in music_data.get("eps", []):
        for track in ep.get("tracks", []):
            tracks.append({"type": "ep", "album_title": ep.get("title", ""), "track_title": track.get("title", ""), "artist": default_artist, "audio_id": track.get("audio_id", ""), "genre": ep.get("genre", "")})
    for single in music_data.get("singles", []):
        for track in single.get("tracks", []):
            tracks.append({"type": "single", "album_title": single.get("title", ""), "track_title": track.get("title", ""), "artist": default_artist, "audio_id": track.get("audio_id", ""), "genre": single.get("genre", "")})
    
    return random.choice(tracks) if tracks else None

def prepare_cover(track_info):
    album_title = track_info.get("album_title", "Unknown")
    cached_att = get_cover_from_cache(album_title)
    if cached_att:
        return cached_att, None
    
    album_slug = transliterate_rus_to_lat(album_title)
    for ext in [".jpg", ".png", ".jpeg"]:
        cover_path = f"covers/{album_slug}{ext}"
        if os.path.exists(cover_path):
            log(f"✅ Обложка найдена авто-поиском: {cover_path}")
            with open(cover_path, "rb") as f:
                return None, f.read()
    
    log(f"❌ Обложка не найдена для «{album_title}» (ожидался: covers/{album_slug}.jpg)")
    return None, None

# ============================================================
# Режимы работы
# ============================================================
def run_tick():
    log("🕐 Режим: ТИК (допубликация)")
    pend = load_pending()
    if not pend:
        log("ℹ️ pending_music.json нет")
        return True
    
    track_info = pend.get("track", {})
    att = pend.get("att", "")
    cover_path = pend.get("cover_path", "")
    
    green, srv = flood_probe()
    if not green:
        log("⏳ Флуд красный — pending music ждёт следующего тика")
        return True
    
    if not att and cover_path and os.path.exists(cover_path):
        with open(cover_path, "rb") as f:
            img_bytes = f.read()
        att = finish_upload(srv, img_bytes)
        if att:
            save_cover_to_cache(track_info.get("album_title", ""), att)
        else:
            return True
            
    artist = track_info.get("artist", "")
    track_title = track_info.get("track_title", "")
    album_title = track_info.get("album_title", "")
    audio_id = track_info.get("audio_id", "")
    genre = track_info.get("genre", "")
    
    caption = f"🎵 {artist} — {track_title}"
    if album_title: caption += f"\n💿 Альбом: «{album_title}»"
    if genre: caption += f"\n🎼 Жанр: {genre}"
    
    attachments = f"{att},{audio_id}" if att and audio_id else audio_id
    res = vk_post_wall(caption, attachments if attachments else None)
    
    if res:
        log("✅ ВК: pending music опубликован")
        clear_pending()
    return bool(res)

def run_publish():
    log("📢 Режим: ПУБЛИКАЦИЯ (музыка)")
    music_data = load_music()
    if not music_data: return False
    
    track_info = get_random_track(music_data)
    if not track_info:
        log("❌ Нет треков для публикации")
        return False
    
    artist = track_info.get("artist", "")
    track_title = track_info.get("track_title", "")
    album_title = track_info.get("album_title", "")
    audio_id = track_info.get("audio_id", "")
    genre = track_info.get("genre", "")
    
    log(f"🎵 Выбран трек: {artist} — {track_title} (альбом: {album_title})")
    log(f"🎵 audio_id: {audio_id}")
    
    att, img_bytes = prepare_cover(track_info)
    
    if att:
        log("✅ Используем обложку из кэша")
    elif img_bytes:
        # ПРОВЕРЯЕМ ФЛУД ТОЛЬКО ЗДЕСЬ (перед реальной загрузкой)
        green, srv = flood_probe()
        if not green:
            log("⏳ Флуд красный — сохраняю трек в pending")
            album_slug = transliterate_rus_to_lat(album_title)
            cover_path = f"covers/pending_{album_slug}.jpg"
            os.makedirs("covers", exist_ok=True)
            with open(cover_path, "wb") as f:
                f.write(img_bytes)
            save_pending(track_info, "", cover_path)
            return True
        
        att = finish_upload(srv, img_bytes)
        if att:
            save_cover_to_cache(album_title, att)
        else:
            log("⚠️ Загрузка обложки не удалась, публикую без фото")
    else:
        log("⚠️ Публикую пост БЕЗ обложки")
    
    # Формируем текст и вложения
    caption_parts = [f"🎵 {artist} — {track_title}"]
    if album_title: caption_parts.append(f"💿 Альбом: «{album_title}»")
    if genre: caption_parts.append(f"🎼 Жанр: {genre}")
    caption = "\n".join(caption_parts)
    
    attachments = f"{att},{audio_id}" if att and audio_id else audio_id
    
    # ПУБЛИКУЕМ СРАЗУ (без лишних проверок барометра, wall.post работает с VK_TOKEN)
    res = vk_post_wall(caption, attachments if attachments else None)
    
    if res:
        log(f"✅ Готово: {album_title} (опубликовано{' с обложкой' if att else ' без обложки'})")
        return True
    else:
        log("❌ Публикация не удалась")
        return False

def main():
    if not VK_TOKEN or not VK_GROUP_ID:
        log("⚠️ Нет VK_TOKEN/VK_GROUP_ID")
        return
    
    mode = "publish" if (not SCHEDULE or SCHEDULE == PUBLISH_CRON) else "tick"
    log(f"🗓 Расписание: «{SCHEDULE or 'ручной'}» → режим: {mode}")
    
    if mode == "tick":
        run_tick()
    else:
        run_publish()

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"❌ КРИТИЧЕСКАЯ ОШИБКА: {e}")
        raise
