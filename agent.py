# -*- coding: utf-8 -*-
import os, json, datetime, requests, time, io, glob, urllib3
from PIL import Image
urllib3.disable_warnings()

GROQ_KEY = os.environ.get("GROQ_KEY", "").strip()
GROQ_KEY2 = os.environ.get("GROQ_KEY2", "").strip()
OR_KEY = os.environ.get("OPENROUTER_KEY", "").strip()
OR_KEY2 = os.environ.get("OPENROUTER_KEY2", "").strip()
CEREBRAS_KEY = os.environ.get("CEREBRAS_KEY", "").strip()
MISTRAL_KEY = os.environ.get("MISTRAL_KEY", "").strip()
GH_AI_TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()
VK_TOKEN = os.environ.get("VK_TOKEN", "").strip()
VK_USER_TOKEN = os.environ.get("VK_USER_TOKEN", "").strip()
VK_GROUP_ID = os.environ.get("VK_GROUP_ID", "").strip().lstrip("-")
VK_API = "https://api.vk.com/method/"
VK_V = "5.131"
ALBUM_CACHE = "vk_album.json"
POLLINATIONS_API = "https://image.pollinations.ai/prompt/"
TAGS = "#ПавелГнесюк #книги #авторскийблог #писатель"
RU = "\n\nВАЖНО: Пиши ТОЛЬКО на русском языке."
MIN_BRIGHTNESS = 90

def log(msg):
    print(msg, flush=True)

log("Версия ℹ️ vk-agent v9 (книги → ВК: 8 ступеней ИИ + повторы загрузки + альбом группы как запасной путь + обрезка знака)")

# ============================================================
# ИИ: 8 ступеней
# ============================================================

def _extract(r):
    try: return r["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError): return None

def ai_github(prompt):
    if not GH_AI_TOKEN: return None
    endpoints = ["https://models.github.ai/inference/chat/completions",
                 "https://models.inference.ai.azure.com/chat/completions"]
    models = ["openai/gpt-4o-mini", "gpt-4o-mini"]
    for ep in endpoints:
        for mdl in models:
            try:
                r = requests.post(ep,
                    headers={"Authorization": f"Bearer {GH_AI_TOKEN}"},
                    json={"model": mdl, "temperature": 0.8,
                          "messages": [{"role": "user", "content": prompt + RU}]}, timeout=60).json()
                if "error" in r: continue
                res = _extract(r)
                if res: return res
            except Exception:
                continue
    return None

def ai_cerebras(prompt):
    if not CEREBRAS_KEY: return None
    try:
        r = requests.post("https://api.cerebras.ai/v1/chat/completions",
            headers={"Authorization": f"Bearer {CEREBRAS_KEY}"},
            json={"model": "llama-3.3-70b", "temperature": 0.8,
                  "messages": [{"role": "user", "content": prompt + RU}]}, timeout=60).json()
        if "error" in r: return None
        return _extract(r)
    except Exception: return None

def ai_mistral(prompt):
    if not MISTRAL_KEY: return None
    try:
        r = requests.post("https://api.mistral.ai/v1/chat/completions",
            headers={"Authorization": f"Bearer {MISTRAL_KEY}"},
            json={"model": "mistral-small-latest", "temperature": 0.8,
                  "messages": [{"role": "user", "content": prompt + RU}]}, timeout=60).json()
        if "error" in r: return None
        return _extract(r)
    except Exception: return None

def ai_groq(prompt, key):
    if not key: return None
    try:
        r = requests.post("https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={"model": "llama-3.3-70b-versatile", "temperature": 0.8,
                  "messages": [{"role": "user", "content": prompt + RU}]}, timeout=60).json()
        if "error" in r: return None
        return _extract(r)
    except Exception: return None

def ai_openrouter(prompt, model, key):
    if not key: return None
    try:
        r = requests.post("https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}", "HTTP-Referer": "https://github.com"},
            json={"model": model, "temperature": 0.8, "max_tokens": 2000,
                  "messages": [{"role": "user", "content": prompt + RU}]}, timeout=60).json()
        if "error" in r: return None
        return _extract(r)
    except Exception: return None

def ai_text(prompt, minlen=600):
    if not GH_AI_TOKEN:
        log("⚠️ github-models: GITHUB_TOKEN не передан (добавьте в agent.yml)")
    else:
        log("🔄 Попытка: github-models (gpt-4o-mini)...")
        res = ai_github(prompt)
        if res and len(res) > minlen:
            log(f"✅ Успех: github-models, {len(res)} симв.")
            return res
    if not CEREBRAS_KEY:
        log("⚠️ cerebras: CEREBRAS_KEY не передан в env!")
    else:
        log("🔄 Попытка: cerebras (llama-3.3-70b)...")
        res = ai_cerebras(prompt)
        if res and len(res) > minlen:
            log(f"✅ Успех: cerebras, {len(res)} симв.")
            return res
    if not MISTRAL_KEY:
        log("⚠️ mistral: MISTRAL_KEY не передан в env!")
    else:
        log("🔄 Попытка: mistral (mistral-small)...")
        res = ai_mistral(prompt)
        if res and len(res) > minlen:
            log(f"✅ Успех: mistral, {len(res)} симв.")
            return res
    for i, key in enumerate((GROQ_KEY, GROQ_KEY2)):
        if not key: continue
        log(f"🔄 Попытка: groq (llama-3.3-70b-versatile, ключ {i+1})...")
        res = ai_groq(prompt, key)
        if res and len(res) > minlen:
            log(f"✅ Успех: groq (ключ {i+1}), {len(res)} симв.")
            return res
    or_models = ["meta-llama/llama-3.3-70b-instruct:free",
                 "google/gemma-3-27b-it:free",
                 "deepseek/deepseek-chat-v3-0324:free",
                 "auto"]
    for i, key in enumerate((OR_KEY, OR_KEY2)):
        if not key: continue
        for model in or_models:
            log(f"🔄 Попытка: openrouter ({model}, ключ {i+1})...")
            res = ai_openrouter(prompt, model, key)
            if res and len(res) > minlen:
                log(f"✅ Успех: openrouter ({model}, ключ {i+1}), {len(res)} симв.")
                return res
    return None

def clean_txt(t):
    return t.replace("**", "").replace("##", "").strip()

def trim_text(t, limit):
    if len(t) <= limit: return t
    c = t[:limit]
    i = max(c.rfind("."), c.rfind("!"), c.rfind("?"), c.rfind("\n"))
    return (c[:i+1] if i > limit//2 else c).rstrip()

# ============================================================
# ТЕКСТЫ ПОСТОВ
# ============================================================

def build_vk_post(book):
    t, a, s = book["title"], book["about"], book["series"]
    prompt = (f"Напиши пост для сообщества ВКонтакте о романе Павла Гнесюка «{t}» (серия «{s}»). "
              f"Сюжет: {a}. Требования: 1. ТОЛЬКО русский язык. 2. Первая строка — заголовок ЗАГЛАВНЫМИ "
              f"буквами, без ** и ##. 3. Текст 800-1000 символов, интригующий, живой, как анонс. "
              f"4. Закончи вопросом или крючком.")
    txt = ai_text(prompt, minlen=300)
    if not txt:
        log("⚠️ Пост не создан — стандартный текст.")
        txt = f"РОМАН «{t.upper()}»: ИСТОРИЯ, КОТОРАЯ ЗАТЯГИВАЕТ\n\n{a}"
    return clean_txt(txt)

def build_quote_post(book, day):
    fr = book["fragments"][day % len(book["fragments"])]
    prompt = (f"Напиши пост для ВКонтакте: разбор цитаты из романа Павла Гнесюка «{book['title']}». "
              f"Цитата: «{fr}». Требования: 1. ТОЛЬКО русский язык. 2. Первая строка — заголовок ЗАГЛАВНЫМИ, "
              f"без ** и ##. 3. 600-900 символов: раскрой смысл цитаты, атмосферу и интригу романа. "
              f"4. Сама цитата должна войти в текст поста.")
    txt = ai_text(prompt, minlen=250)
    if not txt:
        log("⚠️ Разбор цитаты не создан — стандартный пост.")
        return build_vk_post(book)
    return clean_txt(txt)

def build_scene(post):
    prompt = (f"Из текста ниже выбери ОДНУ атмосферную сцену и опиши её в 1-2 предложениях "
              f"БЕЗ ЛЮДЕЙ и без лиц: только место, предметы, природа, погода, свет, детали интерьера.\n\n"
              f"ТЕКСТ: {post[:1500]}")
    return ai_text(prompt, minlen=30)

# ============================================================
# КАРТИНКИ + обрезка водяного знака
# ============================================================

def image_stats(img_bytes):
    try:
        im = Image.open(io.BytesIO(img_bytes))
        im.verify()
        im = Image.open(io.BytesIO(img_bytes)).convert("L")
        im.thumbnail((64, 64))
        px = im.tobytes()
        return True, sum(px) / len(px)
    except Exception:
        return False, 0.0

def strip_watermark(img_bytes):
    try:
        im = Image.open(io.BytesIO(img_bytes))
        w, h = im.size
        cut = int(h * 0.09)
        im = im.crop((0, 0, w, h - cut))
        buf = io.BytesIO()
        im.convert("RGB").save(buf, "JPEG", quality=90)
        log(f"✂️ Водяной знак: срезана нижняя полоса {cut}px (было {w}x{h}, стало {im.size[0]}x{im.size[1]})")
        return buf.getvalue()
    except Exception as e:
        log(f"⚠️ strip_watermark: {e}")
        return img_bytes

def download_image(scene_text, seed):
    clean_img = "".join(c for c in scene_text if c.isalnum() or c.isspace() or c in ".,-")[:220].strip()
    p = ("Wide-angle cinematic landscape photograph, absolutely NO people, NO faces, NO portraits, "
         "bright vivid saturated colors, high contrast, warm golden daylight, crisp sharp details. "
         "Scene: " + clean_img + ". "
         "Empty space without humans, only environment and objects, eye-level wide shot, "
         "no text, no watermark")
    url = (POLLINATIONS_API + requests.utils.quote(p) +
           f"?nologo=true&seed={seed}&model=flux&width=1280&height=960")
    try:
        r = requests.get(url, timeout=240)
        r.raise_for_status()
        ok, bright = image_stats(r.content)
        if not ok:
            log(f"⚠️ Pollinations вернул не картинку (seed={seed})")
            return None
        log(f"🔆 Яркость картинки: {bright:.0f} (порог {MIN_BRIGHTNESS})")
        if bright < MIN_BRIGHTNESS:
            log(f"⚠️ Слишком тёмная картинка (seed={seed}) — отбракована")
            return None
        log(f"✅ Картинка: {len(r.content)} байт (seed={seed})")
        return strip_watermark(r.content)
    except Exception as e:
        log(f"⚠️ Ошибка скачивания картинки (seed={seed}): {e}")
        return None

def convert_to_jpeg(img_bytes):
    try:
        im = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=92)
        return buf.getvalue()
    except Exception:
        return img_bytes

# ============================================================
# ВК v9: путь 1 (wall server с повторами) → путь 2 (альбом группы)
# ============================================================

def vk_call(method, params=None, token=None):
    p = dict(params or {})
    p["access_token"] = token or VK_TOKEN
    p["v"] = VK_V
    try:
        r = requests.post(VK_API + method, data=p, timeout=30).json()
    except Exception as e:
        log(f"⚠️ VK {method}: {e}")
        return None
    if "error" in r:
        log(f"⚠️ VK {method}: {str(r.get('error'))[:150]}")
        return None
    return r.get("response")

def vk_get_album_id():
    """ID альбома книжной группы: секрет VK_ALBUM_ID → файл vk_album.json."""
    env_id = os.environ.get("VK_ALBUM_ID", "").strip()
    if env_id.isdigit():
        return int(env_id)
    try:
        d = json.load(open(ALBUM_CACHE, encoding="utf-8"))
        if d.get("album_id"):
            return d["album_id"]
    except Exception:
        pass
    return None

def vk_upload_via_album(img_bytes):
    """Запасной путь: загрузка в альбом группы (минует флуд getWallUploadServer)."""
    album = vk_get_album_id()
    if not album:
        log("ℹ️ ВК: путь 2 пропущен (нет VK_ALBUM_ID / vk_album.json)")
        return None
    for tok in (VK_USER_TOKEN, VK_TOKEN):
        if not tok:
            continue
        srv = vk_call("photos.getUploadServer",
                      {"group_id": VK_GROUP_ID, "album_id": album}, token=tok)
        if not srv or "upload_url" not in srv:
            continue
        try:
            r = requests.post(srv["upload_url"],
                files={"file1": ("cover.jpg", img_bytes, "image/jpeg")}, timeout=120).json()
        except Exception:
            continue
        if not r.get("hash") or not r.get("photos_list"):
            log(f"⚠️ ВК upload в альбом: пустой ответ: {str(r)[:120]}")
            continue
        saved = vk_call("photos.savePhotos",
                        {"group_id": VK_GROUP_ID, "album_id": album,
                         "server": r.get("server", ""), "photos_list": r.get("photos_list", ""),
                         "hash": r.get("hash", "")}, token=tok)
        if saved:
            p = saved[0]
            att = f"photo{p['owner_id']}_{p['id']}"
            if p.get("access_key"):
                att += f"_{p['access_key']}"
            return att
    return None

def vk_upload_photo(img_bytes):
    tok = VK_USER_TOKEN or VK_TOKEN
    if not tok:
        log("⚠️ ВК: нет VK_USER_TOKEN — пост без фото")
        return None
    img_bytes = convert_to_jpeg(img_bytes)
    os.makedirs("img", exist_ok=True)
    day = datetime.date.today().toordinal()
    with open(f"img/vk_{day}.jpg", "wb") as f:
        f.write(img_bytes)
    # Путь 1: wall upload server, 2 раунда с паузой
    for rnd in range(2):
        for params in ({"group_id": VK_GROUP_ID}, {"owner_id": "-" + VK_GROUP_ID}):
            srv = vk_call("photos.getWallUploadServer", params, token=tok)
            if not srv or "upload_url" not in srv:
                continue
            try:
                r = requests.post(srv["upload_url"],
                    files={"photo": ("cover.jpg", img_bytes, "image/jpeg")}, timeout=120).json()
            except Exception:
                continue
            if not r.get("photo"):
                log(f"⚠️ VK upload вернул пустое photo (раунд {rnd+1}) — флуд")
                continue
            if "server" not in r or "hash" not in r:
                continue
            sp = dict(params)
            sp.update({"photo": r["photo"], "server": r["server"], "hash": r["hash"]})
            saved = vk_call("photos.saveWallPhoto", sp, token=tok)
            if saved:
                p = saved[0]
                att = f"photo{p['owner_id']}_{p['id']}"
                if p.get("access_key"):
                    att += f"_{p['access_key']}"
                log(f"✅ ВК: картинка загружена (wall server) → {att}")
                return att
        if rnd == 0:
            log("⏳ ВК: пауза 15 сек перед повтором (раунд 1/2)")
            time.sleep(15)
    # Путь 2: альбом группы
    att = vk_upload_via_album(img_bytes)
    if att:
        log(f"✅ ВК: картинка загружена (через альбом группы) → {att}")
        return att
    return None

def vk_post_wall(text, attachment=None):
    params = {"owner_id": "-" + VK_GROUP_ID, "message": text, "from_group": 1}
    if attachment:
        params["attachments"] = attachment
    res = vk_call("wall.post", params)
    if res:
        log(f"✅ ВК: пост опубликован: https://vk.com/wall-{VK_GROUP_ID}_{res.get('post_id')}")
        return res

# ============================================================
# ГЛАВНАЯ ЛОГИКА
# ============================================================

def main():
    if not VK_TOKEN or not VK_GROUP_ID:
        log("⚠️ Нет VK_TOKEN/VK_GROUP_ID — пропуск ВК")
        return
    books = json.load(open("books.json", encoding="utf-8"))["books"]
    day = datetime.date.today().toordinal()
    book = books[day % len(books)]
    log(f"📚 Книга дня: «{book['title']}» ({book['series']})")

    if day % 3 == 0 and book.get("fragments"):
        post = build_quote_post(book, day)
    else:
        post = build_vk_post(book)
    log(f"✂️ Заголовок поста: {post.split(chr(10))[0][:150]}")
    link_part = f"\n\n📖 Читайте на ЛитРес: {book['url']}"
    caption = trim_text(post, 2000 - len(link_part) - len(TAGS) - 2) + link_part + "\n\n" + TAGS

    scene = build_scene(post)
    base_img = scene if scene else book.get("about", "")[:120]
    run_no = int(os.environ.get("GITHUB_RUN_NUMBER", "0"))
    img_bytes = None
    for attempt in range(4):
        seed = day + 3000000 + (run_no % 100) + attempt * 7919
        img_bytes = download_image(base_img, seed)
        if img_bytes:
            break
        log(f"⏳ Попытка {attempt + 1} не удалась, пробуем снова...")

    if not img_bytes:
        candidates = []
        for f in glob.glob("img/vk_*.jpg"):
            with open(f, "rb") as fh:
                ok, bright = image_stats(fh.read())
            if ok and bright >= MIN_BRIGHTNESS:
                candidates.append((bright, f))
        if candidates:
            candidates.sort(reverse=True)
            pick = candidates[0][1]
            log(f"⚠️ Генерация не удалась — беру прежнюю картинку {pick} и срезаю знак")
            with open(pick, "rb") as f:
                img_bytes = strip_watermark(f.read())
        else:
            log("⚠️ Нет ни свежей, ни подходящей старой картинки")

    att = vk_upload_photo(img_bytes) if img_bytes else None
    if not att:
        log("⚠️ Картинку загрузить не удалось — пост выйдет без картинки")
    vk_post_wall(caption, att)

    log("=" * 50)
    log("✅ FINISH: пост о книге → ВК!" + (" (с картинкой без знака)" if att else " (БЕЗ картинки!)"))
    log("=" * 50)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"❌ КРИТИЧЕСКАЯ ОШИБКА: {e}")
        raise
