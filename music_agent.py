#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Музыкальный агент для автоматической публикации альбомов в ВКонтакте
Автор: Павел Гнесюк
Версия: 2.0
"""

import json
import time
import logging
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import requests

# ============================================================
# КОНФИГУРАЦИЯ
# ============================================================

CONFIG = {
    # Токен доступа ВКонтакте
    "vk_access_token": "ВАШ_ТОКЕН_ВК",
    
    # Идентификатор группы или страницы для публикации
    "owner_id": -2001000000,
    
    # Файл с данными о музыке
    "data_file": "music.json",
    
    # Настройки публикации
    "publish_interval_hours": 24,
    "max_albums_per_day": 1,
    
    # Шаблон поста
    "post_template": """🎵 {artist} представляет {release_type} «{album_title}»!

🎼 Жанр: {genre}
📀 Треков: {track_count}

{track_list}

🎧 Слушайте прямо сейчас!

#музыка #альбом #новинка #{artist_tag}""",
    
    # Логирование
    "log_file": "music_agent.log",
    "log_level": "INFO",
    
    # Файл для отслеживания опубликованных альбомов
    "published_file": "published_albums.json"
}

# ============================================================
# ЛОГИРОВАНИЕ
# ============================================================

logging.basicConfig(
    level=getattr(logging, CONFIG["log_level"]),
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(CONFIG["log_file"], encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ============================================================
# КЛАСС АГЕНТА
# ============================================================

class MusicAgent:
    """Агент для автоматической публикации музыки в ВКонтакте"""
    
    def __init__(self, config: Dict):
        self.config = config
        self.access_token = config["vk_access_token"]
        self.owner_id = config["owner_id"]
        self.api_version = "5.131"
        self.base_url = "https://api.vk.com/method"
        
        self.data = self._load_data()
        self.published = self._load_published()
        
        logger.info("🚀 Музыкальный агент инициализирован")
        logger.info(f"📊 Альбомов: {len(self.data.get('albums', []))}")
        logger.info(f"📊 EP: {len(self.data.get('eps', []))}")
        logger.info(f"📊 Синглов: {len(self.data.get('singles', []))}")
    
    # ========================================================
    # РАБОТА С ФАЙЛАМИ
    # ========================================================
    
    def _load_data(self) -> Dict:
        """Загрузка данных о музыке"""
        try:
            with open(self.config["data_file"], "r", encoding="utf-8") as f:
                data = json.load(f)
            logger.info(f"✅ Данные загружены из {self.config['data_file']}")
            return data
        except FileNotFoundError:
            logger.error(f"❌ Файл {self.config['data_file']} не найден!")
            return {"albums": [], "eps": [], "singles": []}
        except json.JSONDecodeError as e:
            logger.error(f"❌ Ошибка JSON: {e}")
            return {"albums": [], "eps": [], "singles": []}
    
    def _load_published(self) -> Dict:
        """Загрузка опубликованных альбомов"""
        try:
            if os.path.exists(self.config["published_file"]):
                with open(self.config["published_file"], "r", encoding="utf-8") as f:
                    return json.load(f)
            return {"published_albums": [], "last_publish_time": None}
        except Exception as e:
            logger.error(f"❌ Ошибка: {e}")
            return {"published_albums": [], "last_publish_time": None}
    
    def _save_published(self):
        """Сохранение опубликованных альбомов"""
        try:
            with open(self.config["published_file"], "w", encoding="utf-8") as f:
                json.dump(self.published, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения: {e}")
    
    # ========================================================
    # VK API
    # ========================================================
    
    def _make_request(self, method: str, params: Dict) -> Dict:
        """Запрос к VK API"""
        url = f"{self.base_url}/{method}"
        params["access_token"] = self.access_token
        params["v"] = self.api_version
        
        try:
            response = requests.post(url, data=params)
            response.raise_for_status()
            result = response.json()
            
            if "error" in result:
                logger.error(f"❌ VK API: {result['error']}")
                return {"success": False, "error": result["error"]}
            
            return {"success": True, "response": result.get("response")}
        except requests.RequestException as e:
            logger.error(f"❌ Ошибка запроса: {e}")
            return {"success": False, "error": str(e)}
    
    def _format_track_list(self, tracks: List[Dict]) -> str:
        """Форматирование списка треков"""
        return "\n".join(f"{i}. {t['title']}" for i, t in enumerate(tracks, 1))
    
    def _format_audio_attachments(self, tracks: List[Dict]) -> str:
        """Форматирование аудио-вложений"""
        return ",".join(t["audio_id"] for t in tracks if t.get("audio_id"))
    
    def _create_post_text(self, release: Dict) -> str:
        """Создание текста поста"""
        artist = self.data.get("metadata", {}).get("artist", "Павел Гнесюк")
        
        type_names = {"album": "альбом", "ep": "EP", "single": "сингл"}
        release_type = type_names.get(release.get("type", "album"), "релиз")
        
        tracks = release.get("tracks", [])
        artist_tag = artist.replace(" ", "").lower()
        
        return self.config["post_template"].format(
            artist=artist,
            release_type=release_type,
            album_title=release.get("title", "Без названия"),
            genre=release.get("genre", "разные жанры"),
            track_count=len(tracks),
            track_list=self._format_track_list(tracks),
            artist_tag=artist_tag
        )
    
    def publish_release(self, release: Dict) -> bool:
        """Публикация релиза"""
        title = release.get("title", "Без названия")
        logger.info(f"📤 Публикация: {title}")
        
        try:
            post_text = self._create_post_text(release)
            tracks = release.get("tracks", [])
            audio_attachments = self._format_audio_attachments(tracks)
            
            params = {
                "owner_id": self.owner_id,
                "message": post_text,
                "attachments": audio_attachments,
                "from_group": 1 if self.owner_id < 0 else 0
            }
            
            result = self._make_request("wall.post", params)
            
            if result["success"]:
                post_id = result["response"].get("post_id")
                logger.info(f"✅ «{title}» опубликован! Пост: {post_id}")
                
                self.published["published_albums"].append({
                    "title": title,
                    "type": release.get("type"),
                    "post_id": post_id,
                    "publish_time": datetime.now().isoformat()
                })
                self.published["last_publish_time"] = datetime.now().isoformat()
                self._save_published()
                return True
            
            logger.error(f"❌ Не удалось опубликовать «{title}»")
            return False
        
        except Exception as e:
            logger.error(f"❌ Ошибка: {e}")
            return False
    
    # ========================================================
    # ОСНОВНАЯ ЛОГИКА
    # ========================================================
    
    def get_unpublished(self) -> List[Dict]:
        """Неопубликованные релизы"""
        published_titles = {p["title"] for p in self.published["published_albums"]}
        unpublished = []
        
        for key, rtype in [("albums", "album"), ("eps", "ep"), ("singles", "single")]:
            for item in self.data.get(key, []):
                if item["title"] not in published_titles:
                    item["type"] = rtype
                    unpublished.append(item)
        
        return unpublished
    
    def can_publish_now(self) -> bool:
        """Проверка интервала"""
        if not self.published["last_publish_time"]:
            return True
        last = datetime.fromisoformat(self.published["last_publish_time"])
        return datetime.now() - last >= timedelta(hours=self.config["publish_interval_hours"])
    
    def run_once(self) -> Dict:
        """Однократный запуск"""
        logger.info("=" * 50)
        logger.info("🎵 Запуск агента")
        
        if not self.can_publish_now():
            logger.info("⏳ Слишком рано. Пропуск.")
            return {"success": False, "reason": "interval"}
        
        unpublished = self.get_unpublished()
        if not unpublished:
            logger.info("🎉 Всё опубликовано!")
            return {"success": False, "reason": "all_published"}
        
        release = unpublished[0]
        if self.publish_release(release):
            return {"success": True, "published": release["title"]}
        return {"success": False, "reason": "failed"}
    
    def run_continuous(self):
        """Непрерывный режим"""
        logger.info("🔄 Непрерывный режим")
        while True:
            try:
                self.run_once()
                time.sleep(3600)
            except KeyboardInterrupt:
                logger.info("👋 Остановлено")
                break
    
    def get_stats(self) -> Dict:
        """Статистика"""
        total = sum(len(self.data.get(k, [])) for k in ["albums", "eps", "singles"])
        published = len(self.published["published_albums"])
        return {
            "total": total,
            "published": published,
            "remaining": total - published,
            "percent": round(published / total * 100, 1) if total else 0
        }
    
    def print_stats(self):
        """Вывод статистики"""
        s = self.get_stats()
        print(f"\n📊 Всего: {s['total']} | Опубликовано: {s['published']} | Осталось: {s['remaining']} | Прогресс: {s['percent']}%\n")

# ============================================================
# ТОЧКА ВХОДА
# ============================================================

def main():
    print("\n🎵 МУЗЫКАЛЬНЫЙ АГЕНТ ВКОНТАКТЕ 🎵\n")
    
    agent = MusicAgent(CONFIG)
    agent.print_stats()
    
    print("1. Опубликовать один релиз")
    print("2. Непрерывный режим")
    print("3. Статистика")
    
    choice = input("Выбор (1-3): ").strip()
    
    if choice == "1":
        result = agent.run_once()
        print(f"\n{'✅ ' + result['published'] if result['success'] else 'ℹ️ Пропущено'}")
    elif choice == "2":
        agent.run_continuous()
    elif choice == "3":
        agent.print_stats()

if __name__ == "__main__":
    main()
