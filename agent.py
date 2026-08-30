# -*- coding: utf-8 -*-
import os, json, datetime, requests

# ================= НАСТРОЙКИ =================
VK_TOKEN = os.environ["VK_TOKEN"]                     # токен группы — для постов
VK_USER_TOKEN = os.environ.get("VK_USER_TOKEN", "")   # личный токен админа — для фото (метод PAVRUS)
GROUP_ID = "191540984"
GROQ_KEY = os.environ.get("GROQ_KEY", "")
OR_KEY   = os.environ.get("OPENROUTER_KEY", "")
TG_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TG_CHAT  = os.environ.get("TELEGRAM_CHAT_ID", "")

VK_API = "https://api.vk.com/method/"
POLLINATIONS_API = "https://image.pollinations.ai/prompt/"
TAGS = "#ПавелГнесюк #ТарскиеЛегенды #Хранители #книги #романы"
REPORT = []

def log(msg):
    print(msg); REPORT.append(msg)

def vk(method, token=None, **params):
    params.update(access_token=token or VK_TOKEN, v="5.131")
    r = requests.post(VK_API + method, data=params, timeout=30).json()
    if "error" in r:
        err = r['error']
        log(f"❌ VK API Error [{method}]: code={err.get('error_code')}, msg={err.get('error_msg')}")
        raise RuntimeError(f"VK error {method}: {err}")
    return r["response"]

def _extract(r):
    try:
        return r["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError):
        return None

# ================= ИИ (ТОЛЬКО РУССКИЙ ЯЗЫК) =================
def ai_groq(prompt, model):
    if not GROQ_KEY: return None
    full_prompt = f"{prompt}\n\nВАЖНО: Пиши ТОЛЬКО на русском языке. Никаких английских или китайских слов."
    try:
        r = requests.post("https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_KEY}"},
            json={"model": model, "temperature": 0.8,
                  "messages": [{"role": "user", "content": full_prompt}]}, timeout=60).json()
        if "error" in r: return None
        return _extract(r)
    except Exception:
        return None

def ai_openrouter(prompt, model):
    if not OR_KEY: return None
    full_prompt = f"{prompt}\n\nВАЖНО: Пиши ТОЛЬКО на русском языке. Никаких английских или китайских слов."
    try:
        r = requests.post("https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {OR_KEY}", "HTTP-Referer": "https://github.com"},
            json={"model": model, "temperature": 0.8,
                  "messages": [{"role": "user", "content": full_prompt}]}, timeout=60).json()
        if "error" in r: return None
        return _extract(r)
    except Exception:
        return None

def ai_text(prompt):
    log(f"GROQ_KEY: {'есть' if GROQ_KEY else 'НЕТ'} | OPENROUTER_KEY: {'есть' if OR_KEY else 'НЕТ'}")
    models = [
        ("groq", "llama-3.3-70b-versatile"),
        ("groq", "llama-3.1-8b-instant"),
        ("openrouter", "meta-llama/llama-3.3-70b-instruct:free"),
        ("openrouter", "google/gemma-3-27b-it:free"),
        ("openrouter", "deepseek/deepseek-chat-v3-0324:free"),
        ("openrouter", "auto")
    ]
    for provider, model in models:
        try:
            res = ai_groq(prompt, model) if provider == "groq" else ai_openrouter(prompt, model)
            if res:
                log(f"✅ Успех: {provider} ({model})")
                return res
        except Exception:
            pass
    log("⚠️ Все ИИ недоступны. Публикую стандартный пост из базы.")
    try:
        plot = prompt.split('Сюжет:')[1].split('Требования:')[0].strip()
    except Exception:
        plot = "Увлекательный роман с захватывающим сюжетом."
    return (f"📚 ЧИТАЙТЕ НОВЫЙ РОМАН ПАВЛА ГНЕСЮКА!\n\n{plot}\n\n"
            f"Увлекательный сюжет, неожиданные повороты и глубокие персонажи ждут вас.\n\n"
            f"👉 Читать на Литрес: https://litres.ru\n\n{TAGS}")

# ================= КАРТИНКА (МЕТОД PAVRUS) =================
def make_image_bytes(theme):
    clean_theme = "".join(c for c in theme if c.isalnum() or c.isspace())[:120].strip()
    p = ("Atmospheric cinematic illustration for a russian adventure thriller novel, "
         + clean_theme + ", dramatic light, no text, no letters")
    url = (POLLINATIONS_API + requests.utils.quote(p)
           + "?width=1200&height=800&nologo=true&seed=" + str(datetime.date.today().toordinal()))
    log("Скачивание картинки...")
    r = requests.get(url, timeout=180)
    r.raise_for_status()
    if not r.headers.get("content-type", "").startswith("image"):
        raise RuntimeError("ответ не изображение")
    log(f"Картинка: {len(r.content)} байт")
    return r.content

def upload_photo(data):
    """Как в PAVRUS: фото через ЛИЧНЫЙ токен администратора"""
    up = vk("photos.getWallUploadServer", token=VK_USER_TOKEN, group_id=GROUP_ID)["upload_url"]
    j = requests.post(up, files={"photo": ("i.jpg", data, "image/jpeg")}, timeout=120).json()
    p = None
    for ex in ({"group_id": GROUP_ID}, {}):
        try:
            p = vk("photos.saveWallPhoto", token=VK_USER_TOKEN,
                   photo=j.get("photo", ""), server=j.get("server", ""),
                   hash=j.get("hash", ""), **ex)[0]
            break
        except Exception:
            continue
    if p is None:
        raise RuntimeError("saveWallPhoto не сработал")
    att = f"photo{p['owner_id']}_{p['id']}"
    log(f"✅ Фото загружено: {att}")
    return att

# ================= СБОРКА ПОСТА =================
def build_post(book, mode, day):
    t, a, u = book["title"], book["about"], book["url"]
    base_req = (f"Напиши пост для ВК о книге Павла Гнесюка «{t}». Сюжет: {a}. "
                f"Требования: 1. ТОЛЬКО русский язык. 2. Длина строго 350-600 символов. "
                f"3. Начни с цепляющего ЗАГОЛОВКА (все буквы заглавные). "
                f"4. Не используй кавычки-цитаты, пиши своими словами. 5. В конце призыв к действию.")
    if mode == "fragment" and book.get("fragments"):
        fr = book["fragments"][day % len(book["fragments"])]
        txt = ai_text(f"{base_req} Используй эту цитату как основу: «{fr}».")
        return f"{txt}\n\n📖 Читать на Литрес: {u}\n{TAGS}", a
    if mode == "question":
        txt = ai_text(f"{base_req} Закончи пост интригующим вопросом к читателям.")
        return f"{txt}\n\n📖 Читать на Литрес: {u}\n{TAGS}", a
    txt = ai_text(base_req)
    return f"{txt}\n\n📖 Читать на Литрес: {u}\n{TAGS}", a

def publish(text, attachment):
    params = {"owner_id": f"-{GROUP_ID}", "from_group": 1, "message": text}
    if attachment:
        params["attachments"] = attachment
    res = vk("wall.post", **params)
    log(f"Пост опубликован, id {res['post_id']}")
    return res["post_id"]

def telegram(msg):
    if TG_TOKEN and TG_CHAT:
        try:
            requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                          data={"chat_id": TG_CHAT, "text": msg}, timeout=30)
        except Exception as e:
            print("Telegram error:", e)

# ================= ГЛАВНЫЙ БЛОК =================
def main():
    books = json.load(open("books.json", encoding="utf-8"))["books"]
    day = datetime.date.today().toordinal()
    book = books[day % len(books)]
    mode = ["about", "fragment", "question"][day % 3]
    if mode == "fragment" and not book.get("fragments"):
        mode = "about"
    log(f"📚 Книга дня: «{book['title']}» ({book['series']}) | Режим: {mode}")

    text, theme = build_post(book, mode, day)

    attachment = ""
    if VK_USER_TOKEN:
        try:
            attachment = upload_photo(make_image_bytes(theme))
        except Exception as e:
            log(f"⚠️ Фото через токен админа не удалось: {e}")
    else:
        log("⚠️ Нет VK_USER_TOKEN — пост со ссылкой")

    if not attachment:
        try:
            clean_theme = "".join(c for c in theme if c.isalnum() or c.isspace())[:120].strip()
            p = ("Atmospheric cinematic illustration for a russian adventure thriller novel, "
                 + clean_theme + ", dramatic light, no text")
            url = POLLINATIONS_API + requests.utils.quote(p) + "?width=1200&height=800&nologo=true"
            text += f"\n\n🖼 Иллюстрация: {url}"
            log("Добавлена ссылка на картинку в текст")
        except Exception:
            pass

    pid = publish(text, attachment)
    post_url = f"https://vk.com/wall-{GROUP_ID}_{pid}"

    report_msg = (f"✅ ПОСТ ОПУБЛИКОВАН!\n📖 Книга: {book['title']}\n🎯 Режим: {mode}\n"
                  f"🆔 ID: {pid}\n🔗 Ссылка: {post_url}")
    telegram(report_msg + "\n\n" + "\n".join(REPORT))

    log("=" * 50)
    log("✅ FINISH: Агент завершил работу успешно!")
    log(f"🔗 {post_url}")
    log("=" * 50)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"❌ КРИТИЧЕСКАЯ ОШИБКА: {e}")
        telegram("❌ АГЕНТ УПАЛ:\n" + "\n".join(REPORT))
        raise
