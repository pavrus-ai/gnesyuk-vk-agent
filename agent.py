# -*- coding: utf-8 -*-
import os, json, datetime, requests, time, io, glob, base64, uuid, urllib3, re, random, subprocess
from PIL import Image, ImageEnhance
urllib3.disable_warnings()

GROQ_KEY = os.environ.get("GROQ_KEY", "").strip()
GROQ_KEY2 = os.environ.get("GROQ_KEY2", "").strip()
OR_KEY = os.environ.get("OPENROUTER_KEY", "").strip()
OR_KEY2 = os.environ.get("OPENROUTER_KEY2", "").strip()
CEREBRAS_KEY = os.environ.get("CEREBRAS_KEY", "").strip()
MISTRAL_KEY = os.environ.get("MISTRAL_KEY", "").strip()
OPENAI_KEY = os.environ.get("OPENAI_KEY", "").strip()
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
DOC_FALLBACK = os.environ.get("DOC_FALLBACK", "0").strip() == "1"
PUBLISH_CRON = "0 3 * * *"

VK_API = "https://api.vk.com/method/"
VK_V = "5.131"
ATT_CACHE = "vk_att.json"
PENDING = "pending_attach.json"
POLLINATIONS_API = "https://image.pollinations.ai/prompt/"
MAX_APIS = ["https://platform-api.max.ru", "https://platform-api2.max.ru", "https://botapi.max.ru"]

BOOK_TAGS = "#ПавелГнесюк #книги #авторскийблог #писатель"
MYSTERY_TAGS = "#ПавелГнесюк #тайны #история #загадки"
RU = "\n\nВАЖНО: Пиши ТОЛЬКО на русском языке."

GROQ_MODELS = ["meta-llama/llama-4-scout-17b-16e-instruct", "meta-llama/llama-4-maverick-17b-128e-instruct", "openai/gpt-oss-120b", "llama-3.1-8b-instant"]

# ЖЁСТКИЙ запрет на клише и шаблонные фразы
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
    "ПРИМЕР ХОРОШЕГО НАЧАЛА: «Владимир Тихонин расследует покушение...» "
    "ПРИМЕР ПЛОХОГО НАЧАЛА: «Погрузитесь в тайну древних книг!» "
)

def log(msg):
    print(msg, flush=True)

log("Версия ℹ️ gnesyuk-vk-agent v23.2 (70% тайн / 30% книг; защита от мета-артефактов и клише; MAX с полной диагностикой; картинки 800×800)")

# ============================================================
# ИИ-ТЕКСТ
# ============================================================
def _extract(r):
    try: return r["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError): return None

_GIGACHAT_TOKEN, _GIGACHAT_TOKEN_EXPIRY = None, 0

def get_gigachat_token():
    global _GIGACHAT_TOKEN, _GIGACHAT_TOKEN_EXPIRY
    if not GIGACHAT_CLIENT_ID or not GIGACHAT_CLIENT_SECRET: return None
    if _GIGACHAT_TOKEN and time.time() < _GIGACHAT_TOKEN_EXPIRY: return _GIGACHAT_TOKEN
    try:
        credentials = base64.b64encode(f"{GIGACHAT_CLIENT_ID}:{GIGACHAT_CLIENT_SECRET}".encode()).decode()
        r = requests.post("https://ngw.devices.sberbank.ru:9443/api/v2/oauth",
            headers={"Authorization": f"Basic {credentials}", "RqUID": str(uuid.uuid4()), "Content-Type": "application/x-www-form-urlencoded"},
            data={"scope": "GIGACHAT_API_PERS"}, timeout=30, verify=False)
        if r.status_code == 200 and "access_token" in r.json():
            _GIGACHAT_TOKEN = r.json()["access_token"]
            _GIGACHAT_TOKEN_EXPIRY = time.time() + 1700
            return _GIGACHAT_TOKEN
    except Exception as e:
        log(f"⚠️ GigaChat auth: {e}")
    return None

def ai_text(prompt, minlen=300, rescue_min=200):
    best_res = ""
    def take(res, label):
        nonlocal best_res
        if not res: return None
        res = _strip_meta(res)
        if len(res) >= minlen:
            log(f"✅ Успех: {label}, {len(res)} симв.")
            return res
        if len(res) > len(best_res): best_res = res
        return None

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
        except Exception: pass

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

def _strip_subheadings(text):
    lines = text.split("\n")
    cleaned = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if (len(stripped) < 40 and stripped and 
            not stripped[-1] in ".!?:…" and 
            i + 1 < len(lines) and lines[i+1].strip()):
            cleaned.append(stripped + ": " + lines[i+1].strip())
            i += 2
            continue
        cleaned.append(line)
        i += 1
    return "\n".join(cleaned).strip()

def _fix_bad_opening(text):
    bad_openings = [
        "погрузитесь", "откройте", "узнайте", "представляем",
        "встречайте", "добро пожаловать", "читайте", "новый роман",
        "новая книга", "новая глава", "этот захватывающий", "этот увлекательный",
        "погрузись", "открой для себя"
    ]
    lines = text.split("\n")
    while lines:
        first = lines[0].strip().lower()
        if any(bad in first for bad in bad_openings):
            log(f" Вырезана плохая первая строка: {lines[0][:80]}")
            lines.pop(0)
        else:
            break
    return "\n".join(lines).strip()

def clean_txt(t):
    t = t.replace("**", "").replace("##", "").replace("#", "").strip()
    t = _strip_meta(t)
    t = _strip_subheadings(t)
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
              f"3. Объем СТРОГО 750-850 символов (это критично!). "
              f"4. Живой стиль, без слов 'инновационный', 'стоит отметить'. "
              f"5. В конце НЕ добавляй ссылки, я добавлю их сам."
              + META_BAN)
    txt = ai_text(prompt, minlen=700, rescue_min=600)
    return clean_txt(txt) if txt else f"РОМАН «{t.upper()}»: {a}"

def build_mystery_post(mystery, day):
    topic = mystery["topic"]
    facts = "\n".join([f"- {f}" for f in mystery["facts"]])
    prompt = (f"Напиши захватывающий пост на тему: {topic}. "
              f"Используй эти факты: {facts}. "
              f"Требования: 1. ТОЛЬКО русский язык. "
              f"2. Первая строка — ЭМОЦИОНАЛЬНЫЙ КРЮЧОК (до 90 символов). "
              f"3. Объем СТРОГО 750-850 символов (это критично!). "
              f"4. Живой, интригующий стиль, без нейрослопа. "
              f"5. В конце НЕ добавляй ссылки, я добавлю их сам."
              + META_BAN)
    txt = ai_text(prompt, minlen=700, rescue_min=600)
    return clean_txt(txt) if txt else f"Загадка: {topic}\n\n{mystery['facts'][0]}"

# ============================================================
# КАРТИНКИ
# ============================================================
def image_stats(img_bytes):
    try:
        im = Image.open(io.BytesIO(img_bytes)).convert("L")
        im.thumbnail((64, 64))
        px = list(im.tobytes())
        return True, sum(px) / len(px), sum(1 for p in px if p > 160) / len(px)
    except Exception:
        return False, 0.0, 0.0

def download_image(scene_text, seed):
    clean_img = "".join(c for c in scene_text if c.isalnum() or c.isspace() or c in ".,-")[:220].strip()
    base = f"Cinematic, mysterious, highly detailed, 8k, dramatic lighting. Scene: {clean_img}."
    p_openai = base + " People and faces allowed, anatomically perfect. No text, no watermark."
    p_poll = base + " People ONLY as distant silhouettes from behind. No text, no watermark."
    
    if OPENAI_KEY:
        try:
            r = requests.post("https://api.openai.com/v1/images/generations",
                headers={"Authorization": f"Bearer {OPENAI_KEY}", "Content-Type": "application/json"},
                json={"model": "gpt-image-1", "prompt": p_openai, "n": 1, "size": "1024x1024", "quality": "low"}, timeout=180).json()
            if "error" not in r and r.get("data"):
                return base64.b64decode(r["data"][0].get("b64_json", ""))
        except Exception: pass

    try:
        url = f"{POLLINATIONS_API}{requests.utils.quote(p_poll)}?nologo=true&seed={seed}&model=flux&width=800&height=450"
        r = requests.get(url, timeout=240)
        if r.status_code == 200: return r.content
    except Exception: pass
    return None

def convert_to_jpeg(img_bytes):
    try:
        im = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        im.thumbnail((800, 800))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=85, optimize=True)
        data = buf.getvalue()
        log(f"🖼 Финал: {im.size[0]}x{im.size[1]}, {len(data)} байт")
        return data
    except Exception:
        return img_bytes

def commit_image(img_file):
    try:
        subprocess.run(["git", "config", "user.name", "github-actions[bot]"], check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "github-actions[bot]@users.noreply.github.com"], check=True, capture_output=True)
        subprocess.run(["git", "add", img_file], check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", f"chore: add image {os.path.basename(img_file)} [skip ci]"], check=True, capture_output=True)
        subprocess.run(["git", "push"], check=True, capture_output=True)
        log(f"✅ Картинка {img_file} закоммичена")
        return True
    except Exception as e:
        log(f"⚠️ Коммит картинки не удался: {e}")
        return False

# ============================================================
# ВК
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
    log(f"🌡 Барометр флуда: {'ЗЁЛЕНЫЙ' if ok else 'КРАСНЫЙ'}")
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
        log(f"✅ ВК: пост опубликован: https://vk.com/wall-{VK_GROUP_ID}_{res.get('post_id')}")
    return res

# ============================================================
# TELEGRAM
# ============================================================
def tg_post(img_bytes, caption):
    if not TG_BOT or not TG_CHAT: return False
    try:
        r = requests.post(f"https://api.telegram.org/bot{TG_BOT}/sendPhoto",
            data={"chat_id": TG_CHAT, "caption": caption},
            files={"photo": ("cover.jpg", img_bytes, "image/jpeg")}, timeout=120).json()
        if r.get("ok"):
            log(f"✅ TG: пост отправлен в {TG_CHAT}")
            return True
        log(f"⚠️ TG: {str(r)[:200]}")
    except Exception as e:
        log(f"⚠️ TG ошибка: {e}")
    return False

# ============================================================
# MAX
# ============================================================
def max_post(img_bytes, text):
    if not MAX_TOKEN:
        log("ℹ️ MAX_BOT_TOKEN не задан — MAX пропущен")
        return False
    if not MAX_CHAT:
        log("ℹ️ MAX_CHAT_ID не задан — MAX пропущен")
        return False

    chat_val = int(MAX_CHAT) if MAX_CHAT.lstrip("-").isdigit() else MAX_CHAT
    log(f"️ MAX: chat_id = {chat_val} (тип: {type(chat_val).__name__})")

    bases = ["https://platform-api.max.ru", "https://platform-api2.max.ru", "https://botapi.max.ru"]
    headers_list = [{"Authorization": f"Bearer {MAX_TOKEN}"}, {"Authorization": MAX_TOKEN}]

    for base in bases:
        for hdr in headers_list:
            log(f"🔄 MAX: пробую {base} ...")
            try:
                up = requests.post(f"{base}/uploads", headers=hdr,
                                   params={"type": "image", "chat_id": chat_val},
                                   timeout=60, verify=False).json()
                log(f"   MAX uploads ответ: {str(up)[:200]}")
            except Exception as e:
                log(f"   ⚠️ MAX uploads ошибка сети: {e}")
                continue

            up_url = up.get("url") if isinstance(up, dict) else None
            if not up_url:
                log(f"   ⚠️ MAX: нет upload_url в ответе — пробую следующую базу")
                continue

            try:
                ru = requests.post(up_url,
                                   files={"data": ("cover.jpg", img_bytes, "image/jpeg")},
                                   timeout=120, verify=False).json()
                log(f"   MAX upload фото ответ: {str(ru)[:200]}")
            except Exception as e:
                log(f"   ⚠️ MAX upload фото ошибка: {e}")
                continue

            tok = None
            if isinstance(ru, dict):
                ph = ru.get("photos") or {}
                if isinstance(ph, dict):
                    for v in ph.values():
                        if isinstance(v, dict) and v.get("token"):
                            tok = v["token"]
                            break
                tok = tok or ru.get("token") or ru.get("file")

            if not tok:
                log(f"   ️ MAX: токен вложения не найден — пробую следующую базу")
                continue

            log(f"   ✅ MAX: токен вложения получен: {str(tok)[:30]}...")

            try:
                r = requests.post(f"{base}/messages", headers=hdr,
                                  params={"chat_id": chat_val},
                                  json={"text": text[:4000],
                                        "attachments": [{"type": "image", "payload": {"token": tok}}]},
                                  timeout=60, verify=False).json()
                log(f"   MAX messages ответ: {str(r)[:200]}")
            except Exception as e:
                log(f"   ⚠️ MAX messages ошибка: {e}")
                continue

            ok = isinstance(r, dict) and (r.get("success") is True or isinstance(r.get("message"), dict))
            if ok:
                m = r.get("message") or {}
                log(f"✅ MAX: пост отправлен (chat_id={chat_val}, id={m.get('id')})")
                return True
            else:
                log(f"   ️ MAX: ответ не успех — {str(r)[:150]}")

    log("❌ MAX: все базы API и заголовки исчерпаны — пост не отправлен")
    return False

# ============================================================
# PENDING / TICK
# ============================================================
def save_pending(day, post_id, caption, img_file):
    json.dump({"day": day, "post_id": post_id, "caption": caption, "img_file": img_file}, open(PENDING, "w", encoding="utf-8"), ensure_ascii=False)
    log(f"💾 pending_attach.json создан: пост {post_id} ждёт картинку {img_file}")

def load_pending():
    try:
        if os.path.exists(PENDING): return json.load(open(PENDING, encoding="utf-8"))
    except Exception: pass
    return None

def run_tick(day):
    log("🕐 Режим: ТИК (только барометр + докрепление картинки)")
    pend = load_pending()
    if not pend or pend.get("day", 0) < day - 1:
        if os.path.exists(PENDING): os.remove(PENDING)
        log("🧹 pending очищен (устарел или пуст)")
        return
    green, srv = flood_probe()
    if not green:
        log("⏳ Флуд красный — ждем следующий тик")
        return
    img_bytes = None
    if os.path.exists(pend["img_file"]):
        with open(pend["img_file"], "rb") as f: img_bytes = f.read()
    if not img_bytes:
        log(f"⚠️ Файл {pend['img_file']} не найден — сбрасываю pending")
        os.remove(PENDING)
        return
    
    att = finish_upload(srv, img_bytes)
    if att:
        res = vk_call("wall.edit", {"owner_id": "-" + VK_GROUP_ID, "post_id": pend["post_id"], "message": pend["caption"], "attachments": att}, retries=2)
        if res:
            log(f"✅ ВК: картинка докреплена к посту {pend['post_id']}")
            os.remove(PENDING)
        else:
            log("⚠️ wall.edit не смог докрепить — попробуем в следующем тике")
    else:
        log("⚠️ Загрузка на зелёном барометре не удалась — жду следующий тик")

# ============================================================
# ГЛАВНАЯ ЛОГИКА v23.2
# ============================================================
def main():
    day = datetime.date.today().toordinal()
    
    # При ручном запуске (SCHEDULE пустой) — всегда публикация
    if not SCHEDULE:
        mode = "publish"
    elif SCHEDULE == PUBLISH_CRON:
        mode = "publish"
    else:
        mode = "tick"
    
    log(f"🗓 Расписание: «{SCHEDULE or 'ручной'}» → режим: {mode}")
    
    if mode == "tick":
        run_tick(day)
        return

    log(" Режим: ПУБЛИКАЦИЯ")
    
    # 1. Выбираем тип контента: 70% шанс на тайну, 30% на книгу
    is_mystery = random.random() < 0.7
    mystery_data, book_data = None, None
    platforms = ["vk", "tg", "max"]
    
    if is_mystery and os.path.exists("mysteries.json"):
        try:
            mysteries = json.load(open("mysteries.json", encoding="utf-8"))
            mystery_data = random.choice(mysteries)
            log(f"🔮 Выбрана тема-тайна: {mystery_data['topic']}")
            platforms = mystery_data.get("platforms", ["tg", "max"])
        except Exception as e:
            log(f"⚠️ Ошибка mysteries.json: {e}. Переключаюсь на книгу.")
            is_mystery = False

    if not is_mystery:
        books = json.load(open("books.json", encoding="utf-8"))["books"]
        book_data = books[day % len(books)]
        log(f"📚 Выбрана книга: «{book_data['title']}»")

    # 2. Генерация текста
    if is_mystery:
        post = build_mystery_post(mystery_data, day)
        link_part = "\n\nКниги о подобных фактах: 📖 https://www.litres.ru/author/pavel-gnesuk/"
        tags = MYSTERY_TAGS
        img_prompt = mystery_data.get("image_prompt", f"Mysterious ancient artifact, {mystery_data['topic']}")
    else:
        post = build_book_post(book_data, day)
        link = book_data.get("url", "")
        link_part = f"\n\n Читайте на ЛитРес: {link}" if (link and LINK_IN_TG) else ""
        tags = BOOK_TAGS
        img_prompt = post[:150]

    # 3. Жесткая безопасная обрезка
    max_post_len = 850
    post = safe_trim(post, max_post_len)
    caption = post + link_part + "\n\n" + tags
    log(f"📝 Длина поста: {len(caption)} симв. (безопасно для TG)")
    log(f"✂️ Крючок поста: {caption.split(chr(10))[0][:120]}")

    # 4. Генерация и сохранение картинки
    img_bytes, img_file = None, ""
    if TEST_IMAGE and os.path.exists(TEST_IMAGE):
        with open(TEST_IMAGE, "rb") as f: img_bytes = f.read()
        img_file = TEST_IMAGE
    else:
        run_no = int(os.environ.get("GITHUB_RUN_NUMBER", "0"))
        for attempt in range(3):
            raw = download_image(img_prompt, day + 3000000 + (run_no % 100) + attempt * 7919)
            if raw:
                img_bytes = convert_to_jpeg(raw)
                break
    
    if img_bytes and not img_file:
        os.makedirs("img", exist_ok=True)
        img_file = f"img/vk_{day}.jpg"
        with open(img_file, "wb") as f: f.write(img_bytes)
        commit_image(img_file)

    # 5. Публикация
    att = None
    ok_vk, ok_tg, ok_max = False, False, False

    if "vk" in platforms and img_bytes:
        green, srv = flood_probe()
        if green:
            att = finish_upload(srv, img_bytes)
        else:
            log("⚠️ Флуд красный: картинка уйдёт в pending")
            
    if "vk" in platforms:
        res = vk_post_wall(caption, att)
        ok_vk = bool(res)
        if ok_vk and img_bytes and not att:
            save_pending(day, res["post_id"], caption, img_file)

    if "tg" in platforms:
        ok_tg = tg_post(img_bytes, caption)
        
    if "max" in platforms:
        ok_max = max_post(img_bytes, caption)

    log("=" * 50)
    log(f"✅ FINISH: ВК={'ДА' if ok_vk else 'НЕТ'}, TG={'ДА' if ok_tg else 'НЕТ'}, MAX={'ДА' if ok_max else 'НЕТ'}")
    if not (ok_vk or ok_tg or ok_max):
        raise SystemExit(1)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"❌ КРИТИЧЕСКАЯ ОШИБКА: {e}")
        raise
