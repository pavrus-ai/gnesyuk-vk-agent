import os, json, datetime, requests

VK_TOKEN = os.environ["VK_TOKEN"]
GROUP_ID = os.environ["VK_GROUP_ID"]
GROQ_KEY = os.environ.get("GROQ_KEY", "")
OPENROUTER_KEY = os.environ.get("OPENROUTER_KEY", "")
VK_API = "https://api.vk.com/method/"
TAGS = "#ПавелГнесюк #ТарскиеЛегенды #Хранители #книги #роман"

def vk(method, **params):
    params.update(access_token=VK_TOKEN, v="5.131")
    r = requests.post(VK_API + method, data=params, timeout=30).json()
    if "error" in r:
        raise RuntimeError(f"VK error: {r['error']}")
    return r["response"]

def gen_text(prompt):
    if GROQ_KEY:
        try:
            r = requests.post("https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {GROQ_KEY}"},
                json={"model": "llama-3.3-70b-versatile",
                      "messages": [{"role": "user", "content": prompt}]}, timeout=60).json()
            return r["choices"][0]["message"]["content"].strip()
        except Exception as e:
            print("Groq failed:", e)
    r = requests.post("https://openrouter.ai/api/v1/chat/completions",
        headers={"Authorization": f"Bearer {OPENROUTER_KEY}"},
        json={"model": "meta-llama/llama-3.1-8b-instruct:free",
              "messages": [{"role": "user", "content": prompt}]}, timeout=60).json()
    return r["choices"][0]["message"]["content"].strip()

def make_image(theme):
    prompt = ("Atmospheric cinematic book illustration, russian adventure thriller novel, "
              + theme + ", dramatic light, no text, no letters")
    url = "https://image.pollinations.ai/prompt/" + requests.utils.quote(prompt) + "?width=1200&height=800&nologo=true"
    r = requests.get(url, timeout=180)
    r.raise_for_status()
    open("img.jpg", "wb").write(r.content)
    return "img.jpg"

def upload_photo(path):
    server = vk("photos.getWallUploadServer", group_id=GROUP_ID)
    with open(path, "rb") as f:
        up = requests.post(server["upload_url"], files={"photo": f}, timeout=60).json()
    saved = vk("photos.saveWallPhoto", photo=up["photo"], server=up["server"],
               hash=up["hash"], group_id=GROUP_ID)
    return f"photo{saved[0]['owner_id']}_{saved[0]['id']}"

def build_post(book, mode, day):
    t, a, u = book["title"], book["about"], book["url"]
    if mode == "fragment" and book.get("fragments"):
        fr = book["fragments"][day % len(book["fragments"])]
        intro = gen_text(f"Напиши 1-2 предложения интригующего вступления для поста ВК "
                         f"о романе Павла Гнесюка «{t}». Без кавычек, без хештегов.")
        return f"{intro}\n\n«{fr}»\n\nЧитайте роман «{t}» на Литрес: {u}\n{TAGS}", a
    if mode == "question":
        txt = gen_text(f"Придумай для поста ВК интригующий вопрос читателям по теме романа "
                       f"Павла Гнесюка «{t}» ({a}). Вопрос + 2 предложения размышления. "
                       f"В конце призыв написать мнение в комментариях.")
        return f"{txt}\n\nРоман «{t}»: {u}\n{TAGS}", a
    txt = gen_text(f"Напиши увлекательный пост ВК (600-900 знаков) о романе Павла Гнесюка "
                   f"«{t}». Сюжет: {a}. Стиль интригующий, без спойлеров финала. "
                   f"Не используй кавычки-цитаты.")
    return f"{txt}\n\nЧитайте на Литрес: {u}\n{TAGS}", a

def main():
    books = json.load(open("books.json", encoding="utf-8"))["books"]
    day = datetime.date.today().toordinal()
    book = books[day % len(books)]
    mode = ["about", "fragment", "question"][day % 3]
    if mode == "fragment" and not book.get("fragments"):
        mode = "about"
    text, theme = build_post(book, mode, day)
    att = ""
    try:
        att = upload_photo(make_image(theme))
    except Exception as e:
        print("Image failed, posting without photo:", e)
    res = vk("wall.post", owner_id=f"-{GROUP_ID}", from_group=1,
             message=text, attachments=att)
    print(f"OK! Post id: {res['post_id']}, book: {book['title']}, mode: {mode}")

if __name__ == "__main__":
    main()
