import json
import os
from datetime import datetime, timezone
import time
from pathlib import Path

from dotenv import load_dotenv
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from httplib2 import HttpLib2Error

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Ubah sesuai kebutuhan / Buat None utk ngambil semua hal komen
MAX_PAGES = None
RESUME = True  # False untuk memulai pengambilan baru.
REQUEST_DELAY_SECONDS = 0.5 # Delay
MAX_RETRIES = 3

def utc_now():
    return datetime.now(timezone.utc).isoformat()

def save_json(path, data):
    """Tulis file sementara, lalu ganti file tujuan setelah penulisan selesai."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")

    with temporary_path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)

    temporary_path.replace(path)


def prepare_state(video_id, checkpoint_path):
    """Baca progres sebelumnya atau buat sesi pengambilan baru."""
    if RESUME and checkpoint_path.exists():
        with checkpoint_path.open("r", encoding="utf-8") as file:
            state = json.load(file)

        if state["video_id"] != video_id:
            raise ValueError("ID video pada checkpoint tidak sesuai.")

        return state

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")

    state = {
        "video_id": video_id,
        "output_directory": f"data/raw/comments_{video_id}_{run_id}",
        "next_page": 1,
        "next_page_token": None,
        "total_entries": 0,
        "completed": False,
        "updated_at": utc_now(),
    }

    save_json(checkpoint_path, state)
    return state


def main():
    load_dotenv(PROJECT_ROOT / ".env")

    api_key = os.getenv("YOUTUBE_API_KEY", "").strip()
    video_id = os.getenv("YOUTUBE_VIDEO_ID", "").strip()

    if not api_key or not video_id:
        print("Gagal: isi YOUTUBE_API_KEY dan YOUTUBE_VIDEO_ID dalam .env.")
        return 1

    checkpoint_path = (
        PROJECT_ROOT / "checkpoints" / f"comments_{video_id}.json"
    )
    
    try:
        state = prepare_state(video_id, checkpoint_path)

        if state["completed"]:
            print("Pengambilan pada checkpoint ini sudah selesai.")
            print("Untuk sesi baru, ubah RESUME menjadi False.")
            return 0

        output_directory = PROJECT_ROOT / state["output_directory"]

        print(f"Mulai dari halaman: {state['next_page']}")
        print(f"Entri sebelumnya  : {state['total_entries']}")
        print(f"Folder hasil      : {output_directory}")

        youtube = build(
            "youtube",
            "v3",
            developerKey=api_key,
            cache_discovery=False,
        )

        pages_this_run = 0

        while MAX_PAGES is None or pages_this_run < MAX_PAGES:
            page_number = state["next_page"]

            parameters = {
                "part": "snippet",
                "videoId": video_id,
                "maxResults": 100,
                "order": "time",
                "textFormat": "plainText",
            }

            if state["next_page_token"]:
                parameters["pageToken"] = state["next_page_token"]

            print(f"\nMengambil halaman {page_number}...")

            response = youtube.commentThreads().list(
                **parameters
            ).execute(num_retries=MAX_RETRIES)

            items = response.get("items", [])

            output = {
                "video_id": video_id,
                "collected_at": utc_now(),
                "page_number": page_number,
                "request_parameters": parameters,
                "response": response,
            }

            # Simpan data terlebih dahulu, baru majukan checkpoint.
            output_path = output_directory / f"page_{page_number:04d}.json"
            save_json(output_path, output)

            state["next_page"] = page_number + 1
            state["next_page_token"] = response.get("nextPageToken")
            state["total_entries"] += len(items)
            state["completed"] = not bool(state["next_page_token"])
            state["updated_at"] = utc_now()

            save_json(checkpoint_path, state)
            pages_this_run += 1

            print(f"Tersimpan: {len(items)} komentar utama.")
            print(f"Total entri sesi ini: {state['total_entries']}")

            if state["completed"]:
                print("\nSelesai: tidak ada halaman berikutnya.")
                break

            if MAX_PAGES is None or pages_this_run < MAX_PAGES:
                time.sleep(REQUEST_DELAY_SECONDS)

        if not state["completed"]:
            print("\nBatas halaman per eksekusi tercapai.")
            print("Jalankan kembali dengan RESUME = True untuk melanjutkan.")

        print(f"Checkpoint: {checkpoint_path}")
        return 0

    except HttpError as error:
        print(f"\nPermintaan API gagal. Status HTTP: {error.resp.status}")
        print("Periksa kuota, konfigurasi API, dan akses komentar.")
        print("Progres yang sudah disimpan dapat digunakan kembali.")
        return 1

    except HttpLib2Error:
        print("\nGangguan transport jaringan. Jalankan kembali untuk melanjutkan.")
        return 1

    except OSError:
        print("\nTerjadi masalah jaringan atau akses penyimpanan.")
        print("Periksa koneksi, izin folder, dan ruang penyimpanan.")
        return 1

    except (ValueError, KeyError, TypeError):
        print("\nCheckpoint tidak valid atau strukturnya tidak sesuai.")
        print("Periksa file checkpoint sebelum melanjutkan.")
        return 1

    except KeyboardInterrupt:
        print("\nProses dihentikan. Progres terakhir yang tersimpan tetap tersedia.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())