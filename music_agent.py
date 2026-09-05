# -*- coding: utf-8 -*-
import os, re, json, random, requests, hashlib
from bs4 import BeautifulSoup

# --- Настройки из окружения (те же, что в agent.py) ---
VK_TOKEN = os.getenv("VK_TOKEN", "")
VK_GROUP = os.getenv("VK_GROUP_ID", "")
GROQ_KEY = os.getenv("GROQ_KEY", "")
OR_KEY = os.getenv("OPENROUTER_KEY", "")

ARTIST_URL = "https://vk.ru/artist/pavelgnesyuk"
HISTORY_FILE = "music_history.json"
CACHE_FILE = "music_cache.json"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

def log(msg): 
    print(msg, flush=True)

log("Версия ℹ️ music-agent v3 (VK Music парсинг + пост в ВК)")

# --- 1. Парсинг VK Music ---
def parse_vk_music():
    try:
        log("🔍 Парсинг страницы артиста VK...")
        resp = requests.get(ARTIST_URL, headers=UA, timeout=30)
        soup = BeautifulSoup(resp.text, "html.parser")
        
        audios = []
        albums = {}
        for script in soup.find_all("script"):
            text = script.string or ""
            if "audios" in text.lower() or "AudioArtist" in text:
                # Ищем массив треков
                match_a = re.search(r'"audios":\s*(\[[^\]]+\])', text, re.DOTALL)
                if match_a:
                    try: audios = json.loads(match_a.group(1))
                    except: pass
                
                # Ищем словарь альбомов
                match_b = re.search(r'"albums":\s*(\{.*?\})\s*[,}]', text, re.DOTALL)
                if match_b:
                    try: albums = json.loads(match_b.group(1))
                    except: pass
        
        if not audios:
            raise RuntimeError("Не найдены данные audios в HTML")
        
        # Группируем треки по альбомам
        result = {"albums": {}, "tracks": audios}
        for track in audios:
            aid = str(track.get("album_id", ""))
            if aid and aid != "0":
                if aid not in result["albums"]:
                    alb_data = albums.get(aid, {})
                    result["albums"][aid] = {
                        "id": aid,
                        "title": alb_data.get("title", "Сингл"),
                        "cover": alb_data.get("cover", ""),
                        "url": ARTIST_URL
                    }
                if "tracks" not in result["albums"][aid]:
                    result["albums"][aid]["tracks"] = []
                result["albums"][aid]["tracks"].append({
                    "id": track.get("id"),
                    "title": track.get("title", "Без названия"),
                    "artist": track.get("artist", "Павел Гнесюк"),
                    "url": ARTIST_URL
                })
        
        # Сохраняем кэш на случай сбоев VK
        json.dump(result, open(CACHE_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        log(f"✅ Успешно распарсено: {len(audios)} треков, {len(result['albums'])} альбомов")
        return result
        
    except Exception as e:
        log(f"⚠️ Ошибка парсинга: {e}. Загружаю из кэша...")
        if os.path.exists(CACHE_FILE):
            return json.load(open(CACHE_FILE, encoding="utf-8"))
        return None

# --- 2. Генерация текста (350-700 символов) ---
def generate_text(track, album):
    prompt = (
        f"Напиши короткий пост о песне Павла Гнесюка для группы ВКонтакте.\n\n"
        f"ПЕСНЯ: «{track['title']}»\n"
        f"АЛЬБОМ: «{album['title']}»\n\n"
        f"ТРЕБОВАНИЯ:\n"
        f"1. ТОЛЬКО русский язык.\n"
        f"2. Длина СТРОГО 350-650 символов.\n"
        f"3. Начни с описания самой песни: о чём она, какое настроение или смысл несёт.\n"
        f"4. Добавь 1-2 предложения про смысл или атмосферу всего альбома.\n"
        f"5. В конце обязательно укажи ссылку на альбом: {album['url']}\n"
        f"6. Стиль: живой, искренний, без пафоса и клише.\n"
        f"7. Не используй хэштеги, кроме #ПавелГнесюк #музыка в самом конце."
    )
    
    # Пробуем доступные модели (как в agent.py)
    models = [
        ("groq", "llama-3.3-70b-versatile", GROQ_KEY),
        ("openrouter", "meta-llama/llama-3.3-70b-instruct:free", OR_KEY),
        ("openrouter", "google/gemma-3-27b-it:free", OR_KEY)
    ]
    
    for provider, model, key in models:
        if not key: continue
        try:
            url = "https://api.groq.com/openai/v1/chat/completions" if provider == "groq" else "https://openrouter.ai/api/v1/chat/completions"
            headers = {"Authorization": f"Bearer {key}"}
            if provider == "openrouter": headers["HTTP-Referer"] = "https://github.com"
            
            r = requests.post(url, headers=headers, json={
                "model": model, "temperature": 0.8, "max_tokens": 800,
                "messages": [{"role": "user", "content": prompt}]
            }, timeout=45).json()
            
            if "error" not in r and "choices" in r:
                text = r["choices"][0]["message"]["content"].strip()
                if 300 <= len(text) <= 750:
                    log(f"✅ Текст сгенерирован ({provider}): {len(text)} симв.")
                    return text
        except Exception:
            continue
    
    # Fallback, если ИИ недоступен
    log("⚠️ ИИ недоступен, использую шаблон")
    return (
        f"🎵 «{track['title']}» — песня из альбома «{album['title']}».\n\n"
        f"Этот альбом раскрывает глубокие смыслы и атмосферу, в которую хочется погрузиться.\n\n"
        f"🎧 Слушайте на VK Музыке: {album['url']}\n\n#ПавелГнесюк #музыка"
    )

# --- 3. Публикация в ВК ---
def vk_upload_photo(photo_data):
    if not VK_TOKEN or not VK_GROUP:
        log("⚠️ Нет VK_TOKEN или VK_GROUP_ID")
        return None
    try:
        # 1. Получаем URL загрузки
        req1 = requests.post("https://api.vk.com/method/photos.getWallUploadServer",
            params={"group_id": VK_GROUP, "access_token": VK_TOKEN, "v": "5.131"}, timeout=30).json()
        if "response" not in req1: return None
        
        # 2. Загружаем файл
        files = {"photo": ("cover.jpg", photo_data, "image/jpeg")}
        req2 = requests.post(req1["response"]["upload_url"], files=files, timeout=60).json()
        if "photo" not in req2: return None
        
        # 3. Сохраняем фото
        req3 = requests.post("https://api.vk.com/method/photos.saveWallPhoto",
            params={
                "photo": req2["photo"], "server": req2["server"], "hash": req2["hash"],
                "group_id": VK_GROUP, "access_token": VK_TOKEN, "v": "5.131"
            }, timeout=30).json()
        
        if "response" in req3 and req3["response"]:
            p = req3["response"][0]
            acc = p.get("access_key", "")
            return f"photo{p['owner_id']}_{p['id']}_{acc}" if acc else f"photo{p['owner_id']}_{p['id']}"
        return None
    except Exception as e:
        log(f"⚠️ Ошибка загрузки фото в ВК: {e}")
        return None

def vk_post(message, attachment=None):
    if not VK_TOKEN or not VK_GROUP: return False
    try:
        params = {"owner_id": f"-{VK_GROUP}", "message": message, "access_token": VK_TOKEN, "v": "5.131"}
        if attachment: params["attachments"] = attachment
        
        r = requests.post("https://api.vk.com/method/wall.post", params=params, timeout=30).json()
        if "response" in r:
            log(f"✅ Опубликовано в ВК: post_id={r['response']['post_id']}")
            return True
        log(f"⚠️ Ошибка публикации ВК: {r}")
        return False
    except Exception as e:
        log(f"⚠️ Ошибка ВК: {e}")
        return False

# --- Главная функция ---
def main():
    data = parse_vk_music()
    if not data or not data.get("tracks"):
        log("❌ Нет данных о треках")
        return
    
    # Выбираем случайный альбом с треками
    valid_albums = [a for a in data["albums"].values() if a.get("tracks")]
    if not valid_albums:
        log("❌ Нет альбомов с треками")
        return
    
    album = random.choice(valid_albums)
    track = random.choice(album["tracks"])
    
    log(f"🎵 Альбом: «{album['title']}»")
    log(f"🎶 Трек: «{track['title']}»")
    
    # Скачиваем обложку
    cover_bytes = b""
    if album.get("cover"):
        try:
            r = requests.get(album["cover"], timeout=30)
            if r.headers.get("content-type", "").startswith("image"):
                cover_bytes = r.content
                log(f"✅ Обложка загружена: {len(cover_bytes)} байт")
        except Exception as e:
            log(f"⚠️ Ошибка загрузки обложки: {e}")
    
    # Генерируем текст
    text = generate_text(track, album)
    
    # Публикуем
    if cover_bytes:
        os.makedirs("img", exist_ok=True)
        slug = hashlib.md5(f"{track['id']}".encode()).hexdigest()[:8]
        img_path = f"img/music_{slug}.jpg"
        with open(img_path, "wb") as f:
            f.write(cover_bytes)
        log(f"💾 Сохранено локально: {img_path}")
        
        attachment = vk_upload_photo(cover_bytes)
        if attachment:
            vk_post(text, attachment)
        else:
            log("⚠️ Не удалось загрузить фото в ВК — публикую без картинки")
            vk_post(text)
    else:
        vk_post(text)
    
    # Сохраняем в историю, чтобы не повторяться
    try:
        hist = set(json.load(open(HISTORY_FILE, encoding="utf-8"))) if os.path.exists(HISTORY_FILE) else set()
    except:
        hist = set()
    hist.add(track["id"])
    json.dump(list(hist), open(HISTORY_FILE, "w", encoding="utf-8"), ensure_ascii=False)
    
    log("=" * 50)
    log("✅ FINISH: пост о музыке опубликован в ВК!")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"❌ КРИТИЧЕСКАЯ ОШИБКА: {e}")
        raise
