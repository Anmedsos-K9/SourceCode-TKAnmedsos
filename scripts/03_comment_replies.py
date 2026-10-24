import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from httplib2 import HttpLib2Error


PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Batas total halaman balasan tambahan per eksekusi.
MAX_PAGES = None  # Ubah menjadi None untuk tanpa batas.
RESUME = True # False untuk memulai pengambilan baru.
MAX_RETRIES = 3
REQUEST_DELAY_SECONDS = 0.5


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def read_json(path):
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")

    with temporary_path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)

    temporary_path.replace(path)


def find_parents(source_directory):
    """Ambil ID komentar utama yang memiliki balasan pada snapshot sumber."""
    parents = {}

    for path in sorted(source_directory.glob("page_*.json")):
        page = read_json(path)

        for thread in page["response"].get("items", []):
            snippet = thread["snippet"]

            if snippet.get("totalReplyCount", 0) > 0:
                comment = snippet["topLevelComment"]

                # Gunakan ID komentar utama, bukan ID thread.
                parents[comment["id"]] = {
                    "parent_id": comment["id"],
                    "reported_reply_count": snippet["totalReplyCount"],
                }

    return list(parents.values())


def main():
    load_dotenv(PROJECT_ROOT / ".env")

    api_key = os.getenv("YOUTUBE_API_KEY", "").strip()
    video_id = os.getenv("YOUTUBE_VIDEO_ID", "").strip()

    if not api_key or not video_id:
        print("Gagal: isi YOUTUBE_API_KEY dan YOUTUBE_VIDEO_ID dalam .env.")
        return 1

    comments_checkpoint = (
        PROJECT_ROOT / "checkpoints" / f"comments_{video_id}.json"
    )
    replies_checkpoint = (
        PROJECT_ROOT / "checkpoints" / f"replies_{video_id}.json"
    )

    try:
        if not comments_checkpoint.exists():
            print("Checkpoint komentar utama belum tersedia.")
            return 1

        source_state = read_json(comments_checkpoint)

        if not source_state["completed"]:
            print("Selesaikan pengambilan komentar utama terlebih dahulu.")
            return 1

        source_relative = source_state["output_directory"]
        source_directory = PROJECT_ROOT / source_relative

        if not source_directory.is_dir():
            print("Folder hasil komentar utama tidak ditemukan.")
            return 1

        if RESUME and replies_checkpoint.exists():
            state = read_json(replies_checkpoint)

            if (
                state["video_id"] != video_id
                or state["source_directory"] != source_relative
            ):
                print("Checkpoint balasan berasal dari sesi sumber berbeda.")
                print("Gunakan RESUME = False untuk memulai sesi balasan baru.")
                return 1

        else:
            parents = find_parents(source_directory)
            run_id = datetime.now(timezone.utc).strftime(
                "%Y%m%dT%H%M%S_%fZ"
            )

            # Daftar induk disimpan agar urutannya tetap saat melanjutkan.
            state = {
                "video_id": video_id,
                "source_directory": source_relative,
                "output_directory": (
                    f"data/raw/replies_{video_id}_{run_id}"
                ),
                "parents": parents,
                "parent_index": 0,
                "next_page": 1,
                "next_page_token": None,
                "total_entries": 0,
                "completed": len(parents) == 0,
                "updated_at": utc_now(),
            }

            save_json(replies_checkpoint, state)

        if state["completed"]:
            print("Pengambilan balasan pada sesi ini sudah selesai.")
            print(f"Total entri balasan: {state['total_entries']}")
            return 0

        output_directory = PROJECT_ROOT / state["output_directory"]
        parents = state["parents"]

        print(f"Komentar induk dengan balasan: {len(parents)}")
        print(f"Mulai dari induk ke: {state['parent_index'] + 1}")
        print(f"Folder hasil: {output_directory}")

        youtube = build(
            "youtube",
            "v3",
            developerKey=api_key,
            cache_discovery=False,
        )

        pages_this_run = 0

        while MAX_PAGES is None or pages_this_run < MAX_PAGES:
            parent_index = state["parent_index"]
            parent = parents[parent_index]
            page_number = state["next_page"]

            parameters = {
                "part": "snippet",
                "parentId": parent["parent_id"],
                "maxResults": 100,
                "textFormat": "plainText",
            }

            if state["next_page_token"]:
                parameters["pageToken"] = state["next_page_token"]

            print(
                f"\nInduk {parent_index + 1}/{len(parents)}, "
                f"halaman balasan {page_number}..."
            )

            response = youtube.comments().list(
                **parameters
            ).execute(num_retries=MAX_RETRIES)

            items = response.get("items", [])

            output = {
                "video_id": video_id,
                "parent_id": parent["parent_id"],
                "collected_at": utc_now(),
                "page_number": page_number,
                "request_parameters": parameters,
                "response": response,
            }

            output_path = (
                output_directory
                / f"parent_{parent_index + 1:05d}"
                / f"page_{page_number:04d}.json"
            )

            save_json(output_path, output)

            next_token = response.get("nextPageToken")
            state["total_entries"] += len(items)

            if next_token:
                # Masih ada halaman balasan untuk induk yang sama.
                state["next_page_token"] = next_token
                state["next_page"] = page_number + 1
            else:
                # Balasan induk ini selesai; pindah ke induk berikutnya.
                state["parent_index"] = parent_index + 1
                state["next_page_token"] = None
                state["next_page"] = 1

            state["completed"] = state["parent_index"] >= len(parents)
            state["updated_at"] = utc_now()

            save_json(replies_checkpoint, state)
            pages_this_run += 1

            print(f"Tersimpan: {len(items)} balasan.")
            print(f"Total entri balasan: {state['total_entries']}")

            if state["completed"]:
                print("\nSelesai: semua induk dalam daftar sudah diproses.")
                break

            if MAX_PAGES is None or pages_this_run < MAX_PAGES:
                time.sleep(REQUEST_DELAY_SECONDS)

        if not state["completed"]:
            print("\nBatas halaman per eksekusi tercapai.")
            print("Jalankan kembali dengan RESUME = True untuk melanjutkan.")

        print(f"Checkpoint: {replies_checkpoint}")
        return 0

    except HttpError as error:
        print(f"\nPermintaan API gagal. Status HTTP: {error.resp.status}")
        print("Periksa kuota dan ketersediaan komentar induk.")
        print("Checkpoint terakhir tetap tersedia.")
        return 1

    except HttpLib2Error:
        print("\nGangguan transport jaringan. Coba jalankan kembali.")
        return 1

    except OSError:
        print("\nTerjadi masalah jaringan atau akses file.")
        return 1

    except (ValueError, KeyError, TypeError, IndexError):
        print("\nStruktur data sumber atau checkpoint tidak sesuai.")
        print("Periksa file terkait sebelum melanjutkan.")
        return 1

    except KeyboardInterrupt:
        print("\nProses dihentikan. Checkpoint terakhir tetap tersedia.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())