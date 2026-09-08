# -*- coding: utf-8 -*-
import os, json, datetime, requests, time, io, glob, urllib3
from PIL import Image
urllib3.disable_warnings()

GROQ_KEY = os.environ.get("GROQ_KEY", "").strip()
OR_KEY   = os.environ.get("OPENROUTER_KEY", "").strip()
GROQ_KEY_T = os.environ.get("GROQ_KEY_TEASER", "").strip() or GROQ_KEY
OR_KEY_T   = os.environ.get("OPENROUTER_KEY_TEASER", "").strip() or OR_KEY

VK_TOKEN = os.environ.get("VK_TOKEN", "").strip()
VK_USER_TOKEN = os.environ.get("VK_USER_TOKEN", "").strip()
VK_GROUP_ID = os.environ.get("VK_GROUP_ID", "").strip().lstrip("-")
TG_TOKEN = os.environ.get("TELEGRAM_TOKEN", "").strip()
TG_CHANNEL = os.environ.get("TELEGRAM_CHANNEL", "").strip()   # @scnote
MAX_TOKEN = os.environ.get("MAX_TOKEN", "").strip()
MAX_CHAT_ID = os.environ.get("MAX_CHAT_ID", "").strip()

VK_API = "https://api.vk.com/method/"
VK_V = "5.131"
POLLINATIONS_API = "https://image.pollinations.ai/prompt/"
MAX_HOSTS = ["https://botapi.max.ru", "https://platform-api2.max.ru"]
TAGS = "#ПавелГнесюк #книги #авторскийблог #писатель"
RU = "\n\nВАЖНО: Пиши ТОЛЬКО на русском языке."
MIN_BRIGHTNESS = 100
MAX_HEADERS = {}

def log(msg):
    print(msg, flush=True)

log("Версия ℹ️ gnesyuk-vk-agent v26 (ВК + TG + MAX; TG → Дзен через zen_sync_bot)")

# ============================================================
# ИИ
# ============================================================

def _extract(r):
    try: return r["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError): return None

def ai_groq(prompt, model, key, suffix=RU):
    if not key: return None
    try:
        r = requests.post("https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={"model": model, "temperature": 0.8,
                  "messages": [{"role": "user", "content": prompt + suffix}]}, timeout=45).json()
        if "error" in r: return None
        return _extract(r)
    except Exception:
        return None

def ai_openrouter(prompt, model, key, suffix=RU):
    if not key: return None
    try:
        r = requests.post("https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}", "HTTP-Referer": "https://github.com"},
            json={"model": model, "temperature": 0.8,
                  "messages": [{"role": "user", "content": prompt + suffix}]}, timeout=45).json()
        if "error" in r: return None
        return _extract(r)
    except Exception:
        return None

def ai_text(prompt, minlen=600):
    models = [
        ("groq", "llama-3.3-70b-versatile", GROQ_KEY_T),
        ("openrouter", "meta-llama/llama-3.3-70b-instruct:free", OR_KEY_T),
        ("openrouter", "google/gemma-3-27b-it:free", OR_KEY_T),
        ("openrouter", "deepseek/deepseek-chat-v3-0324:free", OR_KEY_T),
        ("openrouter", "auto", OR_KEY_T)
    ]
    for provider, model, key in models:
        if not key: continue
        try:
            res = ai_groq(prompt, model, key) if provider == "groq" else ai_openrouter(prompt, model, key)
            if res and len(res) > minlen:
                log(f"✅ Успех: {provider} ({model}), {len(res)} симв.")
                return res
        except Exception:
            pass
    return None

def ai_scene(prompt):
    models = [
        ("groq", "llama-3.3-70b-versatile", GROQ_KEY_T),
        ("openrouter", "meta-llama/llama-3.3-70b-instruct:free", OR_KEY_T),
        ("openrouter", "google/gemma-3-27b-it:free", OR_KEY_T),
        ("openrouter", "deepseek/deepseek-chat-v3-0324:free", OR_KEY_T),
        ("openrouter", "auto", OR_KEY_T)
    ]
    for provider, model, key in models:
        if not key: continue
        try:
            res = ai_groq(prompt, model, key, suffix="") if provider == "groq" else ai_openrouter(prompt, model, key, suffix="")
            if res and len(res) > 15:
                return res.split("\n")[0].strip().strip('"')[:300]
        except Exception:
            pass
    return None

def clean_txt(t):
    return t.replace("**", "").replace("##", "").strip()

def trim_text(t, limit):
    if len(t) <= limit: return t
    c = t[:limit]
    i = max(c.rfind("."), c.rfind("!"), c.rfind("?"), c.rfind("\n"))
    return (c[:i+1] if i > limit//2 else c).rstrip()

def fix_title(t):
    """КАПС -> обычное предложение, <=140 символов, с точкой (правило заголовка Дзена)."""
    t = (t or "").strip()
    if t.isupper():
        out, done = [], False
        for ch in t:
            if not done and ch.isalpha():
                out.append(ch.upper()); done = True
            else:
                out.append(ch.lower())
        t = "".join(out)
    if len(t) > 137:
        t = t[:137].rsplit(" ", 1)[0].rstrip()
    if not t.endswith("."):
        t += "."
    return t

# ============================================================
# ТЕКСТЫ
# ============================================================

def build_long_article(book, mode, day):
    t, a, s = book["title"], book["about"], book["series"]
    base = (f"Напиши развёрнутую статью о романе Павла Гнесюка «{t}» (серия «{s}»). "
            f"Текст ПОЛНОСТЬЮ уникальный, живой, как литературный блог. "
            f"Требования: 1. ТОЛЬКО русский язык. 2. Длина СТРОГО 2500-3800 символов. "
            f"3. Первая строка — заголовок ОБЫЧНЫМИ буквами (только первое слово с заглавной), без ** и ##, БЕЗ капса, не длиннее 140 символов. "
            f"4. Не пиши «как я писал книгу» — пиши как литературный обозреватель. "
            f"5. Никаких ссылок и хэштегов в тексте. ")
    if mode == "quote" and book.get("fragments"):
        fr = book["fragments"][day % len(book["fragments"])]
        prompt = (base + f"Тип: РАЗБОР ЦИТАТЫ. Цитата: «{fr}» — раскрой смысл, атмосферу, связь с сюжетом ({a}). 4-6 абзацев.")
        theme = f"dramatic symbolic scene with ancient flame and golden light: {fr[:60]}"
    elif mode == "hero":
        prompt = (base + f"Тип: ГЕРОИ. Характеры, мотивы, внутренний конфликт героев. Сюжет: {a}. 4-6 абзацев.")
        theme = f"ancient sword and dark cloak on sunlit stone altar, {a[:60]}"
    elif mode == "plot":
        prompt = (base + f"Тип: СЮЖЕТ. Завязка и развитие интриги БЕЗ спойлеров концовки. Сюжет: {a}. 4-6 абзацев.")
        theme = f"sunlit mountain path leading to shining ancient fortress, {a[:60]}"
    elif mode == "world":
        prompt = (base + f"Тип: МИР КНИГИ. Вселенная, атмосфера, правила мира серии «{s}». Сюжет: {a}. 4-6 абзацев.")
        theme = f"epic fantasy landscape with golden sky and ancient ruins, {a[:60]}"
    else:
        prompt = (base + f"Тип: ИНТРИГА. Тайны, вопросы, повороты (без спойлеров), сильный призыв в конце. Сюжет: {a}. 4-6 абзацев.")
        theme = f"warm candlelit desk with old map and shining artifacts, {a[:60]}"
    txt = ai_text(prompt, minlen=1500)
    if not txt:
        log("⚠️ ИИ недоступны. Стандартная статья.")
        txt = (f"Роман «{t}»: история, которая затягивает.\n\n{a}\n\n"
               f"Роман «{t}» из серии «{s}» — захватывающее путешествие, полное тайн и неожиданных поворотов. "
               f"Герои, которым сопереживаешь, мир, в который веришь, и интрига, которая не отпускает до последней страницы.")
    return clean_txt(txt), theme

def build_teaser(book, long_title):
    t, a, s = book["title"], book["about"], book["series"]
    prompt = (f"Напиши тизер для поста о романе Павла Гнесюка «{t}» (серия «{s}»). "
              f"Сюжет: {a}. Требования: 1. ТОЛЬКО русский язык. 2. Первая строка — заголовок ОБЫЧНЫМИ буквами "
              f"(только первое слово с заглавной), без ** и ##, не длиннее 140 символов, и он ОБЯЗАН отличаться от: «{long_title}». "
              f"3. Текст 700-950 символов, интригующий, как анонс. 4. Закончи вопросом или крючком. 5. Без ссылок и хэштегов.")
    txt = ai_text(prompt, minlen=300)
    if not txt:
        log("⚠️ Тизер не создан — беру начало статьи.")
        return None
    return clean_txt(txt)

def build_scene(teaser_text):
    prompt = (f"По этому тексту придумай ОДНУ динамичную сцену для иллюстрации. "
              f"Верни ТОЛЬКО одно предложение на АНГЛИЙСКОМ (15-25 слов): кто и что делает в кадре, "
              f"где происходит, атмосфера и свет. Люди — в действии, в полный рост, НЕ портрет. "
              f"Сцена должна быть СВЕТЛОЙ и КРАСОЧНОЙ: дневной или тёплый золотой свет, яркие цвета, "
              f"никакого тёмного мрачного фэнтези. "
              f"Текст: {teaser_text[:900]}")
    scene = ai_scene(prompt)
    if scene:
        log(f"🎨 Сцена для картинки: {scene[:120]}")
    return scene

# ============================================================
# КАРТИНКА: яркая сцена + контроль яркости
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
        return r.content
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
# САМОДИАГНОСТИКА
# ============================================================

def tg_check():
    if not TG_TOKEN or not TG_CHANNEL:
        log("⚠️ DIAG: TELEGRAM_TOKEN или TELEGRAM_CHANNEL не заданы в env!")
        return False
    try:
        r = requests.get(f"https://api.telegram.org/bot{TG_TOKEN}/getMe", timeout=30).json()
        if not r.get("ok"):
            log(f"⚠️ DIAG: TG токен недействителен: {str(r)[:150]}")
            return False
        log(f"✅ DIAG: TG токен рабочий, бот @{r['result'].get('username')}")
    except Exception as e:
        log(f"⚠️ DIAG: TG getMe ошибка: {e}")
        return False
    if not (TG_CHANNEL.startswith("@") or TG_CHANNEL.startswith("-100")):
        log(f"⚠️ DIAG: TELEGRAM_CHANNEL='{TG_CHANNEL}' — нужно '@имя' или '-100…'")
    return True

def max_check():
    global MAX_HEADERS
    if not MAX_TOKEN:
        log("⚠️ DIAG: MAX_TOKEN не задан в env!")
        return False
    for style in ("plain", "bearer"):
        headers = {"Authorization": MAX_TOKEN} if style == "plain" else {"Authorization": f"Bearer {MAX_TOKEN}"}
        for host in MAX_HOSTS:
            try:
                r = requests.get(host + "/me", headers=headers, timeout=30, verify=False)
                j = r.json()
                if r.status_code == 200 and not j.get("code"):
                    MAX_HEADERS = headers
                    log(f"✅ DIAG: MAX токен рабочий (auth={style})")
                    return True
            except Exception:
                continue
    log("⚠️ DIAG: MAX /me не ответил — проверьте MAX_TOKEN")
    return False

# ============================================================
# ПУБЛИКАЦИИ
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

def vk_upload_photo(img_bytes):
    tok = VK_USER_TOKEN or VK_TOKEN
    if not tok:
        return None
    img_bytes = convert_to_jpeg(img_bytes)
    os.makedirs("img", exist_ok=True)
    day = datetime.date.today().toordinal()
    with open(f"img/vk_{day}.jpg", "wb") as f:
        f.write(img_bytes)
    for params in ({"group_id": VK_GROUP_ID}, {"owner_id": "-" + VK_GROUP_ID}):
        srv = vk_call("photos.getWallUploadServer", params, token=tok)
        if not srv or "upload_url" not in srv:
            continue
        try:
            r = requests.post(srv["upload_url"],
                files={"photo": ("cover.jpg", img_bytes, "image/jpeg")}, timeout=120).json()
        except Exception:
            continue
        if "photo" not in r or "server" not in r or "hash" not in r:
            continue
        sp = dict(params)
        sp.update({"photo": r["photo"], "server": r["server"], "hash": r["hash"]})
        saved = vk_call("photos.saveWallPhoto", sp, token=tok)
        if saved:
            p = saved[0]
            att = f"photo{p['owner_id']}_{p['id']}"
            if p.get("access_key"):
                att += f"_{p['access_key']}"
            log(f"✅ ВК: картинка загружена → {att}")
            return att
    return None

def vk_post_wall(text, attachment=None):
    params = {"owner_id": "-" + VK_GROUP_ID, "message": text, "from_group": 1}
    if attachment:
        params["attachments"] = attachment
    res = vk_call("wall.post", params)
    if res:
        log(f"✅ ВК: пост опубликован: https://vk.com/wall-{VK_GROUP_ID}_{res.get('post_id')}")
        return True
    return False

def tg_send_photo(img_bytes, caption):
    r = requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto",
        data={"chat_id": TG_CHANNEL, "caption": caption},
        files={"photo": ("cover.jpg", img_bytes, "image/jpeg")}, timeout=120).json()
    if not r.get("ok"):
        log(f"⚠️ TG sendPhoto: {str(r)[:200]}")
        return False
    log(f"✅ TG: тизер с картинкой → {TG_CHANNEL}")
    return True

def tg_send_article(text):
    if len(text) > 4096:
        text = text[:4090].rsplit(" ", 1)[0].rstrip() + "…"
    r = requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
        data={"chat_id": TG_CHANNEL, "text": text,
              "disable_web_page_preview": "true"}, timeout=60).json()
    if not r.get("ok"):
        log(f"⚠️ TG sendMessage: {str(r)[:200]}")
        return False
    log(f"✅ TG: полная статья ({len(text)} симв.) → {TG_CHANNEL} → Дзен заберёт как статью")
    return True

def max_api(path, payload=None, params=None):
    errs = []
    for host in MAX_HOSTS:
        try:
            if payload is not None:
                r = requests.post(host + path, headers=MAX_HEADERS, params=params, json=payload, timeout=30, verify=False)
            else:
                r = requests.get(host + path, headers=MAX_HEADERS, params=params, timeout=30, verify=False)
            j = r.json()
            if j.get("code") == "too.many.requests":
                log("⏳ MAX: лимит запросов, жду 4 сек...")
                time.sleep(4)
                continue
            if r.status_code == 200:
                return j
            errs.append(f"{host}:{r.status_code}:{str(j)[:60]}")
        except Exception as e:
            errs.append(f"{host}:{str(e)[:60]}")
    log(f"⚠️ MAX {path}: {' | '.join(errs)}")
    return None

def max_post_channel(caption, poll_url):
    chat_id = None
    chats = max_api("/chats")
    if chats:
        for c in chats.get("chats", []):
            if c.get("type") == "channel":
                chat_id = c.get("chat_id")
                log(f"ℹ️ MAX: канал из списка: {chat_id} «{c.get('title')}»")
                break
    if chat_id is None and MAX_CHAT_ID:
        chat_id = int(MAX_CHAT_ID)
        log(f"ℹ️ MAX: канал из секрета MAX_CHAT_ID: {chat_id}")
    if chat_id is None:
        log("⚠️ MAX: не найден канал (бот не админ? задайте MAX_CHAT_ID)")
        return
    res = max_api("/messages", payload={"text": caption,
                  "attachments": [{"type": "image", "payload": {"url": poll_url}}],
                  "disable_link_preview": True}, params={"chat_id": chat_id})
    if res and res.get("message"):
        log("✅ MAX: пост с картинкой отправлен")
        return
    res = max_api("/messages", payload={"text": caption}, params={"chat_id": chat_id})
    log(f"✅ MAX: отправлен текст: {str(res)[:100]}")

# ============================================================
# ГЛАВНАЯ ЛОГИКА
# ============================================================

def main():
    books = json.load(open("books.json", encoding="utf-8"))["books"]
    day = datetime.date.today().toordinal()
    book = books[day % len(books)]
    modes = ["plot", "hero", "quote", "world", "intrigue"]
    mode = modes[day % len(modes)]
    if mode == "quote" and not book.get("fragments"):
        mode = "plot"
    log(f"📚 Книга дня: «{book['title']}» ({book['series']}) | Тип: {mode}")

    vk_ok = bool(VK_TOKEN and VK_GROUP_ID)
    if not vk_ok:
        log("⚠️ DIAG: VK_TOKEN/VK_GROUP_ID не заданы!")
    tg_ok = tg_check()
    max_ok = max_check()

    long_text, theme = build_long_article(book, mode, day)
    lines = long_text.split("\n")
    headline = fix_title(lines[0].strip())
    content = "\n".join(lines[1:]).strip() if len(lines) > 1 else long_text
    log(f"📰 Заголовок статьи: {headline}")

    teaser = build_teaser(book, headline)
    if teaser is None:
        teaser = trim_text(content, 900)
    tlines = teaser.split("\n")
    tlines[0] = fix_title(tlines[0].strip())
    teaser = "\n".join(tlines)[:1024].rstrip()
    log(f"✂️ Заголовок тизера: {teaser.split(chr(10))[0][:100]}")

    scene = build_scene(teaser)
    base_img = scene if scene else theme
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
            log(f"⚠️ Генерация не удалась — беру яркую прежнюю картинку {candidates[0][1]}")
            with open(candidates[0][1], "rb") as f:
                img_bytes = f.read()

    # --- ВК: тизер + ссылка + хэштеги + картинка ---
    if vk_ok:
        link_part = f"\n\n📖 Читайте на ЛитРес: {book['url']}"
        caption_vk = trim_text(teaser, 2000 - len(link_part) - len(TAGS) - 2) + link_part + "\n\n" + TAGS
        att = vk_upload_photo(img_bytes) if img_bytes else None
        if not att and img_bytes:
            log("⚠️ Картинку загрузить не удалось — пост без картинки")
        vk_post_wall(caption_vk, att)
    else:
        log("⚠️ ВК пропущен")

    # --- TG: тизер с картинкой + полная статья (оттуда zen_sync_bot → Дзен) ---
    if tg_ok and img_bytes:
        tg_send_photo(img_bytes, teaser)
        tg_send_article(headline + "\n\n" + content)
    elif tg_ok:
        tg_send_article(headline + "\n\n" + content)
    else:
        log("⚠️ Telegram пропущен")

    # --- MAX: тизер с картинкой ---
    if max_ok:
        clean_img = "".join(c for c in (scene or theme) if c.isalnum() or c.isspace() or c in ".,-")[:220].strip()
        poll_url = (POLLINATIONS_API + requests.utils.quote(
            "Photorealistic cinematic movie still for russian fantasy novel article, " + clean_img +
            ", bright vivid colors, warm golden daylight, sharp focus, no text") +
            f"?nologo=true&seed={day + 2000000 + (run_no % 100)}&model=flux&width=1280&height=960")
        max_post_channel(teaser, poll_url)
    else:
        log("⚠️ MAX пропущен")

    log("=" * 50)
    log("✅ FINISH: ВК + TG (+ Дзен через zen_sync_bot) + MAX!")
    log("=" * 50)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"❌ КРИТИЧЕСКАЯ ОШИБКА: {e}")
        raise
