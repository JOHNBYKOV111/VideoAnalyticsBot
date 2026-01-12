# db/init_db.py
import asyncio
import asyncpg
import json
import os
from datetime import datetime

DB_URL = "postgresql://postgres:password@localhost:5432/video_stats"

async def run_init_sql():
    """Создает таблицы в базе данных"""
    init_sql_path = os.path.join(os.path.dirname(__file__), 'init.sql')
    
    with open(init_sql_path, "r", encoding="utf-8") as f:
        sql = f.read()

    conn = await asyncpg.connect(DB_URL)
    await conn.execute(sql)
    await conn.close()
    print("✅ Таблицы созданы/проверены")

async def import_data_directly():
    """Импортирует данные напрямую"""
    current_dir = os.path.dirname(__file__)  # папка db
    project_root = os.path.dirname(current_dir)  # корень проекта
    json_path = os.path.join(project_root, 'data', 'videos.json')
    
    print(f"🔍 Ищу файл по пути: {json_path}")
    
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"❌ Файл не найден: {json_path}")
        return
    except json.JSONDecodeError as e:
        print(f"❌ Ошибка чтения JSON: {e}")
        return
    
    videos = data.get("videos", [])
    
    if not videos:
        print("⚠️ В файле нет данных (пустой массив videos)")
        return
    
    conn = await asyncpg.connect(DB_URL)
    
    try:
        async with conn.transaction():
            videos_count = 0
            snapshots_count = 0
            
            print(f"📦 Найдено {len(videos)} видео для импорта...")
            
            # Функция для преобразования строки в datetime
            def parse_datetime(dt_str):
                """Преобразует строку в datetime, обрабатывая разные форматы"""
                if not dt_str:
                    return None
                
                # Убираем timezone если есть
                if dt_str.endswith('+00:00'):
                    dt_str = dt_str[:-6]
                
                try:
                    return datetime.fromisoformat(dt_str)
                except ValueError:
                    # Пробуем другие форматы
                    formats = [
                        '%Y-%m-%dT%H:%M:%S',
                        '%Y-%m-%d %H:%M:%S',
                        '%Y-%m-%d'
                    ]
                    
                    for fmt in formats:
                        try:
                            return datetime.strptime(dt_str, fmt)
                        except ValueError:
                            continue
                    
                    print(f"⚠️ Не удалось распарсить дату: {dt_str}")
                    return None
            
            # Импортируем видео
            for i, video in enumerate(videos, 1):
                # Проверяем обязательные поля
                required_fields = ['id', 'creator_id', 'video_created_at', 'views_count']
                missing_fields = [field for field in required_fields if field not in video]
                
                if missing_fields:
                    print(f"⚠️ Видео {i} пропущено, отсутствуют поля: {missing_fields}")
                    continue
                
                # Преобразуем даты
                video_created_at = parse_datetime(video["video_created_at"])
                created_at = parse_datetime(video.get("created_at"))
                updated_at = parse_datetime(video.get("updated_at"))
                
                if not video_created_at:
                    print(f"⚠️ Видео {video['id']} пропущено, некорректная дата создания")
                    continue
                
                await conn.execute('''
                    INSERT INTO videos 
                    (id, creator_id, video_created_at, views_count, likes_count, 
                     reports_count, comments_count, created_at, updated_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                    ON CONFLICT (id) DO UPDATE SET
                        views_count = EXCLUDED.views_count,
                        likes_count = EXCLUDED.likes_count,
                        reports_count = EXCLUDED.reports_count,
                        comments_count = EXCLUDED.comments_count,
                        updated_at = EXCLUDED.updated_at
                ''', 
                    video["id"],
                    video["creator_id"],
                    video_created_at,
                    video["views_count"],
                    video.get("likes_count", 0),
                    video.get("reports_count", 0),
                    video.get("comments_count", 0),
                    created_at,
                    updated_at
                )
                videos_count += 1
                
                # Импортируем snapshots
                for snapshot in video.get("snapshots", []):
                    if 'id' not in snapshot or 'video_id' not in snapshot:
                        continue
                    
                    # Преобразуем даты для snapshot
                    snap_created_at = parse_datetime(snapshot.get("created_at"))
                    snap_updated_at = parse_datetime(snapshot.get("updated_at"))
                    
                    await conn.execute('''
                        INSERT INTO video_snapshots
                        (id, video_id, views_count, likes_count, reports_count, comments_count,
                         delta_views_count, delta_likes_count, delta_reports_count, delta_comments_count,
                         created_at, updated_at)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                        ON CONFLICT (id) DO UPDATE SET
                            views_count = EXCLUDED.views_count,
                            likes_count = EXCLUDED.likes_count,
                            reports_count = EXCLUDED.reports_count,
                            comments_count = EXCLUDED.comments_count,
                            delta_views_count = EXCLUDED.delta_views_count,
                            delta_likes_count = EXCLUDED.delta_likes_count,
                            delta_reports_count = EXCLUDED.delta_reports_count,
                            delta_comments_count = EXCLUDED.delta_comments_count,
                            updated_at = EXCLUDED.updated_at
                    ''', 
                        snapshot["id"],
                        snapshot["video_id"],
                        snapshot.get("views_count", 0),
                        snapshot.get("likes_count", 0),
                        snapshot.get("reports_count", 0),
                        snapshot.get("comments_count", 0),
                        snapshot.get("delta_views_count", 0),
                        snapshot.get("delta_likes_count", 0),
                        snapshot.get("delta_reports_count", 0),
                        snapshot.get("delta_comments_count", 0),
                        snap_created_at,
                        snap_updated_at
                    )
                    snapshots_count += 1
                
                if i % 5 == 0:  # Прогресс каждые 5 видео
                    print(f"📊 Импортировано {i}/{len(videos)} видео...")
            
            print(f"\n✅ Успешно импортировано:")
            print(f"   📹 Видео: {videos_count}")
            print(f"   📋 Снапшотов: {snapshots_count}")
            
    except Exception as e:
        print(f"❌ Ошибка при импорте: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await conn.close()

async def main():
    await run_init_sql()
    await import_data_directly()

if __name__ == "__main__":
    asyncio.run(main())