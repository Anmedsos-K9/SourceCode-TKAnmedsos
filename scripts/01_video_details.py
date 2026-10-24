import json
import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


# Folder utama repository, satu tingkat di atas folder scripts/.
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def main():
    # Membaca konfigurasi dari file .env di folder utama.
    load_dotenv(PROJECT_ROOT / ".env")

    api_key = os.getenv("YOUTUBE_API_KEY", "").strip()
    video_id = os.getenv("YOUTUBE_VIDEO_ID", "").strip()

    if not api_key:
        print("Gagal: YOUTUBE_API_KEY belum diisi dalam .env.")
        return 1

    if not video_id:
        print("Gagal: YOUTUBE_VIDEO_ID belum diisi dalam .env.")
        return 1

    try:
        youtube = build(
            "youtube",
            "v3",
            developerKey=api_key,
            cache_discovery=False,
        )

        # Mengambil metadata dan statistik video.
        response = youtube.videos().list(
            part="snippet,statistics",
            id=video_id,
        ).execute()

    except HttpError as error:
        # Tidak mencetak URL permintaan karena dapat memuat API key.
        print(f"Permintaan API gagal. Status HTTP: {error.resp.status}")
        print(
            "Periksa API key, aktivasi YouTube Data API v3, "
            "pembatasan key, dan kuota project."
        )
        return 1

    except OSError:
        print("Koneksi gagal. Periksa jaringan internet, lalu coba kembali.")
        return 1

    videos = response.get("items", [])

    if not videos:
        print("Video tidak ditemukan atau tidak dapat diakses.")
        print("Periksa kembali YOUTUBE_VIDEO_ID.")
        return 1

    video = videos[0]
    snippet = video.get("snippet", {})
    statistics = video.get("statistics", {})

    # Mencatat kapan data diperoleh.
    collected_at = datetime.now(timezone.utc).isoformat()

    output = {
        "collected_at": collected_at,
        "video": video,
    }

    output_directory = PROJECT_ROOT / "data" / "raw"
    output_path = output_directory / f"video_{video['id']}.json"

    try:
        output_directory.mkdir(parents=True, exist_ok=True)

        with output_path.open("w", encoding="utf-8") as file:
            json.dump(output, file, ensure_ascii=False, indent=2)

    except OSError:
        print("Data berhasil diambil, tetapi gagal disimpan.")
        print("Periksa izin akses dan ruang penyimpanan folder data/raw.")
        return 1

    print("Metadata video berhasil diambil.")
    print(f"ID video       : {video['id']}")
    print(f"Judul          : {snippet.get('title', 'Tidak tersedia')}")
    print(f"Channel        : {snippet.get('channelTitle', 'Tidak tersedia')}")
    print(f"Tanggal unggah : {snippet.get('publishedAt', 'Tidak tersedia')}")
    print(f"Jumlah tayangan: {statistics.get('viewCount', 'Tidak tersedia')}")
    print(f"Jumlah suka    : {statistics.get('likeCount', 'Tidak tersedia')}")
    print(f"Jumlah komentar: {statistics.get('commentCount', 'Tidak tersedia')}")
    print(f"Diambil pada   : {collected_at}")
    print(f"Disimpan ke    : {output_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())