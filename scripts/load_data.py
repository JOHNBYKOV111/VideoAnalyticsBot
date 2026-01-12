import asyncio
import json
from datetime import datetime
import asyncpg


DB_DSN = "postgresql://postgres:password@localhost:5432/video_stats"
JSON_PATH = "../data/videos.json"


# Поддерживаем два ISO-формата: с микросекундами и без
ISO_FORMATS = [
    "%Y-%m-%dT%H:%M:%S.%f%z",
    "%Y-%m-%dT%H:%M:%S%z",
]


def parse_dt(value: str | None):
    if value is None:
        return None
    for fmt in ISO_FORMATS:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    raise ValueError(f"Не удалось распарсить дату: {value}")


async def load_data():
    print("🔌 Подключаемся к БД...")
    conn = await asyncpg.connect(DB_DSN)

    print(f"📄 Читаем JSON: {JSON_PATH}")
    with open(JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
        videos_json = data["videos"]

    total_videos = len(videos_json)
    print(f"🎬 Всего видео в JSON: {total_videos}")

    # Обходим видео по порядку: 1, 2, 3 ...
    for idx, video_obj in enumerate(videos_json, start=1):
        if idx % 20 == 0 or idx == 1:
            print(f"▶️ Обработка видео {idx}/{total_videos}")

        human_number = idx  # Видео 1, Видео 2, ...

        video_id = video_obj["id"]
        creator_id = video_obj["creator_id"]

        # Преобразуем строки дат в datetime
        video_created_at = parse_dt(video_obj.get("video_created_at"))
        created_at = parse_dt(video_obj.get("created_at"))
        updated_at = parse_dt(video_obj.get("updated_at"))

        views = video_obj.get("views_count", 0)
        likes = video_obj.get("likes_count", 0)
        comments = video_obj.get("comments_count", 0)
        reports = video_obj.get("reports_count", 0)

        await conn.execute(
            """
            INSERT INTO videos (
                id,
                creator_id,
                video_created_at,
                views_count,
                likes_count,
                comments_count,
                reports_count,
                created_at,
                updated_at,
                human_number
            )
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
            ON CONFLICT (id) DO UPDATE SET
                creator_id       = EXCLUDED.creator_id,
                video_created_at = EXCLUDED.video_created_at,
                views_count      = EXCLUDED.views_count,
                likes_count      = EXCLUDED.likes_count,
                comments_count   = EXCLUDED.comments_count,
                reports_count    = EXCLUDED.reports_count,
                created_at       = EXCLUDED.created_at,
                updated_at       = EXCLUDED.updated_at,
                human_number     = EXCLUDED.human_number
            """,
            video_id,
            creator_id,
            video_created_at,
            views,
            likes,
            comments,
            reports,
            created_at,
            updated_at,
            human_number,
        )

        # Загружаем почасовые снапшоты для этого видео
        snapshots = video_obj.get("snapshots", [])
        for snap in snapshots:
            snapshot_id = snap["id"]
            snap_video_id = snap["video_id"]

            snap_views = snap.get("views_count", 0)
            snap_likes = snap.get("likes_count", 0)
            snap_comments = snap.get("comments_count", 0)
            snap_reports = snap.get("reports_count", 0)

            views_increment = snap.get("delta_views_count", 0)
            likes_increment = snap.get("delta_likes_count", 0)
            comments_increment = snap.get("delta_comments_count", 0)
            reports_increment = snap.get("delta_reports_count", 0)

            snap_created_at = parse_dt(snap.get("created_at"))
            snap_updated_at = parse_dt(snap.get("updated_at"))

            await conn.execute(
                """
                INSERT INTO video_snapshots (
                    id,
                    video_id,
                    views_count,
                    likes_count,
                    comments_count,
                    reports_count,
                    delta_views_count,
                    delta_likes_count,
                    delta_comments_count,
                    delta_reports_count,
                    created_at,
                    updated_at
                )
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
                ON CONFLICT (id) DO UPDATE SET
                    video_id             = EXCLUDED.video_id,
                    views_count          = EXCLUDED.views_count,
                    likes_count          = EXCLUDED.likes_count,
                    comments_count       = EXCLUDED.comments_count,
                    reports_count        = EXCLUDED.reports_count,
                    delta_views_count    = EXCLUDED.delta_views_count,
                    delta_likes_count    = EXCLUDED.delta_likes_count,
                    delta_comments_count = EXCLUDED.delta_comments_count,
                    delta_reports_count  = EXCLUDED.delta_reports_count,
                    created_at           = EXCLUDED.created_at,
                    updated_at           = EXCLUDED.updated_at
                """,
                snapshot_id,
                snap_video_id,
                snap_views,
                snap_likes,
                snap_comments,
                snap_reports,
                views_increment,
                likes_increment,
                comments_increment,
                reports_increment,
                snap_created_at,
                snap_updated_at,
            )

    # Нумерация креаторов
    print("🔄 Нумерация креаторов...")

    await conn.execute(
        """
        ALTER TABLE videos 
        ADD COLUMN IF NOT EXISTS creator_human_number INTEGER
        """
    )

    creators = await conn.fetch(
        "SELECT DISTINCT creator_id FROM videos ORDER BY creator_id"
    )

    for idx, creator in enumerate(creators, start=1):
        await conn.execute(
            """
            UPDATE videos 
            SET creator_human_number = $1 
            WHERE creator_id = $2
            """,
            idx,
            creator["creator_id"],
        )

    creator_count = len(creators)
    print(f"✅ Креаторы пронумерованы 1-{creator_count}")

    await conn.close()
    print("✅ Данные загружены, human_number и creator_human_number присвоены!")


if __name__ == "__main__":
    asyncio.run(load_data())
