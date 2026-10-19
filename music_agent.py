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

log("🎵 Музыкальный агент инициализирован (v3.18: поддержка metadata + авто-поиск обложек + правильный audio_id)")

# ============================================================
# Транслитерация для авто-поиска обложек
# ============================================================
def transliterate_rus_to_lat(text):
    """Преобразует русское название альбома в имя файла обложки (латиница)."""
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
# ВК API с обработкой флуда
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
                log(f" VK Flood control на {method}: жду {delay} сек (попытка {attempt+1}/{retries})...")
                time.sleep(delay)
                continue
            log(f"⚠️ VK {method}: {str(err)[:150]}")
            return None
        return r.get("response")
    log(f"❌ VK {method}: флуд-контроль не отпустил за {retries} попыток")
    return None

def flood_probe():
    log("🌡 Проверяю барометр флуда для музыки...")
    srv = vk_call("photos.getWallUploadServer", 
                  {"owner_id": "-" + VK_GROUP_ID}, 
                  token=VK_USER_TOKEN, retries=1)
    ok = bool(srv and "upload_url" in srv)
    log(f"🌡 Барометр флуда: {'ЗЁЛЕНЫЙ — загрузка доступна' if ok else 'КРАСНЫЙ — флуд/кулдаун'}")
    return ok, srv

def finish_upload(srv, img_bytes):
    try:
        r = requests.post(srv["upload_url"],
                         files={"photo": ("cover.jpg", img_bytes, "image/jpeg")},
                         timeout=120).json()
    except Exception as e:
        log(f"️ ВК upload: ошибка POST: {e}")
        return None
    if not (r.get("photo") and r.get("hash")):
        log(f"⚠️ ВК upload: пустой ответ: {str(r)[:120]}")
        return None
    saved = vk_call("photos.saveWallPhoto",
                    {"owner_id": "-" + VK_GROUP_ID, "photo": r["photo"],
                     "server": r.get("server", ""), "hash": r.get("hash", "")},
                    token=VK_USER_TOKEN, retries=2)
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
    res = vk_call("wall.post", params)
    if not res and VK_USER_TOKEN:
        log("⚠️ ВК: групповой токен не смог опубликовать — пробую юзер-токеном")
        res = vk_call("wall.post", params, token=VK_USER_TOKEN)
    if res:
        log(f"✅ ВК: пост опубликован: https://vk.com/wall-{VK_GROUP_ID}_{res.get('post_id')}")
        return res
    return None

# ============================================================
# Кэш обложек
# ============================================================
def load_covers_cache():
    try:
        if os.path.exists(COVERS_CACHE):
            return json.load(open(COVERS_CACHE, encoding="utf-8"))
    except Exception:
        pass
    return {}

def save_covers_cache(cache):
    try:
        json.dump(cache, open(COVERS_CACHE, "w", encoding="utf-8"), ensure_ascii=False)
        log(f"💾 Кэш обложек сохранён: {len(cache)} записей")
    except Exception as e:
        log(f"⚠️ Кэш обложек: {e}")

def get_cover_from_cache(album_title):
    cache = load_covers_cache()
    if album_title in cache:
        log(f"✅ Обложка «{album_title}» взята из кэша: {cache[album_title]}")
        return cache[album_title]
    return None

def save_cover_to_cache(album_title, att):
    cache = load_covers_cache()
    cache[album_title] = att
    save_covers_cache(cache)

# ============================================================
# Pending (отложенная публикация)
# ============================================================
def save_pending(track_info, cover_path):
    try:
        json.dump({"track": track_info, "cover_path": cover_path, 
                   "created": datetime.datetime.now().isoformat()},
                  open(PENDING_MUSIC, "w", encoding="utf-8"), ensure_ascii=False)
        log(f"💾 pending_music.json создан: трек ждёт публикации")
    except Exception as e:
        log(f"⚠️ pending music: {e}")

def load_pending():
    try:
        if os.path.exists(PENDING_MUSIC):
            return json.load(open(PENDING_MUSIC, encoding="utf-8"))
    except Exception:
        pass
    return None

def clear_pending():
    try:
        if os.path.exists(PENDING_MUSIC):
            os.remove(PENDING_MUSIC)
            log("🧹 pending_music.json удалён")
    except Exception:
        pass

# ============================================================
# Загрузка музыки
# ============================================================
def load_music():
    try:
        data = json.load(open(MUSIC_FILE, encoding="utf-8"))
        return data
    except Exception as e:
        log(f"❌ Ошибка загрузки {MUSIC_FILE}: {e}")
        return None

def get_random_track(music_data):
    """Выбирает случайный трек из альбомов/EP/синглов."""
    tracks = []
    
    # Получаем исполнителя из metadata (если есть)
    default_artist = ""
    if "metadata" in music_data and "artist" in music_data["metadata"]:
        default_artist = music_data["metadata"]["artist"].strip()
    
    # Альбомы
    for album in music_data.get("albums", []):
        for track in album.get("tracks", []):
            tracks.append({
                "type": "album",
                "album_title": album.get("title", ""),
                "track_title": track.get("title", ""),
                "artist": default_artist,  # Берём из metadata
                "audio_id": track.get("audio_id", ""),
                "genre": album.get("genre", "")
            })
    
    # EP
    for ep in music_data.get("eps", []):
        for track in ep.get("tracks", []):
            tracks.append({
                "type": "ep",
                "album_title": ep.get("title", ""),
                "track_title": track.get("title", ""),
                "artist": default_artist,
                "audio_id": track.get("audio_id", ""),
                "genre": ep.get("genre", "")
            })
    
    # Синглы
    for single in music_data.get("singles", []):
        for track in single.get("tracks", []):
            tracks.append({
                "type": "single",
                "album_title": single.get("title", ""),
                "track_title": track.get("title", ""),
                "artist": default_artist,
                "audio_id": track.get("audio_id", ""),
                "genre": single.get("genre", "")
            })
    
    if not tracks:
        return None
    return random.choice(tracks)

def prepare_cover(track_info):
    """v3.18: Авто-поиск обложки по названию альбома (рус→латиница)."""
    album_title = track_info.get("album_title", "Unknown")
    
    # 1. Сначала проверяем кэш
    cached_att = get_cover_from_cache(album_title)
    if cached_att:
        return cached_att, None
    
    # 2. Авто-поиск: преобразуем название альбома в имя файла
    album_slug = transliterate_rus_to_lat(album_title)
    possible_paths = [
        f"covers/{album_slug}.jpg",
        f"covers/{album_slug}.png",
        f"covers/{album_slug}.jpeg",
    ]
    
    for cover_path in possible_paths:
        if os.path.exists(cover_path):
            log(f"✅ Обложка найдена авто-поиском: {cover_path}")
            with open(cover_path, "rb") as f:
                img_bytes = f.read()
            return None, img_bytes
    
    log(f"❌ Обложка не найдена для альбома «{album_title}» (ожидался: covers/{album_slug}.jpg)")
    return None, None

# ============================================================
# Режим тика (допубликация pending)
# ============================================================
def run_tick():
    log("🕐 Режим: ТИК (допубликация отложенного музыкального поста)")
    pend = load_pending()
    if not pend:
        log("ℹ️ pending_music.json нет — отложенных постов нет")
        return True
    
    track_info = pend.get("track", {})
    cover_path = pend.get("cover_path", "")
    
    green, srv = flood_probe()
    if not green:
        log("⏳ Флуд красный — pending music ждёт следующего тика")
        return True
    
    img_bytes = None
    if cover_path and os.path.exists(cover_path):
        with open(cover_path, "rb") as f:
            img_bytes = f.read()
        log(f"🖼 Обложка загружена из pending: {cover_path}, {len(img_bytes)} байт")
    else:
        log(f"⚠️ Файл {cover_path} не найден — сбрасываю pending")
        clear_pending()
        return True
    
    att = finish_upload(srv, img_bytes)
    if not att:
        log("⚠️ Загрузка обложки не удалась — жду следующий тик")
        return True
    
    album_title = track_info.get("album_title", "")
    if album_title:
        save_cover_to_cache(album_title, att)
    
    artist = track_info.get("artist", "")
    track_title = track_info.get("track_title", "")
    audio_id = track_info.get("audio_id", "")
    
    caption = f" {artist} — {track_title}"
    # audio_id уже содержит префикс "audio-", используем как есть
    attachments = f"{att},{audio_id}" if att and audio_id else audio_id
    
    res = vk_post_wall(caption, attachments if attachments else None)
    if res:
        log(f"✅ ВК: pending music опубликован")
        clear_pending()
        return True
    else:
        log("⚠️ Публикация pending music не удалась")
        return False

# ============================================================
# Режим публикации
# ============================================================
def run_publish():
    log("📢 Режим: ПУБЛИКАЦИЯ (музыка)")
    
    music_data = load_music()
    if not music_data:
        log("❌ Нет данных о музыке")
        return False
    
    track_info = get_random_track(music_data)
    if not track_info:
        log("❌ Нет треков для публикации")
        return False
    
    artist = track_info.get("artist", "")
    track_title = track_info.get("track_title", "")
    album_title = track_info.get("album_title", "")
    audio_id = track_info.get("audio_id", "")
    genre = track_info.get("genre", "")
    
    log(f"🎵 Выбран трек: {artist} — {track_title} (альбом: {album_title}, жанр: {genre})")
    log(f"🎵 audio_id: {audio_id}")
    
    # Подготавливаем обложку (с авто-поиском по транслитерации)
    att, img_bytes = prepare_cover(track_info)
    
    if att:
        log("✅ Используем обложку из кэша")
    elif img_bytes:
        green, srv = flood_probe()
        if not green:
            log("⏳ Флуд красный — сохраняю трек в pending для следующей попытки")
            cover_path = f"covers/pending_{album_title.replace(' ', '_')}.jpg"
            os.makedirs("covers", exist_ok=True)
            with open(cover_path, "wb") as f:
                f.write(img_bytes)
            save_pending(track_info, cover_path)
            return True
        
        att = finish_upload(srv, img_bytes)
        if att:
            save_cover_to_cache(album_title, att)
        else:
            log("⚠️ Загрузка обложки не удалась, пробую опубликовать без фото")
    else:
        log("️ Публикую пост БЕЗ обложки (так как фото не найдено)")
    
    # Формируем caption с информацией об альбоме и жанре
    caption_parts = [f"🎵 {artist} — {track_title}"]
    if album_title:
        caption_parts.append(f"💿 Альбом: «{album_title}»")
    if genre:
        caption_parts.append(f"🎼 Жанр: {genre}")
    
    caption = "\n".join(caption_parts)
    
    # Формируем attachments
    # audio_id уже содержит префикс "audio-", используем как есть
    attachments = f"{att},{audio_id}" if att and audio_id else audio_id
    
    res = vk_post_wall(caption, attachments if attachments else None)
    
    if res:
        log(f"✅ Готово: {album_title} (опубликовано{' с обложкой' if att else ' без обложки'})")
        return True
    else:
        log("❌ Публикация не удалась")
        return False

# ============================================================
# Точка входа
# ============================================================
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
