# -*- coding: utf-8 -*-
"""
Одноразовый скрипт для создания music.json из VK Music
Запустите один раз, потом отредактируйте описания песен вручную
"""
import os, re, json, hashlib, requests
from bs4 import BeautifulSoup

ARTIST_URL = "https://vk.ru/artist/pavelgnesyuk"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

def parse_vk_music():
    """Парсит VK Music и создаёт структуру для music.json"""
    print("🔍 Парсинг страницы артиста VK...")
    
    try:
        resp = requests.get(ARTIST_URL, headers=UA, timeout=30)
        soup = BeautifulSoup(resp.text, "html.parser")
        
        audios = []
        albums = {}
        
        for script in soup.find_all("script"):
            text = script.string or ""
            if "audios" in text.lower() or "AudioArtist" in text:
                # Ищем массив треков
                match_a = re.search(r'"audios":\s*(\[[^\]]+\])', text, re.DOTALL)
                if match_a:
                    try: audios = json.loads(match_a.group(1))
                    except: pass
                
                # Ищем словарь альбомов
                match_b = re.search(r'"albums":\s*(\{.*?\})\s*[,}]', text, re.DOTALL)
                if match_b:
                    try: albums = json.loads(match_b.group(1))
                    except: pass
        
        if not audios:
            print("❌ Не найдены данные audios в HTML")
            return None
        
        # Группируем треки по альбомам
        result = {"albums": []}
        album_tracks = {}
        
        for track in audios:
            aid = str(track.get("album_id", ""))
            if aid and aid != "0":
                if aid not in album_tracks:
                    alb_data = albums.get(aid, {})
                    album_tracks[aid] = {
                        "id": aid,
                        "title": alb_data.get("title", "Сингл"),
                        "url": ARTIST_URL,
                        "cover": alb_data.get("cover", ""),
                        "songs": []
                    }
                album_tracks[aid]["songs"].append({
                    "title": track.get("title", "Без названия"),
                    "about": ""  # ЗАПОЛНИТЕ ВРУЧНУЮ!
                })
        
        result["albums"] = list(album_tracks.values())
        
        print(f"✅ Найдено: {len(result['albums'])} альбомов, {len(audios)} треков")
        return result
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return None

def main():
    data = parse_vk_music()
    if not data:
        return
    
    # Сохраняем в music.json
    with open("music.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print("\n✅ Создан файл music.json!")
    print("📝 Теперь откройте его и заполните поле 'about' для каждой песни")
    print("   (краткое описание: о чём песня, настроение, смысл)")

if __name__ == "__main__":
    main()
