# -*- coding: utf-8 -*-
import os, json, datetime, requests

VK_TOKEN = os.environ["VK_TOKEN"]
GROUP_ID = os.environ["VK_GROUP_ID"]
GROQ_KEY = os.environ.get("GROQ_KEY", "")
OR_KEY   = os.environ.get("OPENROUTER_KEY", "")
TG_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TG_CHAT  = os.environ.get("TELEGRAM_CHAT_ID", "")
VK_API   = "https://api.vk.com/method/"
TAGS     = "#ПавелГнесюк #ТарскиеЛегенды #Хранители #книги #романы"
REPORT   = []

def log(msg):
    print(msg); REPORT.append(msg)

def vk(method, **params):
    params.update(access_token=VK_TOKEN, v="5.131")
    r = requests.post(VK_API + method, data=params, timeout=30).json()
    if "error" in r:
        raise RuntimeError(f"VK error {method}: {r['error']}")
    return r["response"]

def _extract(r):
    try:
        return r["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError):
        return None

def ai_groq(prompt, model="llama-3.1-8b-instant"):
    if not GROQ_KEY:
        return None
    r = requests.post("https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {GROQ_KEY}"},
        json={"model": model, "temperature": 0.9,
              "messages": [{"role": "user", "content": prompt}]}, timeout=60).json()
    if "error" in r:
        log(f"Groq ({model}) error: {r['error'].get('message', r['error'])}")
        return None
    return _extract(r)

def ai_openrouter(prompt, model="meta-llama/llama-3.1-8b-instruct:free"):
    if not OR_KEY:
        return None
    r = requests.post("https://openrouter.ai/api/v1/chat/completions",
        headers={"Authorization": f"Bearer {OR_KEY}",
                 "HTTP-Referer": "https://github.com/gnesyuk-vk-agent",
                 "X-Title": "Gnesyuk VK Agent"},
        json={"model": model, "temperature": 0.9,
              "messages": [{"role": "user", "content": prompt}]}, timeout=60).json()
    if "error" in r:
        log(f"OpenRouter ({model}) error: {r['error'].get('message', r['error'])}")
        return None
    return _extract(r)

def ai_text(prompt):
    log(f"GROQ_KEY: {'есть' if GROQ_KEY else 'НЕТ'} ({len(GROQ_KEY)} символов)")
    log(f"OPENROUTER_KEY: {'есть' if OR_KEY else 'НЕТ'} ({len(OR_KEY)} символов)")

    # === GROQ: актуальные модели 2026 ===
    groq_models = [
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant",
        "gemma2-9b-it",
        "mixtral-8x7b-32768",
        "llama3-70b-8192",
        "llama3-8b-8192"
    ]
    for model in groq_models:
        try:
            result = ai_groq(prompt, model)
            if result:
                log(f"✅ Groq ({model}): успех")
                return result
            else:
                log(f"⚠️ Groq ({model}): пустой ответ")
        except Exception as e:
            log(f"❌ Groq ({model}) исключение: {e}")

    # === OPENROUTER: модели, которые сам сервис предложил как замену + другие бесплатные ===
    or_models = [
        "meta-llama/llama-3.3-70b-instruct:free",
        "google/gemma-3-27b-it:free",
        "qwen/qwen3-32b:free",
        "deepseek/deepseek-chat-v3-0324:free",
        "mistralai/mistral-small-3.1-24b-instruct:free",
        "meta-llama/llama-3.3-70b-instruct",
        "google/gemma-3-27b-it",
        "qwen/qwen3-32b",
        "openrouter/auto"
    ]
    for model in or_models:
        try:
            result = ai_openrouter(prompt, model)
            if result:
                log(f"✅ OpenRouter ({model}): успех")
                return result
            else:
                log(f"⚠️ OpenRouter ({model}): пустой ответ")
        except Exception as e:
            log(f"❌ OpenRouter ({model}) исключение: {e}")

    raise RuntimeError("Все ИИ недоступны. Попробуйте позже или проверьте баланс ключей.")


def make_image(theme):
    p = ("Atmospheric cinematic illustration for a russian adventure thriller novel, "
         + theme + ", dramatic light, film grain, no text, no letters, no watermark")
    url = ("https://image.pollinations.ai/prompt/" + requests.utils.quote(p)
           + "?width=1200&height=800&nologo=true&seed=" + str(datetime.date.today().toordinal()))
    r = requests.get(url, timeout=180); r.raise_for_status()
    open("img.jpg", "wb").write(r.content)
    log("Картинка сгенерирована"); return "img.jpg"

def upload_photo(path):
    s = vk("photos.getWallUploadServer", group_id=GROUP_ID)
    up = requests.post(s["upload_url"], files={"photo": open(path, "rb")}, timeout=60).json()
    saved = vk("photos.saveWallPhoto", photo=up["photo"], server=up["server"],
               hash=up["hash"], group_id=GROUP_ID)
    return f"photo{saved[0]['owner_id']}_{saved[0]['id']}"

def build_post(book, mode, day):
    t, a, u = book["title"], book["about"], book["url"]
    if mode == "fragment" and book.get("fragments"):
        fr = book["fragments"][day % len(book["fragments"])]
        intro = ai_text(f"Напиши 1-2 интригующих предложения-вступления для поста ВК о романе Павла Гнесюка «{t}». Без кавычек и хештегов.")
        return f"{intro}\n\n«{fr}»\n\nПродолжение — в романе «{t}» на Литрес:\n{u}\n{TAGS}", a
    if mode == "question":
        txt = ai_text(f"Пост ВК по роману Павла Гнесюка «{t}» (сюжет: {a}): интригующий вопрос читателям + 2-3 предложения размышления + призыв ответить в комментариях. 500-800 знаков, без кавычек.")
        return f"{txt}\n\nРоман «{t}»: {u}\n{TAGS}", a
    txt = ai_text(f"Увлекательный пост ВК 600-900 знаков о романе Павла Гнесюка «{t}». Сюжет: {a}. Без спойлеров финала, без кавычек, живой писательский стиль.")
    return f"{txt}\n\nЧитайте на Литрес: {u}\n{TAGS}", a

def publish(text, att):
    res = vk("wall.post", owner_id=f"-{GROUP_ID}", from_group=1, message=text, attachments=att)
    log(f"Пост опубликован, id {res['post_id']}"); return res["post_id"]

def telegram(msg):
    if TG_TOKEN and TG_CHAT:
        try:
            requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                          data={"chat_id": TG_CHAT, "text": msg}, timeout=30)
        except Exception as e:
            print("Telegram недоступен:", e)

def main():
    books = json.load(open("books.json", encoding="utf-8"))["books"]
    day = datetime.date.today().toordinal()
    book = books[day % len(books)]
    mode = ["about", "fragment", "question"][day % 3]
    if mode == "fragment" and not book.get("fragments"):
        mode = "about"
    log(f"Книга дня: «{book['title']}» ({book['series']}), режим: {mode}")

    text, theme = build_post(book, mode, day)
    att = ""
    try:
        att = upload_photo(make_image(theme))
    except Exception as e:
        log(f"Картинка недоступна, пост без фото: {e}")

    pid = publish(text, att)
    telegram(f"📚 Пост опубликован!\nКнига: {book['title']}\nРежим: {mode}\nid поста: {pid}\n\n" + "\n".join(REPORT))

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"❌ Ошибка: {e}")
        telegram("❌ Агент не смог опубликовать пост:\n" + "\n".join(REPORT))
        raise
