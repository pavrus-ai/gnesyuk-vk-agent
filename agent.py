# -*- coding: utf-8 -*-
import os, json, datetime, requests

# ================= НАСТРОЙКИ =================
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

# ================= ИИ (ТОЛЬКО РУССКИЙ ЯЗЫК) =================
def ai_groq(prompt, model):
    if not GROQ_KEY: return None
    # Добавляем строгую инструкцию про русский язык
    full_prompt = f"{prompt}\n\nВАЖНО: Пиши ТОЛЬКО на русском языке. Никаких английских или китайских слов."
    r = requests.post("https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {GROQ_KEY}"},
        json={"model": model, "temperature": 0.8,
              "messages": [{"role": "user", "content": full_prompt}]}, timeout=60).json()
    if "error" in r:
        log(f"Groq ({model}) error: {r['error'].get('message', str(r['error']))}")
        return None
    return _extract(r)

def ai_openrouter(prompt, model):
    if not OR_KEY: return None
    full_prompt = f"{prompt}\n\nВАЖНО: Пиши ТОЛЬКО на русском языке. Никаких английских или китайских слов."
    r = requests.post("https://openrouter.ai/api/v1/chat/completions",
        headers={"Authorization": f"Bearer {OR_KEY}", "HTTP-Referer": "https://github.com/gnesyuk-vk-agent"},
        json={"model": model, "temperature": 0.8,
              "messages": [{"role": "user", "content": full_prompt}]}, timeout=60).json()
    if "error" in r:
        log(f"OpenRouter ({model}) error: {r['error'].get('message', str(r['error']))}")
        return None
    return _extract(r)

def ai_text(prompt):
    log(f"GROQ_KEY: {'есть' if GROQ_KEY else 'НЕТ'} | OPENROUTER_KEY: {'есть' if OR_KEY else 'НЕТ'}")
    
    # Список моделей для перебора (актуальные бесплатные)
    models = [
        ("groq", "llama-3.3-70b-versatile"),
        ("groq", "llama-3.1-8b-instant"),
        ("groq", "gemma2-9b-it"),
        ("openrouter", "meta-llama/llama-3.3-70b-instruct:free"),
        ("openrouter", "google/gemma-3-27b-it:free"),
        ("openrouter", "deepseek/deepseek-chat-v3-0324:free"),
        ("openrouter", ":free")  # Джокер: любая доступная бесплатная модель
    ]
    
    for provider, model in models:
        try:
            if provider == "groq":
                res = ai_groq(prompt, model)
            else:
                res = ai_openrouter(prompt, model)
            
            if res:
                log(f"✅ Успех: {provider} ({model})")
                return res
        except Exception as e:
            log(f"❌ Исключение {provider} ({model}): {e}")
            
    raise RuntimeError("Все ИИ недоступны.")

# ================= КАРТИНКА (ССЫЛКОЙ) =================
def make_image_link(theme):
    # Запрос на английском для генерации, но это не влияет на текст поста
    p = ("Atmospheric cinematic illustration for a russian adventure thriller novel, "
         + theme + ", dramatic light, no text, no letters")
    url = ("https://image.pollinations.ai/prompt/" + requests.utils.quote(p)
           + "?width=1200&height=800&nologo=true&seed=" + str(datetime.date.today().toordinal()))
    log(f"Картинка готова: {url[:50]}...")
    return url

# ================= СБОРКА ПОСТА (350-700 ЗНАКОВ) =================
def build_post(book, mode, day):
    t, a, u = book["title"], book["about"], book["url"]
    
    # Базовый промпт с жесткими ограничениями
    base_req = (f"Напиши пост для ВК о книге Павла Гнесюка «{t}». "
                f"Сюжет: {a}. "
                f"Требования: "
                f"1. ТОЛЬКО русский язык. "
                f"2. Длина строго 350-600 символов (без учета ссылки). "
                f"3. Начни с цепляющего ЗАГОЛОВКА (все буквы заглавные). "
                f"4. Не используй кавычки-цитаты из книги, пиши своими словами. "
                f"5. В конце добавь призыв к действию.")

    if mode == "fragment" and book.get("fragments"):
        fr = book["fragments"][day % len(book["fragments"])]
        # Для фрагмента просим ввести цитату и написать вступление
        txt = ai_text(f"{base_req} Используй эту цитату как основу: «{fr}».")
        return f"{txt}\n\n📖 Читать на Литрес: {u}\n{TAGS}", a
    
    if mode == "question":
        txt = ai_text(f"{base_req} Закончи пост интригующим вопросом к читателям.")
        return f"{txt}\n\n📖 Читать на Литрес: {u}\n{TAGS}", a
        
    # Режим "about"
    txt = ai_text(base_req)
    return f"{txt}\n\n📖 Читать на Литрес: {u}\n{TAGS}", a

def publish(text, image_url):
    # Добавляем ссылку на картинку в конец текста — ВК сам подтянет её как фото
    full_text = f"{text}\n\n{image_url}"
    res = vk("wall.post", owner_id=f"-{GROUP_ID}", from_group=1, message=full_text, attachments="")
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
    
    # Если нет фрагментов для книги, переключаемся на "about"
    if mode == "fragment" and not book.get("fragments"):
        mode = "about"
        
    log(f"📚 Книга дня: «{book['title']}» ({book['series']}) | Режим: {mode}")

    text, theme = build_post(book, mode, day)
    
    # Генерация картинки
    img_url = ""
    try:
        img_url = make_image_link(theme)
    except Exception as e:
        log(f"⚠️ Картинка не создана: {e}")

    pid = publish(text, img_url)
    
    # Отчёт в Telegram
    report_msg = (f"✅ ПОСТ ОПУБЛИКОВАН!\n"
                  f"📖 Книга: {book['title']}\n"
                  f"🎯 Режим: {mode}\n"
                  f"🆔 ID: {pid}\n"
                  f"🔗 Ссылка: https://vk.com/wall-{GROUP_ID}_{pid}")
    telegram(report_msg + "\n\n" + "\n".join(REPORT))

    # === ФИНИШНАЯ ИНСТРУКЦИЯ ===
    log("=" * 50)
    log("✅ FINISH: Агент завершил работу успешно!")
    log(f"📖 Книга: {book['title']}")
    log(f"🎯 Режим: {mode}")
    log(f"🆔 Post ID: {pid}")
    log(f"🔗 https://vk.com/wall-{GROUP_ID}_{pid}")
    log("=" * 50)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"❌ КРИТИЧЕСКАЯ ОШИБКА: {e}")
        telegram("❌ АГЕНТ УПАЛ:\n" + "\n".join(REPORT))
        raise
