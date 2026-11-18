# -*- coding: utf-8 -*-
"""
gnesyuk-max-agent v2.1
Агент для публикации РАЗВЁРНУТЫХ лонгридов (2100-2300 симв.) в MAX.
Чередует темы: нечётные дни - книги (max_books_topics.json), чётные - тайны (mysteries.json).
Автоматически формирует идеальный подвал поста с хештегами и ссылкой на ЛитРес.
"""
import os, json, datetime, requests, time, io, base64, uuid, urllib3, re, random
from PIL import Image, ImageEnhance
urllib3.disable_warnings()

# ============================================================
# ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ
# ============================================================
GROQ_KEY = os.environ.get("GROQ_KEY", "").strip()
GROQ_KEY2 = os.environ.get("GROQ_KEY2", "").strip()
OPENAI_KEY = os.environ.get("OPENAI_KEY", "").strip()
GIGACHAT_CLIENT_ID = os.environ.get("GIGACHAT_CLIENT_ID1", "").strip()
GIGACHAT_CLIENT_SECRET = os.environ.get("GIGACHAT_CLIENT_SECRET1", "").strip()
MAX_TOKEN = os.environ.get("MAX_BOT_TOKEN", "").strip()
MAX_CHAT = os.environ.get("MAX_CHAT_ID", "").strip()
POLLINATIONS_API = "https://image.pollinations.ai/prompt/"

BOOK_TAGS = "#ПавелГнесюк #книги #авторскийблог #писатель"
MYSTERY_TAGS = "#ПавелГнесюк #тайны #история #загадки"
RU = "\n\nВАЖНО: Пиши ТОЛЬКО на русском языке."

GROQ_MODELS = ["meta-llama/llama-4-scout-17b-16e-instruct", "llama-3.1-8b-instant"]

META_BAN = (
    " СТРОГИЙ ЗАПРЕТ: НЕ включай в финальный текст служебные слова и метки: "
    "«Эмоциональный крючок», «Крючок поста», «Длина поста», «Пост с отсылкой», "
    "«Заголовок», «Title», «Caption», «Текст:», «Ответ:». "
    "НЕ начинай пост с фраз: «Погрузитесь в», «Откройте для себя», «Узнайте», "
    "«Представляем», «Встречайте», «Добро пожаловать», «Читайте», «Новый роман», "
    "«Новая книга», «Новая глава», «Этот захватывающий», «Этот увлекательный». "
    "НЕ начинай с названия книги или серии. "
    "НЕ используй восклицательные знаки в первой строке. "
    "НЕ делай коротких строк-подзаголовков без продолжения. "
    "Пиши сплошным связным текстом с абзацами. "
    "Первая строка должна быть КОНКРЕТНОЙ СЦЕНОЙ или ДЕЙСТВИЕМ. "
    "СТРОГО ЗАПРЕЩЕНО добавлять хештеги в конец текста, они будут добавлены автоматически."
)

# Файлы кэша
MAX_FAILED = "max_failed.json"
MAX_USED = "max_used.json"
MAX_HISTORY = "max_history.json"

def log(msg):
    print(msg, flush=True)

log("Версия ℹ️ gnesyuk-max-agent v2.1 (чередование книг/тайн + авто-подвал с ЛитРес)")

# ============================================================
# ИИ-ТЕКСТ (GigaChat → Groq)
# ============================================================
def _extract(r):
    try: return r["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError): return None

_G_TOKEN, _G_EXP = None, 0

def get_gigachat_token():
    global _G_TOKEN, _G_EXP
    if not GIGACHAT_CLIENT_ID or not GIGACHAT_CLIENT_SECRET:
        return None
    if _G_TOKEN and time.time() < _G_EXP:
        return _G_TOKEN
    try:
        cred = base64.b64encode(f"{GIGACHAT_CLIENT_ID}:{GIGACHAT_CLIENT_SECRET}".encode()).decode()
        r = requests.post("https://ngw.devices.sberbank.ru:9443/api/v2/oauth",
            headers={"Authorization": f"Basic {cred}", "RqUID": str(uuid.uuid4()),
                     "Content-Type": "application/x-www-form-urlencoded"},
            data={"scope": "GIGACHAT_API_PERS"}, timeout=30, verify=False)
        if r.status_code == 200 and "access_token" in r.json():
            _G_TOKEN = r.json()["access_token"]
            _G_EXP = time.time() + 1700
            return _G_TOKEN
    except Exception as e:
        log(f"⚠️ GigaChat auth: {e}")
    return None

def ai_text(prompt, minlen=2000, rescue_min=1800):
    """Генерация текста: GigaChat → Groq."""
    best_res = ""
    def take(res, label):
        nonlocal best_res
        if not res: return None
        res = _strip_meta(res)
        if len(res) >= minlen:
            log(f"✅ Success: {label}, {len(res)} chars.")
            return res
        if len(res) > len(best_res): best_res = res
        return None

    # 1. GigaChat
    token = get_gigachat_token()
    if token:
        try:
            r = requests.post("https://gigachat.devices.sberbank.ru/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json={"model": "GigaChat:latest", "temperature": 0.9, "max_tokens": 4000,
                      "messages": [{"role": "user", "content": prompt + RU}]},
                timeout=120, verify=False)
            if r.status_code == 200:
                res = take(r.json()["choices"][0]["message"]["content"].strip(), "gigachat")
                if res: return res
        except Exception as e:
            log(f"⚠️ GigaChat request: {e}")

    # 2. Groq
    for key in (GROQ_KEY, GROQ_KEY2):
        if not key: continue
        for model in GROQ_MODELS:
            try:
                r = requests.post("https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {key}"},
                    json={"model": model, "temperature": 0.85,
                          "messages": [{"role": "user", "content": prompt + RU}]},
                    timeout=90).json()
                if "error" not in r:
                    res = take(_extract(r), f"groq {model}")
                    if res: return res
            except Exception: pass

    if best_res and len(best_res) >= rescue_min:
        return best_res
    return None

def _strip_meta(text):
    bad_prefixes = [
        "Эмоциональный крючок", "Крючок поста", "Длина поста", "Пост с отсылкой",
        "Пост:", "Текст:", "Ответ:", "Вот пост", "Вот текст",
        "Заголовок:", "Title:", "Caption:"
    ]
    lines = text.split("\n")
    cleaned = []
    for line in lines:
        stripped = line.strip()
        skip = any(stripped.startswith(p) for p in bad_prefixes)
        if not skip:
            cleaned.append(line)
    return "\n".join(cleaned).strip()

def _fix_bad_opening(text):
    bad_openings = [
        "погрузитесь", "откройте", "узнайте", "представляем",
        "встречайте", "добро пожаловать", "читайте", "новый роман",
        "новая книга", "новая глава", "этот захватывающий", "этот увлекательный"
    ]
    lines = text.split("\n")
    while lines:
        first = lines[0].strip().lower()
        if any(bad in first for bad in bad_openings):
            lines.pop(0)
        else:
            break
    return "\n".join(lines).strip()

def clean_txt(t):
    t = t.replace("**", "").replace("##", "").replace("#", "").strip()
    t = _strip_meta(t)
    t = _fix_bad_opening(t)
    return t

# ============================================================
# КАРТИНКИ
# ============================================================
def download_image(scene_text, seed):
    clean_img = "".join(c for c in scene_text if c.isalnum() or c.isspace() or c in ".,-")[:220].strip()
    base_prompt = f"Cinematic photography, highly detailed, 8k resolution, dramatic lighting, photorealistic. Scene: {clean_img}. No text, no watermark."
    
    img_bytes = None
    source = "unknown"

    if OPENAI_KEY:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=OPENAI_KEY)
            for model_name in ["gpt-image-2.5-flare", "chatgpt-image-latest", "gpt-image-2"]:
                try:
                    response = client.images.generate(model=model_name, prompt=base_prompt, n=1, size="1024x1024", quality="low")
                    if hasattr(response.data[0], 'url') and response.data[0].url:
                        r = requests.get(response.data[0].url, timeout=60)
                        if r.status_code == 200 and len(r.content) > 10000:
                            img_bytes = r.content; source = "openai"; break
                    elif hasattr(response.data[0], 'b64_json') and response.data[0].b64_json:
                        img_bytes = base64.b64decode(response.data[0].b64_json); source = "openai"; break
                except Exception as e:
                    err = str(e).lower()
                    if "permission" in err or "rate_limit" in err or "quota" in err: break
        except Exception: pass

    if not img_bytes:
        silhouette_boost = ", silhouette from behind, shadow figure, back view only, mysterious atmosphere, foggy background"
        anti_artifacts = "face, eyes, mouth, cartoon, anime, painting, text, watermark, logo, distorted"
        final_prompt = base_prompt + silhouette_boost
        for attempt in range(2):
            url = f"{POLLINATIONS_API}{requests.utils.quote(final_prompt)}?nologo=true&seed={seed + attempt * 500}&model=flux&width=768&height=768&negative_prompt={requests.utils.quote(anti_artifacts)}"
            try:
                r = requests.get(url, timeout=300)
                if r.status_code == 200 and len(r.content) > 10000:
                    img_bytes = r.content; source = "pollinations"; break
            except Exception: pass
            time.sleep(2)

    if not img_bytes: return None

    if source == "pollinations":
        try:
            im = Image.open(io.BytesIO(img_bytes))
            w, h = im.size
            im = im.crop((0, 0, w, int(h * 0.96)))
            buf = io.BytesIO()
            im.save(buf, format="JPEG", quality=90)
            img_bytes = buf.getvalue()
        except Exception: pass

    return img_bytes

def convert_to_jpeg(img_bytes):
    if not img_bytes: return None
    try:
        im = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        im.thumbnail((800, 800), Image.Resampling.LANCZOS)
        im = ImageEnhance.Contrast(im).enhance(1.1)
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=90, optimize=True)
        return buf.getvalue()
    except Exception:
        return img_bytes

# ============================================================
# ПУБЛИКАЦИЯ В MAX
# ============================================================
def max_post(img_bytes, text):
    if not MAX_TOKEN or not MAX_CHAT:
        log("⚠️ MAX не настроен")
        return False
    chat_val = int(MAX_CHAT) if MAX_CHAT.lstrip("-").isdigit() else MAX_CHAT
    bases = ["https://platform-api2.max.ru", "https://platform-api.max.ru", "https://botapi.max.ru"]
    headers_list = [{"Authorization": f"Bearer {MAX_TOKEN}"}, {"Authorization": MAX_TOKEN}]
    
    for base in bases:
        for hdr in headers_list:
            try:
                up = requests.post(f"{base}/uploads", headers=hdr, params={"type": "image", "chat_id": chat_val}, timeout=60, verify=False).json()
                up_url = up.get("url") if isinstance(up, dict) else None
                if not up_url: continue
                
                if img_bytes:
                    ru = requests.post(up_url, files={"file": ("cover.jpg", img_bytes, "image/jpeg")}, timeout=120, verify=False).json()
                else:
                    ru = {"photos": {"0": {"token": "no_image"}}}
                
                tok = None
                if isinstance(ru, dict):
                    ph = ru.get("photos") or {}
                    if isinstance(ph, dict):
                        for v in ph.values():
                            if isinstance(v, dict) and v.get("token"):
                                tok = v["token"]; break
                    tok = tok or ru.get("token")
                
                if not tok: continue
                
                payload = {"text": text[:8000]}
                if tok != "no_image":
                    payload["attachments"] = [{"type": "image", "payload": {"token": tok}}]
                
                r = requests.post(f"{base}/messages", headers=hdr, params={"chat_id": chat_val}, json=payload, timeout=60, verify=False).json()
                if isinstance(r, dict) and (r.get("success") is True or isinstance(r.get("message"), dict)):
                    log(f"✅ MAX: Пост отправлен ({len(text)} симв.)")
                    return True
            except Exception: continue
    return False

# ============================================================
# УТИЛИТЫ И КЭШ
# ============================================================
def load_json(path, default):
    try:
        if os.path.exists(path): return json.load(open(path, encoding="utf-8"))
    except Exception: pass
    return default

def save_json(path, data):
    json.dump(data, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

# ============================================================
# ГЛАВНЫЙ ЦИКЛ
# ============================================================
def main():
    day = datetime.date.today().day
    
    # 1. ОПРЕДЕЛЕНИЕ ИСТОЧНИКА ПО ДНЮ МЕСЯЦА
    if day % 2 != 0:
        log(f"📅 {day}-е число (нечётное): генерирую лонгрид по КНИГАМ")
        topics_file = "max_books_topics.json"
    else:
        log(f"📅 {day}-е число (чётное): генерирую лонгрид по ТАЙНАМ")
        topics_file = "mysteries.json"

    # 2. ЗАГРУЗКА ТЕМ
    topics = load_json(topics_file, [])
    if not topics:
        log(f"❌ Файл {topics_file} пуст или не найден!")
        raise SystemExit(1)
    log(f"✅ Загружено тем из {topics_file}: {len(topics)}")

    # 3. ВЫБОР СЛУЧАЙНОЙ НЕИСПОЛЬЗОВАННОЙ ТЕМЫ
    used = set(load_json(MAX_USED, []))
    pool = [t for t in topics if t.get("topic", t.get("title", "")) not in used]
    
    if not pool:
        log(f"⚠️ Все темы в {topics_file} использованы — сброс blacklist")
        pool = topics
        save_json(MAX_USED, []) 

    selected_topic = random.choice(pool)
    topic_key = selected_topic.get("topic", selected_topic.get("title", "Unknown"))
    log(f"🎯 Выбрана тема: {topic_key}")

    # 4. ПОДГОТОВКА ПРОМПТА И КАРТИНКИ
    img_prompt = selected_topic.get("image_prompt", f"Mysterious scene, {topic_key}")
    
    if topics_file == "max_books_topics.json":
        # Для книг берём готовый, идеально выверенный промпт из JSON
        prompt = selected_topic["ai_prompt"]
    else:
        # Для тайн генерируем промпт на лету, сохраняя строгие рамки длины и стиля
        facts = selected_topic.get("facts", [])
        facts_str = "\n".join([f"- {f}" for f in facts])
        prompt = (
            f"Напиши РАЗВЁРНУТЫЙ пост-лонгрид (СТРОГО 2100-2300 символов) для платформы MAX. "
            f"Тема: {selected_topic['topic']}. "
            f"Используй эти факты как основу: {facts_str}. "
            f"Требования: 1. ТОЛЬКО русский язык. "
            f"2. Объем СТРОГО 2100-2300 символов. "
            f"3. Структура: Интригующий заголовок, исторический контекст, подробный разбор фактов, "
            f"риторический вопрос к читателю. "
            f"4. Живой, детективный стиль, без нейрослопа и штампов. "
            f"5. В самом конце добавь хештеги: {MYSTERY_TAGS}"
            + META_BAN
        )

    # 5. ГЕНЕРАЦИЯ ТЕКСТА
    log("📝 Генерация текста...")
    post = ai_text(prompt, minlen=2000, rescue_min=1800)
    if not post:
        log("❌ ИИ не смог сгенерировать текст нужной длины.")
        raise SystemExit(1)
    
    # 6. ПОСТ-ОБРАБОТКА ТЕКСТА (Идеальный подвал)
    post = clean_txt(post)
    
    # 1. Принудительно убираем любые хештеги, которые ИИ всё-таки мог добавить в конец
    post = re.sub(r'\n*#(?:ПавелГнесюк|книги|авторскийблог|писатель|тайны|история|загадки|лонгрид)[\wа-яА-Я#]*', '', post, flags=re.IGNORECASE).strip()
    
    # 2. Формируем чистый хештег из названия темы (убираем пробелы, двоеточия и спецсимволы)
    clean_topic = re.sub(r'[^a-zA-Zа-яА-Я0-9]', '', topic_key)
    
    # 3. Добавляем финальные хештеги и ссылку на ЛитРес
    if topics_file == "max_books_topics.json":
        final_tags = f"\n\n#{clean_topic}\n{BOOK_TAGS}"
    else:
        final_tags = f"\n\n#{clean_topic}\n{MYSTERY_TAGS}"
        
    cta = "\n\nКниги Павла Гнесюка читайте в ЛитРес, https://www.litres.ru/author/pavel-gnesuk/"
    
    # Собираем финальный текст
    post = post + final_tags + cta
    
    log(f"📝 Итоговый пост: {len(post)} симв.")

    # 7. ГЕНЕРАЦИЯ КАРТИНКИ
    log("🎨 Генерация картинки...")
    run_no = int(os.environ.get("GITHUB_RUN_NUMBER", "0"))
    raw_img = download_image(img_prompt, day + 5000000 + (run_no % 100))
    img_bytes = convert_to_jpeg(raw_img) if raw_img else None
    
    if img_bytes:
        os.makedirs("img_max", exist_ok=True)
        img_file = f"img_max/max_{day}.jpg"
        with open(img_file, "wb") as f: f.write(img_bytes)
        log(f"🖼 Картинка сохранена: {img_file}")

    # 8. ПУБЛИКАЦИЯ
    ok = max_post(img_bytes, post)

    # 9. ОБНОВЛЕНИЕ КЭША
    used_list = load_json(MAX_USED, [])
    if topic_key not in used_list:
        used_list.append(topic_key)
    save_json(MAX_USED, used_list[-500:])

    history = load_json(MAX_HISTORY, [])
    history.append({
        "date": datetime.date.today().isoformat(), 
        "day_parity": "odd" if day % 2 != 0 else "even",
        "source_file": topics_file,
        "topic": topic_key, 
        "len": len(post)
    })
    save_json(MAX_HISTORY, history[-200:])

    log("=" * 50)
    log(f"✅ FINISH MAX: {'ОТПРАВЛЕНО' if ok else 'НЕ отправлено'}")
    if not ok:
        raise SystemExit(1)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"❌ CRITICAL: {e}")
        raise
