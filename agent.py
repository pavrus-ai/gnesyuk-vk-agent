# -*- coding: utf-8 -*-
import os, json, datetime, requests

# ================= НАСТРОЙКИ =================
VK_TOKEN = os.environ["VK_TOKEN"]       # Токен вашей группы
GROUP_ID = "191540984"                  # ID вашей группы из ссылки
ALBUM_ID = 310208146                     # ID вашего созданного альбома

GROQ_KEY = os.environ.get("GROQ_KEY", "")
OR_KEY = os.environ.get("OPENROUTER_KEY", "")
TG_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TG_CHAT = os.environ.get("TELEGRAM_CHAT_ID", "")
VK_API = "https://vk.ru"
TAGS = "#ПавелГнесюк #ТарскиеЛегенды #Хранители #книги #романы"
REPORT = []

def log(msg):
    print(msg); REPORT.append(msg)

def vk(method, token, **params):
    params.update(access_token=token, v="5.131")
    # Гарантированно правильное склеивание базового URL API и метода
    url = f"{VK_API.rstrip('/')}/{method.lstrip('/')}"
    r = requests.post(url, data=params, timeout=30).json()
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
        r = requests.post("https://groq.com",
            headers={"Authorization": f"Bearer {GROQ_KEY}"},
            json={"model": model, "temperature": 0.8,
                  "messages": [{"role": "user", "content": full_prompt}]}, timeout=60).json()
        if "error" in r: return None
        return _extract(r)
    except Exception as e:
        return None

def ai_openrouter(prompt, model):
    if not OR_KEY: return None
    full_prompt = f"{prompt}\n\nВАЖНО: Пиши ТОЛЬКО на русском языке. Никаких английских или китайских слов."
    try:
        r = requests.post("https://openrouter.ai",
            headers={"Authorization": f"Bearer {OR_KEY}", "HTTP-Referer": "https://github.com"},
            json={"model": model, "temperature": 0.8,
                  "messages": [{"role": "user", "content": full_prompt}]}, timeout=60).json()
        if "error" in r: return None
        return _extract(r)
    except Exception as e:
        return None

def ai_text(prompt):
    log(f"GROQ_KEY: {'есть' if GROQ_KEY else 'НЕТ'} | OPENROUTER_KEY: {'есть' if OR_KEY else 'НЕТ'}")
    
    models = [
        ("groq", "llama-3.3-70b-versatile"), ("groq", "llama-3.1-8b-instant"),
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
        except Exception as e:
            pass
            
    log("⚠️ Все ИИ недоступны. Публикую стандартный пост из базы.")
    try: 
        plot = prompt.split('Сюжет:')[1].split('Требования:')[0].strip()
    except: 
        plot = "Увлекательный роман с захватывающим сюжетом."
        
    return (f"📚 ЧИТАЙТЕ НОВЫЙ РОМАН ПАВЛА ГНЕСЮКА!\n\n{plot}\n\n"
            f"Увлекательный сюжет, неожиданные повороты и глубокие персонажи ждут вас.\n\n"
            f"👉 Читать на Литрес: https://litres.ru\n\n{TAGS}")

# ================= КАРТИНКА =================
def make_image_file(theme):
    # Очищаем тему от спецсимволов и обрезаем строку для стабильности URL генератора
    clean_theme = "".join(c for c in theme if c.isalnum() or c.isspace())[:120].strip()
    
    p = ("Atmospheric cinematic illustration for a russian adventure thriller novel, "
         + clean_theme + ", dramatic light, no text, no letters")
    url = ("https://pollinations.ai" + requests.utils.quote(p)
           + "?width=1200&height=800&nologo=true&seed=" + str(datetime.date.today().toordinal()))
    log(f"Скачивание картинки...")
    r = requests.get(url, timeout=180)
    r.raise_for_status()
    path = "img.jpg"
    with open(path, "wb") as f:
        f.write(r.content)
    return path

def upload_photo_to_vk(path):
    """Загрузка фото полностью через токен ГРУППЫ (без привязки к IP-адресу)"""
    try:
        # 1. Получаем сервер для загрузки в конкретный альбом группы
        server_data = vk("photos.getUploadServer", VK_TOKEN, 
                         group_id=int(GROUP_ID), 
                         album_id=ALBUM_ID)
        upload_url = server_data["upload_url"]
        
        # 2. Отправляем файл. Для метода загрузки в альбом поле обязательно называется 'file1'
        with open(path, "rb") as f:
            upload_resp = requests.post(upload_url, files={"file1": f}, timeout=60).json()
        
        if "error" in upload_resp or not upload_resp.get("photos_list"):
             log(f"❌ Ошибка загрузки файла в альбом ВК: {upload_resp}")
             return None

        # 3. Сохраняем фото в альбом сообщества
        saved_photos = vk("photos.save", VK_TOKEN, 
                          photos_list=upload_resp["photos_list"], 
                          server=upload_resp["server"], 
                          hash=upload_resp["hash"], 
                          group_id=int(GROUP_ID),
                          album_id=ALBUM_ID)
        
        if not saved_photos:
            log("❌ ВК вернул пустой массив при сохранении фотографии")
            return None
            
        # Берем первый объект из массива сохраненных фото
        photo_obj = saved_photos[0]
        attachment = f"photo{photo_obj['owner_id']}_{photo_obj['id']}"
        log(f"✅ Фото успешно загружено в альбом группы: {attachment}")
        return attachment
        
    except Exception as e:
        log(f"⚠️ Не удалось загрузить фото через токен группы: {e}")
        return None

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
    # Публикация записи на стене от имени группы
    params = {"owner_id": f"-{GROUP_ID}", "from_group": 1, "message": text}
    if attachment:
        params["attachments"] = attachment
    
    res = vk("wall.post", VK_TOKEN, **params)
    post_id = res['post_id']
    log(f"Пост опубликован, id {post_id}")
    return post_id

def telegram(msg):
    if TG_TOKEN and TG_CHAT:
        try:
            requests.post(f"https://telegram.org{TG_TOKEN}/sendMessage",
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
    
    # Попытка загрузить сгенерированное фото
    attachment = ""
    try:
        img_path = make_image_file(theme)
        attachment = upload_photo_to_vk(img_path)
    except Exception as e:
        log(f"⚠️ Ошибка при работе с картинкой: {e}")
    
    # Резервный вариант: если фото не смогло загрузиться, крепим прямую ссылку на Pollinations в текст
    if not attachment:
        try:
             clean_theme = "".join(c for c in theme if c.isalnum() or c.isspace())[:120].strip()
             p = ("Atmospheric cinematic illustration for a russian adventure thriller novel, " + clean_theme + ", dramatic light, no text")
             url = ("https://pollinations.ai" + requests.utils.quote(p) + "?width=1200&height=800&nologo=true")
             text += f"\n\n🖼 Иллюстрация: {url}"
             log("Добавлена ссылка на картинку в текст")
        except: pass

    pid = publish(text, attachment)
    
    post_url = f"https://vk.ru{GROUP_ID}_{pid}"
    
    report_msg = (f"✅ ПОСТ ОПУБЛИКОВАН!\n📖 Книга: {book['title']}\n🎯 Режим: {mode}\n🆔 ID: {pid}\n🔗 Ссылка: {post_url}")
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
