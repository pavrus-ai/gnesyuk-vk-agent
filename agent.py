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
    """Безопасное извлечение текста из ответа ИИ."""
    try:
        return r["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError):
        return None

def ai_groq(prompt):
    r = requests.post("https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {GROQ_KEY}"},
        json={"model": "llama-3.1-8b-instant", "temperature": 0.9,
              "messages": [{"role": "user", "content": prompt}]}, timeout=60).json()
    return _extract(r)

def ai_openrouter(prompt):
    r = requests.post("https://openrouter.ai/api/v1/chat/completions",
        headers={"Authorization": f"Bearer {OR_KEY}"},
        json={"model": "meta-llama/llama-3.1-8b-instruct:free", "temperature": 0.9,
              "messages": [{"role": "user", "content": prompt}]}, timeout=60).json()
    return _extract(r)

def ai_text(prompt):
    """ИИ-1 пишет черновик, ИИ-2 шлифует. Если один недоступен — работает второй."""
    draft = final = None
    try:
        draft = ai_groq(prompt)
        if draft: log("ИИ-1 (Groq): черновик готов")
        else: log("ИИ-1 (Groq): пустой ответ")
    except Exception as e:
        log(f"ИИ-1 (Groq) недоступен: {e}")
    try:
        if draft:
            final = ai_openrouter(f"Улучши текст поста ВК: сделай живым и интригующим, "
                f"не добавляй фактов, не используй кавычки, до 900 знаков. Текст:\n{draft}")
            if final: log("ИИ-2 (OpenRouter): текст отшлифован")
        if not final:
            final = ai_openrouter(prompt)
            if final: log("ИИ-2 (OpenRouter): текст написан")
    except Exception as e:
        log(f"ИИ-2 (OpenRouter) недоступен: {e}")
        final = draft
    if not final:
        raise RuntimeError("Оба ИИ недоступны")
    return final

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
