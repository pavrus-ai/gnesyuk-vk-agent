# -*- coding: utf-8 -*-
import os, json, datetime, requests, time, io, glob
from PIL import Image

GROQ_KEY = os.environ.get("GROQ_KEY", "")
OR_KEY   = os.environ.get("OPENROUTER_KEY", "")
VK_TOKEN = os.environ.get("VK_TOKEN", "").strip()
VK_USER_TOKEN = os.environ.get("VK_USER_TOKEN", "").strip()
VK_GROUP_ID = os.environ.get("VK_GROUP_ID", "").strip().lstrip("-")
VK_API = "https://api.vk.com/method/"
VK_V = "5.131"
POLLINATIONS_API = "https://image.pollinations.ai/prompt/"
TAGS = "#ПавелГнесюк #книги #авторскийблог #писатель"
RU = "\n\nВАЖНО: Пиши ТОЛЬКО на русском языке."

def log(msg):
    print(msg, flush=True)

log("Версия ℹ️ vk-agent v4 (надёжная картинка: ретраи + owner_id + фолбэк)")

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

# ============================================================
# ТЕКСТОВЫЕ ХЕЛПЕРЫ
# ============================================================

def clean_txt(txt):
    """Убирает markdown-мусор из ответа нейросети."""
    lines = []
    for ln in txt.splitlines():
        ln = ln.replace("**", "").replace("##", "").replace("###", "")
        lines.append(ln.rstrip())
    out = "\n".join(lines).strip()
    while "\n\n\n" in out:
        out = out.replace("\n\n\n", "\n\n")
    return out

def trim_text(txt, limit):
    """Обрезает текст по границе слов, не превышая limit."""
    if len(txt) <= limit:
        return txt
    cut = txt[:limit]
    if " " in cut:
        cut = cut[:cut.rfind(" ")]
    return cut.rstrip() + "…"

def build_scene(post):
    """Просит ИИ выделить одну кинематографичную сцену для картинки."""
    prompt = (f"Из текста ниже выбери ОДНУ яркую зрительную сцену и опиши её в 1-2 предложениях "
              f"для генерации картинки: место, действие, освещение, атмосфера. Без имён и цитат.\n\n"
              f"ТЕКСТ: {post[:1500]}")
    res = ai_text(prompt, minlen=30)
    return res

# ============================================================
# ПОСТЫ
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

# ============================================================
# VK API
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

# ============================================================
# КАРТИНКИ: генерация, проверка, загрузка
# ============================================================

def convert_to_jpeg(img_bytes):
    try:
        im = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=92)
        result = buf.getvalue()
        log(f"✅ Конвертировано в JPEG: {len(result)} байт (было {len(img_bytes)})")
        return result
    except Exception as e:
        log(f"⚠️ Ошибка конвертации JPEG: {e}")
        return img_bytes

def is_valid_image(img_bytes):
    """Проверяет, что байты — настоящая картинка."""
    try:
        im = Image.open(io.BytesIO(img_bytes))
        im.verify()
        return True
    except Exception:
        return False

def download_image(prompt, seed):
    """Скачивает картинку с pollinations с проверкой результата."""
    clean_img = "".join(c for c in prompt if c.isalnum() or c.isspace() or c in ".,-")[:220].strip()
    p = ("Photorealistic cinematic movie still for russian novel article, "
         + clean_img + ", bright vivid colors, beautiful epic composition, warm golden daylight, "
         "highly detailed, sharp focus, crisp edges, high resolution, full-body figures in action "
         "seen from behind or from a distance, faces NOT visible, no close-up portraits, no text")
    url = (POLLINATIONS_API + requests.utils.quote(p) +
           f"?nologo=true&seed={seed}&model=flux&width=1280&height=960")
    try:
        r = requests.get(url, timeout=240)
        r.raise_for_status()
        if is_valid_image(r.content):
            log(f"✅ Картинка: {len(r.content)} байт (seed={seed})")
            return r.content
        log(f"⚠️ Pollinations вернул не картинку (seed={seed})")
    except Exception as e:
        log(f"⚠️ Ошибка скачивания картинки (seed={seed}): {e}")
    return None

def vk_upload_photo(img_bytes):
    """Загрузка фото на стену группы.
    НОВОЕ в v4: сначала пробуем owner_id (отрицательный) — эта комбинация
    доказанно работает с пользовательским токеном; group_id — запасной вариант."""
    tok = VK_USER_TOKEN or VK_TOKEN
    if not tok:
        log("⚠️ Нет токена для загрузки фото")
        return None

    img_bytes = convert_to_jpeg(img_bytes)

    os.makedirs("img", exist_ok=True)
    day = datetime.date.today().toordinal()
    local_path = f"img/vk_{day}.jpg"
    with open(local_path, "wb") as f:
        f.write(img_bytes)
    log(f"💾 Сохранено локально: {local_path}")

    variants = (
        {"owner_id": "-" + VK_GROUP_ID},   # доказанный рабочий вариант
        {"group_id": VK_GROUP_ID},         # запасной
    )
    for params in variants:
        srv = vk_call("photos.getWallUploadServer", params, token=tok)
        if not srv or "upload_url" not in srv:
            continue
        try:
            r = requests.post(srv["upload_url"],
                files={"photo": ("cover.jpg", img_bytes, "image/jpeg")}, timeout=120).json()
        except Exception as e:
            log(f"⚠️ VK upload: {e}")
            continue

        if "photo" not in r or "server" not in r or "hash" not in r:
            log(f"⚠️ Нет photo/server/hash: {str(r)[:200]}")
            continue

        save_params = dict(params)
        save_params.update({"photo": r["photo"], "server": r["server"], "hash": r["hash"]})
        saved = vk_call("photos.saveWallPhoto", save_params, token=tok)
        if saved and len(saved) > 0:
            p = saved[0]
            owner_id, photo_id, acc = p.get("owner_id", ""), p.get("id", ""), p.get("access_key", "")
            if owner_id and photo_id:
                att = f"photo{owner_id}_{photo_id}"
                if acc:
                    att += f"_{acc}"
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

    # --- Картинка: до 3 попыток генерации с разными seed ---
    scene = build_scene(post)
    base_img = scene if scene else book.get("about", "")[:120]
    run_no = int(os.environ.get("GITHUB_RUN_NUMBER", "0"))
    img_bytes = None
    for attempt in range(3):
        seed = day + 3000000 + (run_no % 100) + attempt * 7919
        img_bytes = download_image(base_img, seed)
        if img_bytes:
            break
        log(f"⏳ Попытка {attempt + 1} не удалась, пробуем снова...")

    # --- Фолбэк: последняя сохранённая картинка из img/ ---
    if not img_bytes:
        old = sorted(glob.glob("img/vk_*.jpg"), key=os.path.getmtime)
        if old:
            log(f"⚠️ Генерация не удалась — беру прежнюю картинку {old[-1]}")
            with open(old[-1], "rb") as f:
                img_bytes = f.read()

    # --- Загрузка и публикация ---
    att = vk_upload_photo(img_bytes) if img_bytes else None
    if not att:
        log("⚠️ Картинку загрузить не удалось — пост выйдет без картинки")
    vk_post_wall(caption, att)

    log("=" * 50)
    log("✅ FINISH: пост → ВК!" + (" (с картинкой)" if att else " (БЕЗ картинки!)"))
    log("=" * 50)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"❌ КРИТИЧЕСКАЯ ОШИБКА: {e}")
        raise
