# -*- coding: utf-8 -*-
import os, re, json, random, requests, datetime, hashlib, time
from bs4 import BeautifulSoup

VK_TOKEN = os.getenv("VK_TOKEN", "")
VK_GROUP = os.getenv("VK_GROUP_ID", "")
GROQ_KEY = os.getenv("GROQ_KEY2", "") or os.getenv("GROQ_KEY", "")
OR_KEY = os.getenv("OPENROUTER_KEY2", "") or os.getenv("OPENROUTER_KEY", "")

ARTIST_URL = "https://vk.ru/artist/pavelgnesyuk"
HISTORY_FILE = "music_history.json"
MUSIC_CACHE_FILE = "music_cache.json"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

def log(msg): 
    print(msg, flush=True)

log("Версия ℹ️ music-agent v1 (парсинг VK Music + посты о песнях)")

# --- Парсинг VK Music ---
def parse_vk_music():
    """Извлекает альбомы и треки со страницы артиста VK"""
    try:
        log("🔍 Парсинг VK Music...")
        resp = requests.get(ARTIST_URL, headers=UA, timeout=30)
        soup = BeautifulSoup(resp.text, "html.parser")
        
        # Ищем JSON с данными
        scripts = soup.find_all("script")
        audios = []
        albums = {}
        
        for script in scripts:
            text = script.string or ""
            if "AudioArtist" in text or "audios" in text.lower():
                # Ищем массив audios
                match = re.search(r'"audios":\s*(\[[^\]]+\])', text, re.DOTALL)
                if match:
                    try:
                        audios = json.loads(match.group(1))
                        log(f"✅ Найдено треков: {len(audios)}")
                    except:
                        pass
                
                # Ищем альбомы
                album_match = re.search(r'"albums":\s*(\{[^\}]+\})', text, re.DOTALL)
                if album_match:
                    try:
                        albums = json.loads(album_match.group(1))
                        log(f"✅ Найдено альбомов: {len(albums)}")
                    except:
                        pass
        
        if not audios:
            log("️ Не удалось распарсить audios — используем кэш")
            if os.path.exists(MUSIC_CACHE_FILE):
                return json.load(open(MUSIC_CACHE_FILE, encoding="utf-8"))
        
        # Структурируем данные
        result = {"albums": {}, "tracks": audios}
        
        # Группируем треки по альбомам
        for track in audios:
            album_id = track.get("album_id")
            if album_id:
                if album_id not in result["albums"]:
                    result["albums"][album_id] = {
                        "id": album_id,
                        "title": albums.get(album_id, {}).get("title", "Без альбома"),
                        "cover": albums.get(album_id, {}).get("cover", ""),
                        "tracks": []
                    }
                result["albums"][album_id]["tracks"].append({
                    "id": track.get("id"),
                    "title": track.get("title"),
                    "artist": track.get("artist"),
                    "duration": track.get("duration"),
                    "url": f"{ARTIST_URL}"
                })
        
        # Сохраняем кэш
        json.dump(result, open(MUSIC_CACHE_FILE, "w", encoding="utf-8"), 
                  ensure_ascii=False, indent=2)
        log(f"✅ Кэш сохранён: {MUSIC_CACHE_FILE}")
        
        return result
        
    except Exception as e:
        log(f"❌ Ошибка парсинга: {e}")
        if os.path.exists(MUSIC_CACHE_FILE):
            log("🔄 Загружаю из кэша...")
            return json.load(open(MUSIC_CACHE_FILE, encoding="utf-8"))
        return None

# --- Генерация текста ---
def generate_post_text(track, album_info):
    """Генерирует пост о песне (350-700 символов)"""
    
    prompt = (
        f"Напиши короткий пост о песне Павла Гнесюка.\n\n"
        f"ПЕСНЯ: «{track['title']}»\n"
        f"ИСПОЛНИТЕЛЬ: {track.get('artist', 'Павел Гнесюк')}\n"
        f"АЛЬБОМ: «{album_info.get('title', 'Сингл')}»\n\n"
        f"ТРЕБОВАНИЯ:\n"
        f"1. ТОЛЬКО русский язык.\n"
        f"2. Длина СТРОГО 350-550 символов.\n"
        f"3. Начни с описания песни: о чём она, настроение, атмосфера.\n"
        f"4. Добавь 1-2 предложения об альбоме (если это не сингл).\n"
        f"5. Закончи призывом послушать.\n"
        f"6. В конце добавь ссылку: {track['url']}\n"
        f"7. Стиль: живой, искренний, без пафоса.\n\n"
        f"Текст должен быть интересен поклонникам музыки."
    )
    
    # Пробуем разные модели
    models = [
        ("groq", "llama-3.3-70b-versatile"),
        ("openrouter", "meta-llama/llama-3.3-70b-instruct:free"),
        ("openrouter", "google/gemma-3-27b-it:free")
    ]
    
    for provider, model in models:
        try:
            log(f"🔄 Генерация текста: {provider} ({model})...")
            
            if provider == "groq" and GROQ_KEY:
                r = requests.post("https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {GROQ_KEY}"},
                    json={"model": model, "temperature": 0.8,
                          "messages": [{"role": "user", "content": prompt}]},
                    timeout=45).json()
                if "error" not in r:
                    text = r["choices"][0]["message"]["content"].strip()
                    if 300 <= len(text) <= 700:
                        log(f"✅ Успех: {provider}, {len(text)} симв.")
                        return text
            
            elif provider == "openrouter" and OR_KEY:
                r = requests.post("https://openrouter.ai/api/v1/chat/completions",
                    headers={"Authorization": f"Bearer {OR_KEY}", "HTTP-Referer": "https://github.com"},
                    json={"model": model, "temperature": 0.8, "max_tokens": 800,
                          "messages": [{"role": "user", "content": prompt}]},
                    timeout=45).json()
                if "error" not in r:
                    text = r["choices"][0]["message"]["content"].strip()
                    if 300 <= len(text) <= 700:
                        log(f"✅ Успех: {provider}, {len(text)} симв.")
                        return text
                        
        except Exception as e:
            log(f"⚠️ {provider}: {e}")
    
    # Fallback: простой текст
    log("⚠️ ИИ недоступны — использую шаблон")
    return (
        f"🎵 «{track['title']}» — новая песня Павла Гнесюка.\n\n"
        f"Из альбома «{album_info.get('title', 'Сингл')}».\n\n"
        f"🎧 Слушайте на VK Музыке: {track['url']}\n\n"
        f"#ПавелГнесюк #музыка #VKмузыка"
    )

# --- Публикация ВК ---
def vk_upload_photo(photo_data):
    """Загрузка фото в ВК и получение attachment"""
    if not VK_TOKEN or not VK_GROUP:
        log("️ Нет VK_TOKEN или VK_GROUP_ID")
        return None
    
    try:
        # 1. Получаем URL для загрузки
        upload_req = requests.post(
            "https://api.vk.com/method/photos.getWallUploadServer",
            params={"group_id": VK_GROUP, "access_token": VK_TOKEN, "v": "5.131"},
            timeout=30
        ).json()
        
        if "response" not in upload_req:
            log(f"⚠️ VK: ошибка получения URL: {upload_req}")
            return None
        
        upload_url = upload_req["response"]["upload_url"]
        
        # 2. Загружаем фото
        files = {"photo": ("cover.jpg", photo_data, "image/jpeg")}
        upload_res = requests.post(upload_url, files=files, timeout=60)
        upload_json = upload_res.json()
        
        if "photo" not in upload_json:
            log(f"⚠️ VK: ошибка загрузки: {upload_json}")
            return None
        
        # 3. Сохраняем фото
        save_req = requests.post(
            "https://api.vk.com/method/photos.saveWallPhoto",
            params={
                "photo": upload_json["photo"],
                "server": upload_json["server"],
                "hash": upload_json["hash"],
                "group_id": VK_GROUP,
                "access_token": VK_TOKEN,
                "v": "5.131"
            },
            timeout=30
        ).json()
        
        if "response" not in save_req or not save_req["response"]:
            log(f"⚠️ VK: ошибка сохранения: {save_req}")
            return None
        
        photo_id = save_req["response"][0]["id"]
        owner_id = save_req["response"][0]["owner_id"]
        access_key = save_req["response"][0].get("access_key", "")
        
        return f"photo{owner_id}_{photo_id}_{access_key}" if access_key else f"photo{owner_id}_{photo_id}"
        
    except Exception as e:
        log(f"⚠️ VK upload error: {e}")
        return None

def vk_post(message, attachment=None):
    """Публикация поста в ВК"""
    if not VK_TOKEN or not VK_GROUP:
        log("⚠️ Нет VK_TOKEN или VK_GROUP_ID")
        return False
    
    try:
        params = {
            "owner_id": f"-{VK_GROUP}",
            "message": message,
            "access_token": VK_TOKEN,
            "v": "5.131"
        }
        if attachment:
            params["attachments"] = attachment
        
        r = requests.post(
            "https://api.vk.com/method/wall.post",
            params=params,
            timeout=30
        ).json()
        
        if "response" in r:
            log(f"✅ Опубликовано в ВК: post_id={r['response']['post_id']}")
            return True
        else:
            log(f"⚠️ VK post error: {r}")
            return False
            
    except Exception as e:
        log(f"⚠️ VK post error: {e}")
        return False

# --- Главная функция ---
def main():
    # Парсим VK Music
    music_data = parse_vk_music()
    if not music_data or not music_data.get("tracks"):
        log("❌ Нет данных о треках")
        return
    
    # Загружаем историю
    try:
        history = set(json.load(open(HISTORY_FILE, encoding="utf-8"))) if os.path.exists(HISTORY_FILE) else set()
    except:
        history = set()
    
    # Выбираем случайный трек
    available_tracks = [t for t in music_data["tracks"] if t["id"] not in history]
    if not available_tracks:
        history.clear()
        available_tracks = music_data["tracks"]
    
    track = random.choice(available_tracks)
    
    # Находим альбом
    album_id = track.get("album_id")
    album_info = music_data["albums"].get(album_id, {
        "title": "Сингл",
        "cover": "",
        "id": None
    })
    
    log(f" Альбом: «{album_info.get('title', 'Сингл')}»")
    log(f"🎶 Трек: «{track['title']}»")
    
    # Скачиваем обложку альбома
    cover_url = album_info.get("cover", "")
    cover_bytes = b""
    
    if cover_url:
        try:
            log(f"🖼️ Загрузка обложки...")
            r = requests.get(cover_url, timeout=30)
            if r.headers.get("content-type", "").startswith("image"):
                cover_bytes = r.content
                log(f"✅ Обложка: {len(cover_bytes)} байт")
        except Exception as e:
            log(f"⚠️ Ошибка загрузки обложки: {e}")
    
    # Генерируем текст поста
    text = generate_post_text(track, album_info)
    if not text:
        log("❌ Не удалось сгенерировать текст")
        return
    
    # Публикуем в ВК
    if cover_bytes:
        # Сохраняем обложку локально
        slug = hashlib.md5(f"{track['id']}".encode()).hexdigest()[:8]
        os.makedirs("img", exist_ok=True)
        img_path = f"img/music_{slug}.jpg"
        with open(img_path, "wb") as f:
            f.write(cover_bytes)
        
        attachment = vk_upload_photo(cover_bytes)
        if attachment:
            vk_post(text, attachment)
        else:
            log("⚠️ Не удалось загрузить фото в ВК — публикую без картинки")
            vk_post(text)
    else:
        vk_post(text)
    
    # Сохраняем в историю
    history.add(track["id"])
    json.dump(list(history), open(HISTORY_FILE, "w", encoding="utf-8"), ensure_ascii=False)
    
    log("=" * 50)
    log("✅ FINISH: пост о песне опубликован в ВК!")
    log("=" * 50)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"❌ КРИТИЧЕСКАЯ ОШИБКА: {e}")
        raise
