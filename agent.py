# -*- coding: utf-8 -*-
import os, json, datetime, requests, time, urllib3
urllib3.disable_warnings()

GROQ_KEY = os.environ.get("GROQ_KEY", "").strip()
OR_KEY   = os.environ.get("OPENROUTER_KEY", "").strip()
GROQ_KEY_T = os.environ.get("GROQ_KEY_TEASER", "").strip() or GROQ_KEY
OR_KEY_T   = os.environ.get("OPENROUTER_KEY_TEASER", "").strip() or OR_KEY

TG_TOKEN = os.environ.get("TELEGRAM_TOKEN", "").strip()
TG_CHANNEL = os.environ.get("TELEGRAM_CHANNEL", "").strip()   # @scnote
MAX_TOKEN = os.environ.get("MAX_TOKEN", "").strip()
MAX_CHAT_ID = os.environ.get("MAX_CHAT_ID", "").strip()

POLLINATIONS_API = "https://image.pollinations.ai/prompt/"
MAX_HOSTS = ["https://botapi.max.ru", "https://platform-api2.max.ru"]
RU = "\n\nВАЖНО: Пиши ТОЛЬКО на русском языке."
MAX_HEADERS = {}

def log(msg):
    print(msg, flush=True)

log("Версия ℹ️ pavel-gnesyuk-dzen v25 (статьи и тизеры → scnote → Дзен через zen_sync_bot; без RSS и сайта)")

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
# САМОДИАГНОСТИКА
# ============================================================

def tg_check():
    if not TG_TOKEN or not TG_CHANNEL:
        log("⚠️ DIAG: TELEGRAM_TOKEN или TELEGRAM_CHANNEL не заданы!")
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
        log("⚠️ DIAG: MAX_TOKEN не задан!")
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
# ПУБЛИКАЦИИ
# ============================================================

def tg_send_photo(img_bytes, caption):
    r = requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto",
        data={"chat_id": TG_CHANNEL, "caption": caption},
        files={"photo": ("cover.jpg", img_bytes, "image/jpeg")}, timeout=120).json()
    if not r.get("ok"):
        log(f"⚠️ TG sendPhoto: {str(r)[:200]}")
        return False
    log("✅ Тизер с картинкой → scnote")
    return True

def tg_send_article(text):
    if len(text) > 4096:
        text = text[:4090].rsplit(" ", 1)[0].rstrip() + "…"
    r = requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
        data={"chat_id": TG_CHANNEL, "text": text,
              "disable_web_page_preview": "true"}, timeout=60).json()
    if not r.get("ok"):
        log(f"❌ TG sendMessage: {str(r)[:200]}")
        return False
    log(f"✅ Полная статья ({len(text)} симв.) → scnote → Дзен заберёт как статью")
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

def max_post_channel(caption, img_url, poll_url):
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
    for i, u in enumerate([poll_url, img_url], 1):
        body = {"text": caption,
                "attachments": [{"type": "image", "payload": {"url": u}}],
                "disable_link_preview": True}
        res = max_api("/messages", payload=body, params={"chat_id": chat_id})
        if res and res.get("message"):
            log(f"✅ MAX: пост с картинкой отправлен (вариант {i})")
            return
        log(f"⚠️ MAX: вариант {i} не прошёл: {str(res)[:80]}")
        time.sleep(2)
    res = max_api("/messages", payload={"text": caption}, params={"chat_id": chat_id})
    log(f"✅ MAX: отправлен текст без картинки: {str(res)[:100]}")

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
    teaser = "\n".join(tlines)
    teaser = teaser[:1024].rstrip()
    log(f"✂️ Заголовок тизера: {teaser.split(chr(10))[0][:100]}")

    scene = build_scene(teaser)
    base_img = scene if scene else theme
    clean_img = "".join(c for c in base_img if c.isalnum() or c.isspace() or c in ".,-")[:220].strip()
    p = ("Photorealistic cinematic movie still for russian fantasy novel article, "
         + clean_img + ", bright vivid colors, beautiful epic composition, warm golden daylight, "
         "highly detailed, sharp focus, crisp edges, high resolution, full-body figures in action, "
         "no close-up portraits, no text")
    run_no = int(os.environ.get("GITHUB_RUN_NUMBER", "0"))
    seed = day + 2000000 + (run_no % 100)
    url = (POLLINATIONS_API + requests.utils.quote(p) +
           f"?nologo=true&seed={seed}&model=flux&width=1280&height=960")
    log("Скачивание картинки (flux, 1280x960)...")
    r = requests.get(url, timeout=240)
    r.raise_for_status()
    img_bytes = r.content
    log(f"✅ Картинка: {len(img_bytes)} байт")

    if tg_ok:
        tg_send_photo(img_bytes, teaser)
        tg_send_article(headline + "\n\n" + content)
    else:
        log("⚠️ Telegram пропущен (см. DIAG выше)")
    if max_ok:
        max_post_channel(teaser, "", url)
    else:
        log("⚠️ MAX пропущен (см. DIAG выше)")

    log("=" * 50)
    log("✅ FINISH: тизер+статья → scnote → Дзен (zen_sync_bot), тизер → MAX!")
    log("=" * 50)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"❌ КРИТИЧЕСКАЯ ОШИБКА: {e}")
        raise
