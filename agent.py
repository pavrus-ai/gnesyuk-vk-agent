# -*- coding: utf-8 -*-
import os, json, datetime, requests, time

GROQ_KEY = os.environ.get("GROQ_KEY", "")
OR_KEY   = os.environ.get("OPENROUTER_KEY", "")
VK_TOKEN = os.environ.get("VK_TOKEN", "").strip()
VK_GROUP_ID = os.environ.get("VK_GROUP_ID", "").strip().lstrip("-")

VK_API = "https://api.vk.com/method/"
VK_V = "5.131"
POLLINATIONS_API = "https://image.pollinations.ai/prompt/"
TAGS = "#ПавелГнесюк #книги #авторскийблог #писатель"
RU = "\n\nВАЖНО: Пиши ТОЛЬКО на русском языке."

def log(msg):
    print(msg, flush=True)

log("Версия ℹ️ vk-agent v2 (яркие резкие сцены по тексту поста, flux 1280x960)")

def _extract(r):
    try: return r["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError): return None

def ai_groq(prompt, model, suffix=RU):
    if not GROQ_KEY: return None
    try:
        r = requests.post("https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_KEY}"},
            json={"model": model, "temperature": 0.8,
                  "messages": [{"role": "user", "content": prompt + suffix}]}, timeout=45).json()
        if "error" in r: return None
        return _extract(r)
    except Exception:
        return None

def ai_openrouter(prompt, model, suffix=RU):
    if not OR_KEY: return None
    try:
        r = requests.post("https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {OR_KEY}", "HTTP-Referer": "https://github.com"},
            json={"model": model, "temperature": 0.8,
                  "messages": [{"role": "user", "content": prompt + suffix}]}, timeout=45).json()
        if "error" in r: return None
        return _extract(r)
    except Exception:
        return None

def ai_text(prompt, minlen=600):
    models = [
        ("groq", "llama-3.3-70b-versatile"),
        ("openrouter", "meta-llama/llama-3.3-70b-instruct:free"),
        ("openrouter", "google/gemma-3-27b-it:free"),
        ("openrouter", "deepseek/deepseek-chat-v3-0324:free"),
        ("openrouter", "auto")
    ]
    for provider, model in models:
        try:
            res = ai_groq(prompt, model) if provider == "groq" else ai_openrouter(prompt, model)
            if res and len(res) > minlen:
                log(f"✅ Успех: {provider} ({model}), {len(res)} симв.")
                return res
        except Exception:
            pass
    return None

def ai_scene(prompt):
    models = [
        ("groq", "llama-3.3-70b-versatile"),
        ("openrouter", "meta-llama/llama-3.3-70b-instruct:free"),
        ("openrouter", "google/gemma-3-27b-it:free"),
        ("openrouter", "deepseek/deepseek-chat-v3-0324:free"),
        ("openrouter", "auto")
    ]
    for provider, model in models:
        try:
            res = ai_groq(prompt, model, suffix="") if provider == "groq" else ai_openrouter(prompt, model, suffix="")
            if res and len(res) > 15:
                return res.split("\n")[0].strip().strip('"')[:300]
        except Exception:
            pass
    return None

def build_scene(post_text):
    prompt = (f"По этому тексту придумай ОДНУ динамичную сцену для иллюстрации. "
              f"Верни ТОЛЬКО одно предложение на АНГЛИЙСКОМ (15-25 слов): кто и что делает в кадре, "
              f"где происходит, атмосфера и свет. Люди — в действии, в полный рост, НЕ портрет. "
              f"Сцена СВЕТЛАЯ и КРАСОЧНАЯ: дневной или тёплый золотой свет, яркие цвета, "
              f"никакого тёмного мрачного фэнтези. Показывай людей СО СПИНЫ или издалека, лица НЕ видны. "
              f"Текст: {post_text[:900]}")
    scene = ai_scene(prompt)
    if scene:
        log(f"🎨 Сцена для картинки: {scene[:120]}")
    return scene

def clean_txt(t):
    return t.replace("**","").replace("##","").strip()

def trim_text(t, limit):
    if len(t) <= limit: return t
    c = t[:limit]
    i = max(c.rfind("."), c.rfind("!"), c.rfind("?"), c.rfind("\n"))
    return (c[:i+1] if i > limit//2 else c).rstrip()

def build_vk_post(book):
    t, a, s = book["title"], book["about"], book["series"]
    prompt = (f"Напиши пост для сообщества ВКонтакте о романе Павла Гнесюка «{t}» (серия «{s}»). "
              f"Сюжет: {a}. Требования: 1. ТОЛЬКО русский язык. 2. Первая строка — заголовок ЗАГЛАВНЫМИ "
              f"буквами, без ** и ##. 3. Текст 800-1000 символов, интригующий, живой, как анонс. "
              f"4. Закончи вопросом или крючком.")
    txt = ai_text(prompt, minlen=300)
    if not txt:
        log("⚠️ Пост не создан — стандартный текст.")
        txt = (f"РОМАН «{t.upper()}»: ИСТОРИЯ, КОТОРАЯ ЗАТЯГИВАЕТ\n\n{a}")
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

def vk_call(method, params=None):
    p = dict(params or {})
    p["access_token"] = VK_TOKEN
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
    # Способ 1: сервер для стены (групповому токену недоступен)
    srv = vk_call("photos.getWallUploadServer", {"group_id": VK_GROUP_ID})
    if srv and srv.get("upload_url"):
        try:
            r = requests.post(srv["upload_url"],
                              files={"photo": ("cover.jpg", img_bytes, "image/jpeg")}, timeout=120).json()
            saved = vk_call("photos.saveWallPhoto",
                            {"photo": r.get("photo"), "server": r.get("server"),
                             "hash": r.get("hash"), "group_id": VK_GROUP_ID})
            if saved:
                p = saved[0]
                log("✅ ВК: картинка загружена (стена)")
                return f"photo{p['owner_id']}_{p['id']}"
        except Exception as e:
            log(f"⚠️ VK upload wall: {e}")
    # Способ 2: альбом сообщества (работает с групповым токеном)
    srv = vk_call("photos.getUploadServer", {"group_id": VK_GROUP_ID})
    if not srv or not srv.get("upload_url"):
        return None
    try:
        r = requests.post(srv["upload_url"],
                          files={"file": ("cover.jpg", img_bytes, "image/jpeg")}, timeout=120).json()
    except Exception as e:
        log(f"⚠️ VK upload album: {e}")
        return None
    saved = vk_call("photos.save", {"photo": r.get("photo"), "server": r.get("server"),
                                    "hash": r.get("hash"), "group_id": VK_GROUP_ID})
    if not saved:
        return None
    p = saved[0]
    log("✅ ВК: картинка загружена (альбом)")
    return f"photo{p['owner_id']}_{p['id']}"

def vk_post_wall(text, attachment=None):
    params = {"owner_id": "-" + VK_GROUP_ID, "message": text, "from_group": 1}
    if attachment:
        params["attachments"] = attachment
    res = vk_call("wall.post", params)
    if res:
        log(f"✅ ВК: пост опубликован: https://vk.com/wall-{VK_GROUP_ID}_{res.get('post_id')}")
    return res

def main():
    if not VK_TOKEN or not VK_GROUP_ID:
        log("⚠️ Нет VK_TOKEN/VK_GROUP_ID — пропуск ВК")
        return
    books = json.load(open("books.json", encoding="utf-8"))["books"]
    day = datetime.date.today().toordinal()
    book = books[day % len(books)]
    log(f"📚 Книга дня: «{book['title']}» ({book['series']})")

    # Каждый третий день — разбор цитаты, иначе анонс
    if day % 3 == 0 and book.get("fragments"):
        post = build_quote_post(book, day)
    else:
        post = build_vk_post(book)
    log(f"✂️ Заголовок поста: {post.split(chr(10))[0][:150]}")

    link_part = f"\n\n📖 Читайте на ЛитРес: {book['url']}"
    caption = trim_text(post, 2000 - len(link_part) - len(TAGS) - 2) + link_part + "\n\n" + TAGS

    # --- Картинка: яркая, чёткая сцена по тексту поста ---
    scene = build_scene(post)
    base_img = scene if scene else book.get("about", "")[:120]
    clean_img = "".join(c for c in base_img if c.isalnum() or c.isspace() or c in ".,-")[:220].strip()
    p = ("Photorealistic cinematic movie still for russian novel article, "
         + clean_img + ", bright vivid colors, beautiful epic composition, warm golden daylight, "
         "highly detailed, sharp focus, crisp edges, high resolution, full-body figures in action "
         "seen from behind or from a distance, faces NOT visible, no close-up portraits, no text")
    run_no = int(os.environ.get("GITHUB_RUN_NUMBER", "0"))
    seed = day + 3000000 + (run_no % 100)   # свой диапазон — картинки ВК отличаются от других площадок
    url = (POLLINATIONS_API + requests.utils.quote(p) + f"?nologo=true&seed={seed}&model=flux&width=1280&height=960")
    log("Скачивание картинки (flux, 1280x960)...")
    r = requests.get(url, timeout=240)
    r.raise_for_status()
    img_bytes = r.content
    log(f"✅ Картинка: {len(img_bytes)} байт")

    # --- Публикация в группу ВК ---
    att = vk_upload_photo(img_bytes)
    vk_post_wall(caption, att)
    log("=" * 50)
    log("✅ FINISH: пост с картинкой → ВК!")
    log("=" * 50)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"❌ КРИТИЧЕСКАЯ ОШИБКА: {e}")
        raise
