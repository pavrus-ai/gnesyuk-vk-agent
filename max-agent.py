# -*- coding: utf-8 -*-
"""
gnesyuk-max-agent v1.0
Агент для публикации РАЗВЁРНУТЫХ лонгридов (2100-2300 симв.) ТОЛЬКО в MAX.
Использует те же книги и тайны, что и основной агент, но со своим blacklist.
"""
import os, json, datetime, requests, time, io, base64, uuid, urllib3, re, random, subprocess
from PIL import Image, ImageEnhance, ImageStat
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
    "Первая строка должна быть КОНКРЕТНОЙ СЦЕНОЙ или ДЕЙСТВИЕМ героя. "
)

# Файлы кэша — ОТДЕЛЬНЫЕ от основного агента!
MAX_FAILED = "max_failed.json"
MAX_USED = "max_used.json"
MAX_HISTORY = "max_history.json"

def log(msg):
    print(msg, flush=True)

log("Версия ℹ️ gnesyuk-max-agent v1.0 (лонгриды 2100-2300 симв. только для MAX)")

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
            log("✅ GigaChat token acquired")
            return _G_TOKEN
    except Exception as e:
        log(f"⚠️ GigaChat auth: {e}")
    return None

def ai_text(prompt, minlen=2000, rescue_min=1500):
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
            log(f"🩹 Cut bad opening: {lines[0][:50]}...")
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
# ГЕНЕРАЦИЯ ЛОНГРИДОВ (2100-2300 символов)
# ============================================================
def build_max_book_post(book, day):
    """Развёрнутый пост о книге специально для MAX."""
    t, a, s = book["title"], book["about"], book.get("series", "")
    prompt = (
        f"Напиши РАЗВЁРНУТЫЙ пост-лонгрид для платформы MAX о романе Павла Гнесюка «{t}»"
        f"{f' (серия «{s}»)' if s else ''}. Сюжет: {a}. "
        f"Требования: 1. ТОЛЬКО русский язык. "
        f"2. Объем СТРОГО 2100-2300 символов (длинный формат). "
        f"3. Структура: Цепляющий заголовок (1 строка), подробный синопсис без спойлеров финала, "
        f"анализ атмосферы или мотивации героев (2-3 абзаца), стилизованная мысль или цитата, "
        f"призыв к обсуждению в комментариях. "
        f"4. Живой, литературный стиль, без канцеляризмов и штампов. "
        f"5. В самом конце добавь хештеги: {BOOK_TAGS}"
        + META_BAN
    )
    txt = ai_text(prompt, minlen=2000, rescue_min=1800)
    return clean_txt(txt) if txt else f"РОМАН «{t.upper()}»: {a}"

def build_max_mystery_post(mystery, day):
    """Развёрнутый пост о тайне специально для MAX."""
    topic = mystery["topic"]
    facts = "\n".join([f"- {f}" for f in mystery["facts"]])
    prompt = (
        f"Напиши РАЗВЁРНУТЫЙ пост-лонгрид для платформы MAX на тему: {topic}. "
        f"Используй эти факты как основу: {facts}. "
        f"Требования: 1. ТОЛЬКО русский язык. "
        f"2. Объем СТРОГО 2100-2300 символов (длинный формат). "
        f"3. Структура: Интригующий заголовок (1 строка), исторический контекст, "
        f"подробный разбор фактов и противоречий (3-4 абзаца), "
        f"мнение автора или риторический вопрос к читателю. "
        f"4. Живой, детективный стиль, без нейрослопа. "
        f"5. В самом конце добавь хештеги: {MYSTERY_TAGS}"
        + META_BAN
    )
    txt = ai_text(prompt, minlen=2000, rescue_min=1800)
    return clean_txt(txt) if txt else f"Загадка: {topic}\n\n{mystery['facts'][0]}"

# ============================================================
# КАРТИНКИ (OpenAI Flare low + Pollinations fallback)
# ============================================================
def download_image(scene_text, seed):
    """OpenAI Flare (low) → Pollinations с обрезкой логотипа."""
    clean_img = "".join(c for c in scene_text if c.isalnum() or c.isspace() or c in ".,-")[:220].strip()
    base_prompt = f"Cinematic photography, highly detailed, 8k resolution, dramatic lighting, photorealistic. Scene: {clean_img}. No text, no watermark."
    
    img_bytes = None
    source = "unknown"

    if OPENAI_KEY:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=OPENAI_KEY)
            models_to_try = ["gpt-image-2.5-flare", "chatgpt-image-latest", "gpt-image-2"]
            for model_name in models_to_try:
                log(f"🎨 [OpenAI] Пробую '{model_name}' (quality=low)...")
                try:
                    response = client.images.generate(
                        model=model_name, prompt=base_prompt, n=1,
                        size="1024x1024", quality="low")
                    if hasattr(response.data[0], 'url') and response.data[0].url:
                        r = requests.get(response.data[0].url, timeout=60)
                        if r.status_code == 200 and len(r.content) > 10000:
                            img_bytes = r.content
                            source = "openai"
                            log(f"🏆 УСПЕХ: OpenAI ({model_name})!")
                            break
                    elif hasattr(response.data[0], 'b64_json') and response.data[0].b64_json:
                        img_bytes = base64.b64decode(response.data[0].b64_json)
                        source = "openai"
                        log(f"🏆 УСПЕХ: OpenAI ({model_name}) via Base64!")
                        break
                except Exception as e:
                    err = str(e).lower()
                    log(f"❌ OpenAI {model_name}: {str(e)[:100]}")
                    if "permission" in err or "rate_limit" in err or "quota" in err:
                        log("💸 Лимиты OpenAI — прекращаю.")
                        break
        except ImportError:
            log("⚠️ openai не установлен.")
        except Exception as e:
            log(f"🔥 OpenAI client: {e}")

    if not img_bytes:
        log("🔄 Fallback: Pollinations (Flux)...")
        silhouette_boost = ", silhouette from behind, shadow figure, back view only, mysterious atmosphere, foggy background, depth of field, bokeh, professional color grading, vibrant colors"
        anti_artifacts = "face, eyes, mouth, nose, ears, hair details, cartoon, anime, painting, drawing, sketch, illustration, abstract, surreal, distorted face, extra limbs, blurry, low quality, ugly, deformed"
        final_prompt = base_prompt + silhouette_boost
        for attempt in range(2):
            current_seed = seed + attempt * 500
            url = f"{POLLINATIONS_API}{requests.utils.quote(final_prompt)}?nologo=true&seed={current_seed}&model=flux&width=768&height=768&negative_prompt={requests.utils.quote(anti_artifacts)}"
            try:
                r = requests.get(url, timeout=300)
                if r.status_code == 200 and len(r.content) > 10000:
                    try:
                        im_check = Image.open(io.BytesIO(r.content)).convert("L")
                        avg = sum(im_check.getdata()) / (im_check.width * im_check.height)
                        if avg < 30: continue
                    except: pass
                    img_bytes = r.content
                    source = "pollinations"
                    log(f"✅ Pollinations успешен! (Попытка {attempt+1})")
                    break
            except Exception as e:
                log(f"⚠️ Pollinations: {e}")
            time.sleep(2)

    if not img_bytes:
        log("❌ ВСЕ ПОПЫТКИ ГЕНЕРАЦИИ ПРОВАЛИЛИСЬ")
        return None

    # Обрезаем логотип Pollinations
    if source == "pollinations":
        log("✂️ Обрезаю логотип pollinations.ai...")
        try:
            im = Image.open(io.BytesIO(img_bytes))
            w, h = im.size
            im = im.crop((0, 0, w, int(h * 0.96)))
            buf = io.BytesIO()
            im.save(buf, format="JPEG", quality=90)
            img_bytes = buf.getvalue()
            log("✅ Логотип удалён.")
        except Exception as e:
            log(f"⚠️ Обрезка: {e}")

    return img_bytes

def convert_to_jpeg(img_bytes):
    if not img_bytes: return None
    try:
        im = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        im.thumbnail((800, 800), Image.Resampling.LANCZOS)
        im = ImageEnhance.Contrast(im).enhance(1.1)
        im = ImageEnhance.Sharpness(im).enhance(1.3)
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=90, optimize=True, progressive=True)
        data = buf.getvalue()
        log(f"🖼 Final: {im.size[0]}x{im.size[1]}, {len(data)//1024} KB")
        return data
    except Exception as e:
        log(f"⚠️ JPEG: {e}")
        return img_bytes

def commit_image(img_file):
    try:
        subprocess.run(["git", "config", "user.name", "github-actions[bot]"], check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "github-actions[bot]@users.noreply.github.com"], check=True, capture_output=True)
        subprocess.run(["git", "add", img_file], check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", f"chore: add max image {os.path.basename(img_file)} [skip ci]"], check=True, capture_output=True)
        subprocess.run(["git", "push"], check=True, capture_output=True)
        log(f"✅ Image {img_file} committed")
        return True
    except Exception as e:
        log(f"⚠️ Image commit: {e}")
        return False

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
                up = requests.post(f"{base}/uploads", headers=hdr,
                    params={"type": "image", "chat_id": chat_val}, timeout=60, verify=False).json()
                up_url = up.get("url") if isinstance(up, dict) else None
                if not up_url: continue
                if img_bytes:
                    ru = requests.post(up_url, files={"file": ("cover.jpg", img_bytes, "image/jpeg")},
                        timeout=120, verify=False).json()
                else:
                    ru = {"photos": {"0": {"token": "no_image"}}}
                tok = None
                if isinstance(ru, dict):
                    ph = ru.get("photos") or {}
                    if isinstance(ph, dict):
                        for v in ph.values():
                            if isinstance(v, dict) and v.get("token"):
                                tok = v["token"]; break
                    tok = tok or ru.get("token") or ru.get("file")
                if not tok: continue
                payload = {"text": text[:8000]}
                if tok != "no_image":
                    payload["attachments"] = [{"type": "image", "payload": {"token": tok}}]
                r = requests.post(f"{base}/messages", headers=hdr,
                    params={"chat_id": chat_val}, json=payload, timeout=60, verify=False).json()
                if isinstance(r, dict) and (r.get("success") is True or isinstance(r.get("message"), dict)):
                    log(f"✅ MAX: Пост отправлен ({len(text)} симв.)")
                    return True
            except Exception:
                continue
    return False

# ============================================================
# BLACKLIST (отдельный от основного агента)
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
    day = datetime.date.today().toordinal()
    log(f"📅 День {day} — генерация лонгрида для MAX")

    # Случайный выбор: книги или тайны (70% тайн, как в основном агенте)
    is_mystery = random.random() < 0.7
    mystery_data, book_data = None, None

    if is_mystery and os.path.exists("mysteries.json"):
        try:
            mysteries = json.load(open("mysteries.json", encoding="utf-8"))
            # Фильтр: берём только неиспользованные
            used = set(load_json(MAX_USED, []))
            pool = [m for m in mysteries if m["topic"] not in used]
            if not pool:
                log("⚠️ Все тайны использованы — сброс blacklist")
                pool = mysteries
                save_json(MAX_USED, [])
            mystery_data = random.choice(pool)
            log(f"🔮 Mystery: {mystery_data['topic']}")
        except Exception as e:
            log(f"⚠️ mysteries.json: {e}")
            is_mystery = False

    if not is_mystery:
        try:
            books = json.load(open("books.json", encoding="utf-8"))["books"]
            used = set(load_json(MAX_USED, []))
            pool = [b for b in books if b["title"] not in used]
            if not pool:
                log("⚠️ Все книги использованы — сброс")
                pool = books
                save_json(MAX_USED, [])
            book_data = random.choice(pool)
            log(f"📚 Book: «{book_data['title']}»")
        except Exception as e:
            log(f"❌ books.json: {e}")
            raise SystemExit(1)

    # Генерация лонгрида
    if is_mystery:
        post = build_max_mystery_post(mystery_data, day)
        img_prompt = mystery_data.get("image_prompt", f"Mysterious ancient artifact, {mystery_data['topic']}")
        topic_key = mystery_data["topic"]
    else:
        post = build_max_book_post(book_data, day)
        img_prompt = post[:150]
        topic_key = book_data["title"]

    log(f"📝 Пост: {len(post)} симв.")

    # Картинка
    img_bytes = None
    run_no = int(os.environ.get("GITHUB_RUN_NUMBER", "0"))
    raw = download_image(img_prompt, day + 5000000 + (run_no % 100))
    if raw:
        img_bytes = convert_to_jpeg(raw)
        if img_bytes:
            os.makedirs("img_max", exist_ok=True)
            img_file = f"img_max/max_{day}.jpg"
            with open(img_file, "wb") as f: f.write(img_bytes)
            commit_image(img_file)

    # Публикация в MAX
    ok = max_post(img_bytes, post)

    # Обновляем blacklist
    used_list = load_json(MAX_USED, [])
    if topic_key not in used_list:
        used_list.append(topic_key)
    save_json(MAX_USED, used_list[-500:])

    history = load_json(MAX_HISTORY, [])
    history.append({"date": datetime.date.today().isoformat(), "topic": topic_key,
                    "kind": "mystery" if is_mystery else "book", "len": len(post)})
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
