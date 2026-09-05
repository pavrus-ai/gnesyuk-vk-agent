# -*- coding: utf-8 -*-
import os, json, random, requests, hashlib, io, urllib.parse
try:
    from PIL import Image
    PIL_OK = True
except Exception:
    PIL_OK = False

VK_TOKEN = os.getenv("VK_TOKEN", "")
VK_USER_TOKEN = os.getenv("VK_USER_TOKEN", "")
VK_GROUP = os.getenv("VK_GROUP_ID", "").strip().lstrip("-")
GROQ_KEY = os.getenv("GROQ_KEY", "")
OR_KEY = os.getenv("OPENROUTER_KEY", "")

MUSIC_FILE = "music.json"
HISTORY_FILE = "music_history.json"
POLLINATIONS_API = "https://image.pollinations.ai/prompt/"
COVERS_BASE = "https://raw.githubusercontent.com/pavrus-ai/gnesyuk-vk-agent/main/covers/"

# Соответствие альбомов файлам обложек в папке covers/
COVER_FILES = {
    "Оставим грусть. С Новым Годом!": "ostavim-grust.jpg",
    "Горячий песок Египта": "goryachiy-pesok-egipta.jpg",
    "Дар богов": "dar-bogov.jpg",
    "Imperium": "imperium.jpg",
    "Энергия для души": "energiya-dlya-dushi.jpg",
    "Бездна": "bezdna.jpg",
    "Тишина вместо слов": "tishina-vmesto-slov.jpg",
    "Управление чувствами": "upravlenie-chuvstvami.jpg",
    "Небесный страж": "nebesnyy-strazh.jpg",
    "Пленники Хроноса": "plenniki-khronosa.jpg",
    "Поколение ветра": "pokolenie-vetra.jpg",
    "Туманные зеркала": "tumannye-zerkala.jpg",
    "Раскаленный мир": "raskalennyy-mir.jpg",
    "Обжигающий": "obzhigayushchiy.jpg",
    "Лекарство от печали": "lekarstvo-ot-pechali.jpg",
    "Пока ты ждёшь": "poka-ty-zhdesh.jpg",
    "Весенние чувства": "vesennie-chuvstva.jpg",
    "Тени Великой Тартарии": "teni-velikoy-tartarii.jpg",
    "Spirit": "spirit.jpg",
    "Enjoyments": "enjoyments.jpg",
    "Турецкие мотивы": "turetskie-motivy.jpg",
    "Прикосновения": "prikosnoveniya.jpg",
    "Истоки славы": "istoki-slavy.jpg",
    "Цена тишины": "tsena-tishiny.jpg",
    "Под одним небом": "pod-odnim-nebom.jpg",
    "Дух свободы": "dukh-svobody.jpg",
    "Gloria Romae": "gloria-romae.jpg",
    "Gloria Romae II": "gloria-romae-2.jpg",
    "Сибирский ветер": "sibirskiy-veter.jpg",
    "Чувственный горизонт": "chuvstvennyy-gorizont.jpg",
    "Твой свет": "tvoy-svet.jpg",
    "Дух возвращается": "dukh-vozvrashchaetsya.jpg",
    "Энергия существует": "energiya-sushchestvuet.jpg",
    "Тёплый свет": "tyoplyy-svet.jpg",
    "Россия матушка зовет (folk garmonica)": "rossiya-matushka-zovet.jpg",
    "Шторм и штиль": "shtorm-i-shtil.jpg"
}

def log(msg):
    print(msg, flush=True)

log("Версия ℹ️ music-agent v5 (music.json + covers/ + генерация 1:1)")

def _extract(r):
    try: return r["choices"][0]["message"]["content"].strip()
    except Exception: return None

def ai_call(prompt):
    models = [
        ("groq", "llama-3.3-70b-versatile", GROQ_KEY),
        ("openrouter", "meta-llama/llama-3.3-70b-instruct:free", OR_KEY),
        ("openrouter", "google/gemma-3-27b-it:free", OR_KEY),
        ("openrouter", "auto", OR_KEY)
    ]
    for provider, model, key in models:
        if not key: continue
        try:
            url = "https://api.groq.com/openai/v1/chat/completions" if provider == "groq" else "https://openrouter.ai/api/v1/chat/completions"
            headers = {"Authorization": f"Bearer {key}"}
            if provider == "openrouter": headers["HTTP-Referer"] = "https://github.com"
            r = requests.post(url, headers=headers, json={
                "model": model, "temperature": 0.8, "max_tokens": 800,
                "messages": [{"role": "user", "content": prompt + "\n\nВАЖНО: Пиши ТОЛЬКО на русском языке."}]
            }, timeout=45).json()
            if "error" not in r and "choices" in r:
                text = _extract(r)
                if text and 300 <= len(text) <= 750:
                    log(f"✅ Текст: {provider} ({model}), {len(text)} симв.")
                    return text
        except Exception:
            continue
    return None

def generate_text(track, album):
    coauthors = album.get("coauthors", [])
    co_text = f"Учти коллаборацию с {', '.join(coauthors)}. " if coauthors else ""
    song_info = track.get("about", "") or f"название «{track['title']}»"
    prompt = (
        f"Напиши пост о песне Павла Гнесюка для группы ВКонтакте.\n\n"
        f"ПЕСНЯ: «{track['title']}»\n"
        f"О ПЕСНЕ: {song_info}\n"
        f"АЛЬБОМ: «{album['title']}» ({album.get('type', 'альбом')}, {album.get('genre', '')}, {album.get('year', '')})\n"
        f"ОБ АЛЬБОМЕ: {album.get('about', '')}\n"
        f"СОАВТОРЫ: {', '.join(coauthors) if coauthors else 'сольно'}\n\n"
        f"ТРЕБОВАНИЯ:\n"
        f"1. ТОЛЬКО русский язык.\n"
        f"2. Длина СТРОГО 350-650 символов.\n"
        f"3. Начни с описания песни: о чём она, настроение, атмосфера. {co_text}\n"
        f"4. Добавь 1-2 предложения про смысл и атмосферу альбома.\n"
        f"5. В конце обязательно: 🎧 Слушать: {album['url']}\n"
        f"6. Стиль живой, искренний, без пафоса.\n"
        f"7. Хэштеги только: #ПавелГнесюк #музыка"
    )
    text = ai_call(prompt)
    if not text:
        log("⚠️ ИИ недоступен — шаблонный текст")
        text = (f"🎵 «{track['title']}» — трек из альбома «{album['title']}».\n\n"
                f"{album.get('about', '')}\n\n"
                f"🎧 Слушать: {album['url']}\n\n#ПавелГнесюк #музыка")
    return text

def get_cover(album, track):
    # 1. Ссылка из music.json
    url = album.get("cover", "")
    if url:
        try:
            r = requests.get(url, timeout=30)
            if r.headers.get("content-type", "").startswith("image") and len(r.content) > 1000:
                log(f"✅ Обложка по ссылке: {len(r.content)} байт")
                return r.content
        except Exception as e:
            log(f"⚠️ Обложка по ссылке не скачалась: {e}")
    # 2. Файл из папки covers/ репозитория
    fname = COVER_FILES.get(album.get("title", ""), "")
    if fname:
        try:
            r = requests.get(COVERS_BASE + fname, timeout=30)
            if r.status_code == 200 and len(r.content) > 1000:
                log(f"✅ Обложка из covers/: {fname}")
                return r.content
        except Exception:
            pass
    # 3. Генерация квадратной обложки 1:1
    log("🎨 Генерирую квадратную обложку (1:1)...")
    coauthors = f", feat. {', '.join(album.get('coauthors', []))}" if album.get("coauthors") else ""
    p = (f"Square album artwork for {album.get('genre', 'rock')} music '{track['title']}' by Pavel Gnesyuk{coauthors}, "
         f"mood: {album.get('about', '')[:120]}, bright vivid colors, beautiful composition, "
         f"no text, no letters, no words")
    seed = random.randint(1, 999999)
    u = POLLINATIONS_API + urllib.parse.quote(p) + f"?nologo=true&seed={seed}&model=flux&width=1024&height=1024"
    try:
        r = requests.get(u, timeout=240)
        if r.headers.get("content-type", "").startswith("image"):
            log(f"✅ Сгенерированная обложка: {len(r.content)} байт")
            return r.content
    except Exception as e:
        log(f"⚠️ Ошибка генерации обложки: {e}")
    return b""

def vk_call(method, params=None, token=None):
    p = dict(params or {})
    p["access_token"] = token or VK_TOKEN
    p["v"] = "5.131"
    try:
        r = requests.post("https://api.vk.com/method/" + method, data=p, timeout=30).json()
    except Exception as e:
        log(f"⚠️ VK {method}: {e}")
        return None
    if "error" in r:
        log(f"⚠️ VK {method}: {str(r.get('error'))[:150]}")
        return None
    return r.get("response")

def vk_upload_photo(img_bytes):
    tok = VK_USER_TOKEN or VK_TOKEN
    if not tok:
        log("⚠️ Нет токена для загрузки фото")
        return None
    if PIL_OK:
        try:
            im = Image.open(io.BytesIO(img_bytes)).convert("RGB")
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=92)
            img_bytes = buf.getvalue()
            log(f"✅ Конвертировано в JPEG: {len(img_bytes)} байт")
        except Exception as e:
            log(f"⚠️ JPEG-конвертация: {e}")
    srv = vk_call("photos.getWallUploadServer", {"group_id": VK_GROUP}, token=tok)
    if not srv or not srv.get("upload_url"):
        log(f"⚠️ Не получен upload_url: {srv}")
        return None
    try:
        r = requests.post(srv["upload_url"],
            files={"photo": ("cover.jpg", img_bytes, "image/jpeg")}, timeout=120).json()
        if "photo" not in r or "server" not in r or "hash" not in r:
            log(f"⚠️ Ошибка загрузки фото: {str(r)[:150]}")
            return None
        saved = vk_call("photos.saveWallPhoto",
            {"photo": r["photo"], "server": r["server"], "hash": r["hash"], "group_id": VK_GROUP},
            token=tok)
        if saved and len(saved) > 0:
            p = saved[0]
            acc = p.get("access_key", "")
            att = f"photo{p['owner_id']}_{p['id']}"
            if acc: att += f"_{acc}"
            log(f"✅ ВК: обложка загружена → {att}")
            return att
    except Exception as e:
        log(f"⚠️ VK upload: {e}")
    return None

def vk_post(message, attachment=None):
    params = {"owner_id": "-" + VK_GROUP, "message": message, "from_group": 1}
    if attachment:
        params["attachments"] = attachment
    res = vk_call("wall.post", params)
    if res:
        log(f"✅ ВК: пост опубликован: https://vk.com/wall-{VK_GROUP}_{res.get('post_id')}")
        return True
    return False

def load_albums():
    raw = open(MUSIC_FILE, encoding="utf-8").read().strip()
    try:
        return json.loads(raw)["albums"]
    except Exception:
        log("⚠️ music.json из двух частей — склеиваю автоматически")
        dec = json.JSONDecoder()
        data1, end1 = dec.raw_decode(raw)
        albums = data1["albums"]
        rest = raw[end1:].strip()
        if rest:
            if rest.startswith("}"):
                rest = rest[1:]
            if rest.startswith(","):
                rest = rest[1:]
            data2 = json.loads('{"albums":[' + rest)
            albums += data2["albums"]
        log(f"✅ Склеено: всего альбомов {len(albums)}")
        return albums

def main():
    try:
        albums = load_albums()
    except Exception as e:
        log(f"❌ Ошибка чтения music.json: {e}")
        return

    try:
        hist = set(json.load(open(HISTORY_FILE, encoding="utf-8"))) if os.path.exists(HISTORY_FILE) else set()
    except Exception:
        hist = set()

    pairs = [(a, s) for a in albums for s in a["songs"] if f"{a['title']}||{s['title']}" not in hist]
    if not pairs:
        log("🔄 Вся история пройдена — начинаю заново")
        hist.clear()
        pairs = [(a, s) for a in albums for s in a["songs"]]

    album, track = random.choice(pairs)
    log(f"🎵 Альбом: «{album['title']}» ({album.get('genre', '')}, {album.get('year', '')})")
    log(f"🎶 Трек: «{track['title']}»")
    if album.get("coauthors"):
        log(f"👥 Соавторы: {', '.join(album['coauthors'])}")

    text = generate_text(track, album)
    cover = get_cover(album, track)

    if cover:
        os.makedirs("img", exist_ok=True)
        slug = hashlib.md5(f"{album['title']}-{track['title']}".encode()).hexdigest()[:8]
        with open(f"img/music_{slug}.jpg", "wb") as f:
            f.write(cover)
        log(f"💾 Сохранено локально: img/music_{slug}.jpg")
        att = vk_upload_photo(cover)
        if att:
            vk_post(text, att)
        else:
            log("⚠️ Фото не загрузилось — пост без картинки")
            vk_post(text)
    else:
        vk_post(text)

    hist.add(f"{album['title']}||{track['title']}")
    json.dump(list(hist), open(HISTORY_FILE, "w", encoding="utf-8"), ensure_ascii=False)

    log("=" * 50)
    log("✅ FINISH: пост о музыке опубликован в ВК!")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"❌ КРИТИЧЕСКАЯ ОШИБКА: {e}")
        raise
