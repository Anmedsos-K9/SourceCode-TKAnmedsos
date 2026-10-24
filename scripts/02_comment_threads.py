import json
import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def main():
    load_dotenv(PROJECT_ROOT / ".env")

    api_key = os.getenv("YOUTUBE_API_KEY", "").strip()
    video_id = os.getenv("YOUTUBE_VIDEO_ID", "").strip()

    if not api_key or not video_id:
        print("Gagal: isi YOUTUBE_API_KEY dan YOUTUBE_VIDEO_ID dalam .env.")
        return 1

    try:
        youtube = build(
            "youtube",
            "v3",
            developerKey=api_key,
            cache_discovery=False,
        )

        response = youtube.commentThreads().list(
            part="snippet",
            videoId=video_id,
            maxResults=100,
            order="time",
            textFormat="plainText",
        ).execute()

    except HttpError as error:
        # Hindari mencetak URL permintaan yang dapat memuat API key.
        print(f"Permintaan API gagal. Status HTTP: {error.resp.status}")
        print(
            "Periksa konfigurasi API, kuota, akses video, "
            "dan apakah komentar video diaktifkan."
        )
        return 1

    except OSError:
        print("Koneksi gagal. Periksa jaringan internet.")
        return 1

    threads = response.get("items", [])
    collected_at = datetime.now(timezone.utc).isoformat()

    # Menyimpan respons API, termasuk token halaman berikutnya jika tersedia.
    output = {
        "video_id": video_id,
        "collected_at": collected_at,
        "request_parameters": {
            "part": "snippet",
            "maxResults": 100,
            "order": "time",
            "textFormat": "plainText",
        },
        "response": response,
    }

    output_directory = PROJECT_ROOT / "data" / "raw"
    output_path = (
        output_directory / f"comment_threads_{video_id}_page_001.json"
    )

    try:
        output_directory.mkdir(parents=True, exist_ok=True)

        with output_path.open("w", encoding="utf-8") as file:
            json.dump(output, file, ensure_ascii=False, indent=2)

    except OSError:
        print("Data berhasil diambil, tetapi gagal disimpan.")
        print("Periksa izin akses dan ruang penyimpanan.")
        return 1

    print(f"Komentar utama diperoleh: {len(threads)}")
    print(f"Disimpan ke: {output_path}")

    # Menampilkan maksimal tiga contoh untuk memeriksa hasil.
    for number, thread in enumerate(threads[:3], start=1):
        thread_snippet = thread["snippet"]
        comment = thread_snippet["topLevelComment"]
        snippet = comment["snippet"]

        text = snippet.get("textDisplay", "")
        preview = " ".join(text.split())
        if len(preview) > 250:
            preview = preview[:250] + "..."

        print(f"\nContoh {number}")
        print(f"ID komentar   : {comment['id']}")
        print(f"Dipublikasikan: {snippet.get('publishedAt')}")
        print(f"Jumlah suka   : {snippet.get('likeCount', 0)}")
        print(f"Jumlah balasan: {thread_snippet.get('totalReplyCount', 0)}")
        print(f"Teks          : {preview}")

    if response.get("nextPageToken"):
        print("\nHalaman berikutnya tersedia, tetapi belum diambil.")
    else:
        print("\nAPI tidak memberikan halaman berikutnya.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())