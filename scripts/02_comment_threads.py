import json
import os
from datetime import datetime, timezone

import time
from pathlib import Path

from dotenv import load_dotenv
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Ubah sesuai kebutuhan / Buat None utk ngambil semua hal komen
MAX_PAGES = None

# Delay .
REQUEST_DELAY_SECONDS = 0.5

def main():
    load_dotenv(PROJECT_ROOT / ".env")

    api_key = os.getenv("YOUTUBE_API_KEY", "").strip()
    video_id = os.getenv("YOUTUBE_VIDEO_ID", "").strip()

    if not api_key or not video_id:
        print("Gagal: isi YOUTUBE_API_KEY dan YOUTUBE_VIDEO_ID dalam .env.")
        return 1

    # Setiap eksekusi memiliki folder tersendiri agar hasil sebelumnya terjaga.
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
    output_directory = (
        PROJECT_ROOT / "data" / "raw" / f"comments_{video_id}_{run_id}"
    )

    page_token = None
    page_number = 1
    total_comments = 0
    
    try:
        output_directory.mkdir(parents=True, exist_ok=True)

        youtube = build(
            "youtube",
            "v3",
            developerKey=api_key,
            cache_discovery=False,
        )

        while True:
            print(f"\nMengambil halaman {page_number}...")
            parameters = {
                "part": "snippet",
                "videoId": video_id,
                "maxResults": 100,
                "order": "time",
                "textFormat": "plainText",
            }

            if page_token:
                parameters["pageToken"] = page_token

            response = youtube.commentThreads().list(
                **parameters
                ).execute()

            threads = response.get("items", [])

            output = {
                "video_id": video_id,
                "collected_at": datetime.now(timezone.utc).isoformat(),
                "page_number": page_number,
                "request_parameters": parameters,
                "response": response,
            }

            output_path = (
                output_directory / f"page_{page_number:04d}.json"
            )

            with output_path.open("w", encoding="utf-8") as file:
                json.dump(output, file, ensure_ascii=False, indent=2)

            total_comments += len(threads)

            print(
                f"Halaman {page_number} tersimpan: "
                f"{len(threads)} komentar utama. "
                f"Total entri: {total_comments}."
            )

            next_page_token = response.get("nextPageToken")

            if not next_page_token:
                print("\nSelesai: API tidak memberikan halaman berikutnya.")
                break

            if MAX_PAGES is not None and page_number >= MAX_PAGES:
                print(f"\nBerhenti pada batas uji coba: {MAX_PAGES} halaman.")
                print("Masih ada halaman berikutnya yang belum diambil.")
                break

            # Token respons digunakan untuk permintaan berikutnya.
            page_token = next_page_token
            page_number += 1

            time.sleep(REQUEST_DELAY_SECONDS)

    except HttpError as error:
        print(f"\nPermintaan API gagal. Status HTTP: {error.resp.status}")
        print("Halaman yang sudah berhasil disimpan tetap tersedia.")
        print(f"Folder hasil: {output_directory}")
        return 1

    except OSError:
        print("\nTerjadi masalah koneksi atau penyimpanan.")
        print(f"Periksa hasil yang sudah tersimpan di: {output_directory}")
        return 1

    except KeyboardInterrupt:
        print("\nProses dihentikan oleh pengguna.")
        print(f"Periksa hasil yang sudah tersimpan di: {output_directory}")
        return 130

    print(f"\nJumlah halaman tersimpan: {page_number}")
    print(f"Jumlah entri komentar utama: {total_comments}")
    print(f"Folder hasil: {output_directory}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())