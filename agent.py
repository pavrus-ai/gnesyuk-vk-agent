# -*- coding: utf-8 -*-
import os, json, datetime, requests, time, io, glob, base64, uuid, urllib3, re, random, subprocess
from PIL import Image, ImageEnhance, ImageStat
urllib3.disable_warnings()

# ============================================================
# ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ
# ============================================================
GROQ_KEY = os.environ.get("GROQ_KEY", "").strip()
GROQ_KEY2 = os.environ.get("GROQ_KEY2", "").strip()
OPENAI_KEY = os.environ.get("OPENAI_KEY", "").strip()

# GigaChat (Исправлено!)
GIGACHAT_CLIENT_ID = os.environ.get("GIGACHAT_CLIENT_ID1", "").strip()
GIGACHAT_CLIENT_SECRET = os.environ.get("GIGACHAT_CLIENT_SECRET1", "").strip()

VK_TOKEN = os.environ.get("VK_TOKEN", "").strip()
VK_USER_TOKEN = os.environ.get("VK_USER_TOKEN", "").strip()
VK_GROUP_ID = os.environ.get("VK_GROUP_ID", "").strip().lstrip("-")
TG_BOT = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TG_CHAT = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
MAX_TOKEN = os.environ.get("MAX_BOT_TOKEN", "").strip()
MAX_CHAT = os.environ.get("MAX_CHAT_ID", "").strip()
LINK_IN_TG = os.environ.get("LINK_IN_TG", "1").strip() != "0"

SCHEDULE = os.environ.get("SCHEDULE", "").strip()
TEST_IMAGE = os.environ.get("TEST_IMAGE", "").strip()
PUBLISH_CRON = "0 3 * * *" 

VK_API = "https://api.vk.com/method/"
VK_V = "5.131"
ATT_CACHE = "vk_att.json"
PENDING = "pending_attach.json"
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

def log(msg):
    print(msg, flush=True)

log("Версия ℹ️ gnesyuk-vk-agent v27.3 (Optimized OpenAI Flare + Safe VK Publish)")

# ============================================================
# ИИ-ТЕКСТ
# ============================================================
def _extract(r):
    try: return r["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError): return None

_GIGACHAT_TOKEN, _GIGACHAT_TOKEN_EXPIRY = None, 0

def get_gigachat_token():
    global _GIGACHAT_TOKEN, _GIGACHAT_TOKEN_EXPIRY
    if not GIGACHAT_CLIENT_ID or not GIGACHAT_CLIENT_SECRET: 
        log("⚠️ GigaChat keys missing in env")
        return None
    
    if _GIGACHAT_TOKEN and time.time() < _GIGACHAT_TOKEN_EXPIRY: 
        return _GIGACHAT_TOKEN
    
    try:
        credentials = base64.b64encode(f"{GIGACHAT_CLIENT_ID}:{GIGACHAT_CLIENT_SECRET}".encode()).decode()
        r = requests.post("https://ngw.devices.sberbank.ru:9443/api/v2/oauth",
            headers={"Authorization": f"Basic {credentials}", "RqUID": str(uuid.uuid4()), "Content-Type": "application/x-www-form-urlencoded"},
            data={"scope": "GIGACHAT_API_PERS"}, timeout=30, verify=False)
        
        if r.status_code == 200 and "access_token" in r.json():
            _GIGACHAT_TOKEN = r.json()["access_token"]
            _GIGACHAT_TOKEN_EXPIRY = time.time() + 1700
            log("✅ GigaChat token acquired")
            return _GIGACHAT_TOKEN
        else:
            log(f"⚠️ GigaChat auth failed: {r.text[:100]}")
    except Exception as e:
        log(f"⚠️ GigaChat exception: {e}")
    return None

def ai_text(prompt, minlen=300, rescue_min=200):
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
                json={"model": "GigaChat:latest", "temperature": 0.9, "max_tokens": 2000, "messages": [{"role": "user", "content": prompt + RU}]},
                timeout=90, verify=False)
            if r.status_code == 200:
                res = take(r.json()["choices"][0]["message"]["content"].strip(), "gigachat")
                if res: return res
        except Exception as e:
            log(f"⚠️ GigaChat request error: {e}")

    # 2. Groq
    for key in (GROQ_KEY, GROQ_KEY2):
        if not key: continue
        for model in GROQ_MODELS:
            try:
                r = requests.post("https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {key}"},
                    json={"model": model, "temperature": 0.8, "messages": [{"role": "user", "content": prompt + RU}]}, timeout=60).json()
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
        skip = False
        for prefix in bad_prefixes:
            if stripped.startswith(prefix):
                skip = True
                break
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

def safe_trim(text, limit):
    if len(text) <= limit:
        return text
    cut_pos = max(text.rfind("."), text.rfind("!"), text.rfind("?"), text.rfind("\n"))
    if cut_pos > limit * 0.7:
        return text[:cut_pos+1]
    return text[:limit].rsplit(' ', 1)[0] + "..."

# ============================================================
# ГЕНЕРАЦИЯ ПОСТОВ
# ============================================================
def build_book_post(book, day):
    t, a, s = book["title"], book["about"], book["series"]
    prompt = (f"Напиши пост-анонс для соцсетей о романе Павла Гнесюка «{t}» (серия «{s}»). "
              f"Сюжет: {a}. Требования: 1. ТОЛЬКО русский язык. "
              f"2. Первая строка — ЭМОЦИОНАЛЬНЫЙ КРЮЧОК (до 90 символов). "
              f"3. Объем СТРОГО 550-650 символов (это критично!). "
              f"4. Живой стиль, без слов 'инновационный', 'стоит отметить'. "
              f"5. В конце НЕ добавляй ссылки, я добавлю их сам."
              + META_BAN)
    txt = ai_text(prompt, minlen=500, rescue_min=400)
    return clean_txt(txt) if txt else f"РОМАН «{t.upper()}»: {a}"

def build_mystery_post(mystery, day):
    topic = mystery["topic"]
    facts = "\n".join([f"- {f}" for f in mystery["facts"]])
    prompt = (f"Напиши захватывающий пост на тему: {topic}. "
              f"Используй эти факты: {facts}. "
              f"Требования: 1. ТОЛЬКО русский язык. "
              f"2. Первая строка — ЭМОЦИОНАЛЬНЫЙ КРЮЧОК (до 90 символов). "
              f"3. Объем СТРОГО 550-650 символов (это критично!). "
              f"4. Живой, интригующий стиль, без нейрослопа. "
              f"5. В конце НЕ добавляй ссылки, я добавлю их сам."
              + META_BAN)
    txt = ai_text(prompt, minlen=500, rescue_min=400)
    return clean_txt(txt) if txt else f"Загадка: {topic}\n\n{mystery['facts'][0]}"

# ============================================================
# КАРТИНКИ v27.3: Оптимизированный OpenAI Flare + Fallback
# ============================================================
def check_image_quality(img_bytes):
    """Проверяет, не слишком ли темная или серая картинка."""
    try:
        im = Image.open(io.BytesIO(img_bytes)).convert("L")
        stat = ImageStat.Stat(im)
        mean_brightness = stat.mean[0]
        
        # Допускаем диапазон яркости 30-230
        if mean_brightness < 30 or mean_brightness > 230:
            return False, f"Brightness {mean_brightness:.1f} (extreme)"
        return True, "OK"
    except Exception as e:
        return False, f"Analysis error: {e}"

def download_image(scene_text, seed):
    """
    v27.3: Экономичная стратегия OpenAI (Flare first) + Fallback Pollinations.
    Цель: Максимум качества при минимуме затрат ($10 надолго).
    """
    clean_img = "".join(c for c in scene_text if c.isalnum() or c.isspace() or c in ".,-")[:220].strip()
    
    # Промпт для генерации
    base_prompt = f"Cinematic photography, highly detailed, 8k resolution, dramatic lighting, photorealistic. Scene: {clean_img}. No text, no watermark."
    
    img_bytes = None

    # --- БЛОК 1: Попытки с моделями OpenAI (Приоритет: ДЕШЕВО -> ДОРОГО) ---
    if OPENAI_KEY:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=OPENAI_KEY)
            
            # Список моделей: сначала самая выгодная (Flare), потом универсальная, потом топовая
            models_to_try = [
                "gpt-image-2.5-flare",          # 💰 Самый выгодный вариант (быстро/дешево)
                "chatgpt-image-latest",         # 🔄 Стандартная latest (если flare недоступен)
                "gpt-image-2"                   # ⚙️ Старая добрая двойка (запасной)
            ]
            
            for model_name in models_to_try:
                log(f"🎨 [OpenAI] Пробую экономичную модель '{model_name}'...")
                try:
                    # Используем quality="standard" для экономии. 
                    response = client.images.generate(
                        model=model_name,
                        prompt=base_prompt,
                        n=1,
                        size="1024x1024",
                        quality="standard" 
                    )
                    
                    # Проверяем результат (URL или Base64)
                    if hasattr(response.data[0], 'url') and response.data[0].url:
                        img_url = response.data[0].url
                        log(f"✅ OpenAI ({model_name}) вернул URL. Скачиваю...")
                        
                        r = requests.get(img_url, timeout=60)
                        if r.status_code == 200 and len(r.content) > 10000:
                            img_bytes = r.content
                            log(f"🏆 УСПЕХ: Картинка получена от OpenAI ({model_name})!")
                            break # Выходим из цикла, успех достигнут
                        
                    elif hasattr(response.data[0], 'b64_json') and response.data[0].b64_json:
                        log(f"✅ OpenAI ({model_name}) вернул Base64. Декодирую...")
                        img_bytes = base64.b64decode(response.data[0].b64_json)
                        log(f"🏆 УСПЕХ: Картинка получена от OpenAI ({model_name}) via Base64!")
                        break
                    
                    else:
                        log(f"⚠️ OpenAI ({model_name}): Ответ пустой или неизвестного формата.")
                        
                except Exception as e:
                    error_str = str(e).lower()
                    log(f"❌ Ошибка OpenAI ({model_name}): {str(e)[:100]}")
                    
                    # Если ошибка связана с правами доступа или лимитами — прекращаем попытки
                    if "permission" in error_str or "rate_limit" in error_str or "quota" in error_str:
                        log("💸 Лимиты OpenAI исчерпаны или нет прав. Прекращаю попытки с этим ключом.")
                        break 

        except ImportError:
            log("⚠️ Библиотека 'openai' не найдена. Проверьте pip install openai в YAML.")
        except Exception as e:
            log(f"🔥 Критическая ошибка инициализации OpenAI клиента: {e}")

    # --- БЛОК 2: Fallback на Pollinations (Бесплатно и надежно) ---
    if not img_bytes:
        log("🔄 Переключаюсь на бесплатный фолбэк: Pollinations (Flux)...")
        
        # Стратегия силуэтов для избежания кривых лиц
        silhouette_boost = ", silhouette from behind, shadow figure, back view only, mysterious atmosphere, foggy background, depth of field, bokeh, professional color grading, vibrant colors"
        anti_artifacts = "face, eyes, mouth, nose, ears, hair details, cartoon, anime, painting, drawing, sketch, illustration, abstract, surreal, distorted face, extra limbs, blurry, low quality, ugly, deformed"
        
        final_prompt = base_prompt + silhouette_boost
        
        # Пытаемся 2 раза с разными сидами
        for attempt in range(2):
            current_seed = seed + attempt * 500
            
            encoded_prompt = requests.utils.quote(final_prompt)
            encoded_negative = requests.utils.quote(anti_artifacts)
            
            url = f"{POLLINATIONS_API}{encoded_prompt}?nologo=true&seed={current_seed}&model=flux&width=768&height=768&negative_prompt={encoded_negative}"
            
            try:
                r = requests.get(url, timeout=300)
                
                if r.status_code == 200 and len(r.content) > 10000:
                    # Быстрая проверка яркости (чтобы не было черных квадратов)
                    try:
                        im_check = Image.open(io.BytesIO(r.content)).convert("L")
                        avg_brightness = sum(im_check.getdata()) / (im_check.width * im_check.height)
                        
                        if avg_brightness < 30: # Слишком темно
                             log(f"⚠️ Pollinations попытка {attempt+1}: Темная картинка. Пробую другой сид...")
                             continue
                    except: pass # Если PIL не открыл, просто берем как есть

                    img_bytes = r.content
                    log(f"✅ Pollinations успешен! (Попытка {attempt+1})")
                    break
                else:
                    log(f"⚠️ Pollinations попытка {attempt+1}: HTTP {r.status_code}")
                    
            except Exception as e:
                log(f"⚠️ Pollinations исключение: {e}")
            
            time.sleep(2)

    if not img_bytes:
        log("❌ ВСЕ ПОПЫТКИ ГЕНЕРАЦИИ ПРОВАЛИЛИСЬ")
        return None
        
    return img_bytes

def convert_to_jpeg(img_bytes):
    """Улучшенная конвертация: резкость + контраст + прогрессивное сжатие."""
    if not img_bytes: return None
    try:
        im = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        
        # 1. Масштабируем до квадрата 800x800
        im.thumbnail((800, 800), Image.Resampling.LANCZOS)
        
        # 2. Немного повышаем контраст и резкость
        enhancer_contrast = ImageEnhance.Contrast(im)
        im = enhancer_contrast.enhance(1.1) 
        
        enhancer_sharpness = ImageEnhance.Sharpness(im)
        im = enhancer_sharpness.enhance(1.3) 
        
        # 3. Сохраняем в высоком качестве
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=90, optimize=True, progressive=True)
        data = buf.getvalue()
        
        log(f"🖼 Final processing: {im.size[0]}x{im.size[1]}, {len(data)//1024} KB")
        return data
    except Exception as e:
        log(f"⚠️ JPEG conversion error: {e}")
        return img_bytes

def commit_image(img_file):
    try:
        subprocess.run(["git", "config", "user.name", "github-actions[bot]"], check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "github-actions[bot]@users.noreply.github.com"], check=True, capture_output=True)
        subprocess.run(["git", "add", img_file], check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", f"chore: add image {os.path.basename(img_file)} [skip ci]"], check=True, capture_output=True)
        subprocess.run(["git", "push"], check=True, capture_output=True)
        log(f"✅ Image {img_file} committed")
        return True
    except Exception as e:
        log(f"⚠️ Image commit failed: {e}")
        return False

# ============================================================
# ВК / TG / MAX (Стандартная логика, но ВК публикуется ВСЕГДА)
# ============================================================
def vk_call(method, params=None, token=None, retries=4):
    p = dict(params or {})
    p["access_token"] = token or VK_TOKEN
    p["v"] = VK_V
    for attempt in range(retries):
        try:
            r = requests.post(VK_API + method, data=p, timeout=30).json()
            if "error" in r and r["error"].get("error_code") == 9:
                time.sleep(15 * (attempt + 1))
                continue
            return r.get("response") if "error" not in r else None
        except Exception:
            time.sleep(5)
    return None

def flood_probe():
    srv = vk_call("photos.getWallUploadServer", {"owner_id": "-" + VK_GROUP_ID}, token=VK_USER_TOKEN, retries=1)
    ok = bool(srv and "upload_url" in srv)
    log(f"🌡 Flood probe: {'GREEN' if ok else 'RED'}")
    return ok, srv

def finish_upload(srv, img_bytes):
    try:
        r = requests.post(srv["upload_url"], files={"photo": ("cover.jpg", img_bytes, "image/jpeg")}, timeout=120).json()
        if r.get("photo") and r.get("hash"):
            saved = vk_call("photos.saveWallPhoto", {"owner_id": "-" + VK_GROUP_ID, "photo": r["photo"], "server": r.get("server", ""), "hash": r.get("hash", "")}, token=VK_USER_TOKEN, retries=2)
            if saved:
                p = saved[0]
                return f"photo{p['owner_id']}_{p['id']}_{p.get('access_key', '')}".rstrip("_")
    except Exception: pass
    return None

def vk_post_wall(text, attachment=None):
    res = vk_call("wall.post", {"owner_id": "-" + VK_GROUP_ID, "message": text, "attachments": attachment, "from_group": 1})
    if not res and VK_USER_TOKEN:
        res = vk_call("wall.post", {"owner_id": "-" + VK_GROUP_ID, "message": text, "attachments": attachment, "from_group": 1}, token=VK_USER_TOKEN)
    if res:
        log(f"✅ VK: Post published: https://vk.com/wall-{VK_GROUP_ID}_{res.get('post_id')}")
        return res
    return None

def tg_post(img_bytes, caption):
    if not TG_BOT or not TG_CHAT: return False
    
    # Обрезка для TG лимита
    if len(caption) > 1000:
        caption = caption[:1000] + "..."

    if img_bytes:
        try:
            r = requests.post(f"https://api.telegram.org/bot{TG_BOT}/sendPhoto",
                data={"chat_id": TG_CHAT, "caption": caption},
                files={"photo": ("cover.jpg", img_bytes, "image/jpeg")}, timeout=120).json()
            if r.get("ok"):
                log(f"✅ TG: Photo post sent")
                return True
        except Exception as e:
            log(f"⚠️ TG photo error: {e}")
    
    # Fallback текст
    try:
        r = requests.post(f"https://api.telegram.org/bot{TG_BOT}/sendMessage",
            data={"chat_id": TG_CHAT, "text": caption}, timeout=60).json()
        if r.get("ok"):
            log(f"✅ TG: Text post sent")
            return True
    except Exception as e:
        log(f"⚠️ TG text error: {e}")
    return False

def max_post(img_bytes, text):
    if not MAX_TOKEN or not MAX_CHAT: return False
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
                    tok = tok or ru.get("token") or ru.get("file")
                
                if not tok: continue
                
                payload = {"text": text[:4000]}
                if tok != "no_image":
                    payload["attachments"] = [{"type": "image", "payload": {"token": tok}}]
                
                r = requests.post(f"{base}/messages", headers=hdr, params={"chat_id": chat_val}, json=payload, timeout=60, verify=False).json()
                
                if isinstance(r, dict) and (r.get("success") is True or isinstance(r.get("message"), dict)):
                    log(f"✅ MAX: Post sent")
                    return True
            except Exception:
                continue
    return False

def save_pending(day, post_id, caption, img_file):
    json.dump({"day": day, "post_id": post_id, "caption": caption, "img_file": img_file}, open(PENDING, "w", encoding="utf-8"), ensure_ascii=False)
    log(f"💾 pending_attach.json created")

def load_pending():
    try:
        if os.path.exists(PENDING): return json.load(open(PENDING, encoding="utf-8"))
    except Exception: pass
    return None

def run_tick(day):
    log("🕐 Mode: TICK")
    pend = load_pending()
    if not pend or pend.get("day", 0) < day - 1:
        if os.path.exists(PENDING): os.remove(PENDING)
        return
    green, srv = flood_probe()
    if not green: return
    
    img_bytes = None
    if os.path.exists(pend["img_file"]):
        with open(pend["img_file"], "rb") as f: img_bytes = f.read()
    if not img_bytes:
        os.remove(PENDING); return
    
    att = finish_upload(srv, img_bytes)
    if att:
        res = vk_call("wall.edit", {"owner_id": "-" + VK_GROUP_ID, "post_id": pend["post_id"], "message": pend["caption"], "attachments": att}, retries=2)
        if res:
            log(f"✅ VK: Image attached to post {pend['post_id']}")
            os.remove(PENDING)

def main():
    day = datetime.date.today().toordinal()
    mode = "publish" if (not SCHEDULE or SCHEDULE == PUBLISH_CRON) else "tick"
    
    if mode == "tick":
        run_tick(day)
        return

    log("📢 Mode: PUBLICATION")
    
    is_mystery = random.random() < 0.7
    mystery_data, book_data = None, None
    platforms = ["vk", "tg", "max"]
    
    if is_mystery and os.path.exists("mysteries.json"):
        try:
            mysteries = json.load(open("mysteries.json", encoding="utf-8"))
            mystery_data = random.choice(mysteries)
            log(f"🔮 Mystery topic: {mystery_data['topic']}")
            platforms = mystery_data.get("platforms", ["tg", "max"])
        except Exception:
            is_mystery = False

    if not is_mystery:
        books = json.load(open("books.json", encoding="utf-8"))["books"]
        book_data = books[day % len(books)]
        log(f"📚 Book selected: «{book_data['title']}»")

    if is_mystery:
        post = build_mystery_post(mystery_data, day)
        link_part = "\n\nКниги о подобных фактах: 📖 https://www.litres.ru/author/pavel-gnesuk/"
        tags = MYSTERY_TAGS
        img_prompt = mystery_data.get("image_prompt", f"Mysterious ancient artifact, {mystery_data['topic']}")
    else:
        post = build_book_post(book_data, day)
        link = book_data.get("url", "")
        link_part = f"\n\n📖 Читайте на ЛитРес: {link}" if (link and LINK_IN_TG) else ""
        tags = BOOK_TAGS
        img_prompt = post[:150]

    max_post_len = 600
    post = safe_trim(post, max_post_len)
    caption = post + link_part + "\n\n" + tags
    log(f"📝 Post length: {len(caption)} chars.")

    img_bytes, img_file = None, ""
    if TEST_IMAGE and os.path.exists(TEST_IMAGE):
        with open(TEST_IMAGE, "rb") as f: img_bytes = f.read()
        img_file = TEST_IMAGE
    else:
        run_no = int(os.environ.get("GITHUB_RUN_NUMBER", "0"))
        raw = download_image(img_prompt, day + 3000000 + (run_no % 100))
        if raw:
            img_bytes = convert_to_jpeg(raw)
    
    if img_bytes and not img_file:
        os.makedirs("img", exist_ok=True)
        img_file = f"img/vk_{day}.jpg"
        with open(img_file, "wb") as f: f.write(img_bytes)
        commit_image(img_file)

    att = None
    ok_vk, ok_tg, ok_max = False, False, False

    # --- ПУБЛИКАЦИЯ ВК (ИСПРАВЛЕНО: Публикуем всегда, даже без картинки) ---
    if "vk" in platforms:
        if img_bytes:
            green, srv = flood_probe()
            if green:
                att = finish_upload(srv, img_bytes)
            else:
                log("⚠️ Red flood: image will go to pending")
        
        # Публикуем пост (с картинкой или без)
        res = vk_post_wall(caption, att)
        ok_vk = bool(res)
        
        # Если картинка есть, но не приложилась из-за флуда — сохраняем в pending
        if ok_vk and img_bytes and not att:
            save_pending(day, res["post_id"], caption, img_file)

    if "tg" in platforms:
        ok_tg = tg_post(img_bytes, caption)
        
    if "max" in platforms:
        ok_max = max_post(img_bytes, caption)

    log("=" * 50)
    log(f"✅ FINISH: VK={'YES' if ok_vk else 'NO'}, TG={'YES' if ok_tg else 'NO'}, MAX={'YES' if ok_max else 'NO'}")
    if not (ok_vk or ok_tg or ok_max):
        raise SystemExit(1)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"❌ CRITICAL ERROR: {e}")
        raise
