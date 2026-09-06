# -*- coding: utf-8 -*-
"""
Сбор audio_id всех треков из VK Music
Запускается один раз через Actions (workflow_dispatch)
Результат: файл audio_ids.json
"""
import os, json, requests, time

VK_TOKEN = os.getenv("VK_USER_TOKEN") or os.getenv("VK_TOKEN", "")
VK_GROUP_ID = os.getenv("VK_GROUP_ID", "").strip().lstrip("-")

ALBUM_URLS = [
    ("Оставим грусть. С Новым Годом!", "-2000882358_26882358"),
    ("Горячий песок Египта", "-2000087584_26087584"),
    ("Дар богов", "-2000276266_26276266"),
    ("Imperium", "-2000903105_26903105"),
    ("Энергия для души", "-2000921965_26921965"),
    ("Бездна", "-2000905527_26905527"),
    ("Тишина вместо слов", "-2000915616_26915616"),
    ("Управление чувствами", "-2000687207_26687207"),
    ("Небесный страж", "-2000688683_26688683"),
    ("Пленники Хроноса", "-2000688667_26688667"),
    ("Поколение ветра", "-2000812994_26812994"),
    ("Туманные зеркала", "-2000822740_26822740"),
    ("Раскаленный мир", "-2000866265_26866265"),
    ("Обжигающий", "-2000889455_26889455"),
    ("Лекарство от печали", "-2000896190_26896190"),
    ("Пока ты ждёшь", "-2000019250_27019250"),
    ("Весенние чувства", "-2000142707_27142707"),
    ("Тени Великой Тартарии", "-2000592309_27592309"),
    ("Spirit", "-2000673297_27673297"),
    ("Enjoyments", "-2000459373_28459373"),
    ("Турецкие мотивы", "-2000457759_28457759"),
    ("Прикосновения", "-2000457449_28457449"),
    ("Истоки славы", "-2000517591_28517591"),
    ("Цена тишины", "-2000694677_28694677"),
    ("Под одним небом", "-2000817997_28817997"),
    ("Дух свободы", "-2000819321_28819321"),
    ("Gloria Romae", "-2000908768_28908768"),
    ("Gloria Romae II", "-2000910959_28910959"),
    ("Сибирский ветер", "-2000007672_29007672"),
    ("Чувственный горизонт", "-2000295679_27295679"),
    ("Твой свет", "-2000258699_27258699"),
    ("Дух возвращается", "-2000688528_28688528"),
    ("Энергия существует", "-2000690046_28690046"),
    ("Тёплый свет", "-2000021745_27021745"),
    ("Россия матушка зовет (folk garmonica)", "-2000267152_26267152"),
    ("Шторм и штиль", "-2000266456_26266456"),
]

def vk_call(method, params):
    p = dict(params)
    p["access_token"] = VK_TOKEN
    p["v"] = "5.131"
    try:
        r = requests.post(f"https://api.vk.com/method/{method}", data=p, timeout=30).json()
        if "error" in r:
            print(f"⚠️ {method}: {r.get('error')}")
            return None
        return r.get("response", {}).get("items", [])
    except Exception as e:
        print(f"⚠️ {method}: {e}")
        return []

def main():
    if not VK_TOKEN:
        print("❌ Нет VK_TOKEN")
        return
    
    result = {}
    for album_title, album_id in ALBUM_URLS:
        print(f"\n🎵 {album_title} ({album_id})")
        # Извлекаем owner_id альбома
        owner, aid = album_id.split("_")
        owner = owner.lstrip("-")
        
        # Получаем треки альбома
        items = vk_call("audio.get", {
            "owner_id": f"-{owner}",
            "album_id": aid,
            "count": 1000
        })
        
        tracks = {}
        for item in items:
            title = item.get("title", "")
            aid_full = f"{item.get('owner_id')}_{item.get('id')}"
            tracks[title] = aid_full
            print(f"  ✅ {title} → {aid_full}")
        
        result[album_title] = tracks
        time.sleep(0.4)  # anti-flood
    
    with open("audio_ids.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ Сохранено: audio_ids.json ({len(result)} альбомов)")

if __name__ == "__main__":
    main()
