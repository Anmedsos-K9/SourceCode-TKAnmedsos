import argparse
import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


COLUMNS = [
    "video_id",
    "comment_id",
    "parent_id",
    "is_reply",
    "text_original",
    "text_display",
    "text_raw",
    "text_source",
    "published_at",
    "updated_at",
    "collected_at",
    "like_count",
    "reported_reply_count",
    "source_file",
]


def read_json(path):
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def save_json(path, data):
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


def select_session(raw_directory, prefix, requested=None):
    """Pilih satu folder sesi, bukan file percobaan halaman pertama."""
    candidates = sorted(
        path
        for path in raw_directory.iterdir()
        if path.is_dir() and path.name.startswith(prefix)
    )

    if requested:
        candidates = [
            path for path in candidates if path.name == requested
        ]

    if len(candidates) != 1:
        names = [path.name for path in candidates]
        raise ValueError(
            f"Harus dipilih tepat satu sesi dengan awalan {prefix}. "
            f"Ditemukan: {names}. "
            "Gunakan --main-session atau --reply-session jika perlu."
        )

    return candidates[0]


def load_pages(paths, video_id, parent_id=None):
    """Periksa urutan halaman dan rantai pagination."""
    pages = [(path, read_json(path)) for path in paths]
    pages.sort(key=lambda item: item[1]["page_number"])

    if not pages:
        raise ValueError("Tidak ditemukan halaman JSON pada sesi.")

    previous_token = None

    for expected_number, (path, page) in enumerate(pages, start=1):
        if page["video_id"] != video_id:
            raise ValueError(f"ID video tidak sesuai: {path}")

        if page["page_number"] != expected_number:
            raise ValueError(f"Urutan halaman tidak lengkap: {path}")

        parameters = page["request_parameters"]

        if (
            parameters.get("part") != "snippet"
            or parameters.get("textFormat") != "plainText"
        ):
            raise ValueError(f"Parameter pengambilan tidak sesuai: {path}")

        if parameters.get("pageToken") != previous_token:
            raise ValueError(f"Rantai token pagination terputus: {path}")

        if expected_number > 1 and not previous_token:
            raise ValueError(
                f"Ada halaman setelah pagination berakhir: {path}"
            )

        if parent_id is not None:
            if (
                page.get("parent_id") != parent_id
                or parameters.get("parentId") != parent_id
            ):
                raise ValueError(f"ID induk balasan tidak sesuai: {path}")

        elif (
            parameters.get("videoId") != video_id
            or parameters.get("order") != "time"
        ):
            raise ValueError(f"Parameter video atau urutan tidak sesuai: {path}")

        if not isinstance(page["response"].get("items"), list):
            raise ValueError(f"Daftar items tidak valid: {path}")

        previous_token = page["response"].get("nextPageToken")

    if previous_token:
        raise ValueError(
            "Pengumpulan belum lengkap: halaman terakhir masih "
            f"memiliki nextPageToken pada {pages[-1][0]}"
        )

    return pages


def flatten_comment(
    comment,
    page,
    path,
    raw_directory,
    is_reply,
    reported_reply_count=None,
):
    snippet = comment["snippet"]
    comment_id = comment.get("id")

    if not isinstance(comment_id, str) or not comment_id.strip():
        raise ValueError(f"ID komentar kosong: {path}")

    parent_id = snippet.get("parentId") if is_reply else None

    if is_reply:
        if not parent_id or parent_id != page["parent_id"]:
            raise ValueError(f"Relasi induk balasan tidak sesuai: {path}")

    original = snippet.get("textOriginal")
    display = snippet.get("textDisplay")

    for value in [original, display]:
        if value is not None and not isinstance(value, str):
            raise ValueError(f"Atribut teks bukan string: {path}")

    return {
        "video_id": page["video_id"],
        "comment_id": comment_id,
        "parent_id": parent_id,
        "is_reply": is_reply,
        "text_original": original,
        "text_display": display,
        "text_raw": original if original is not None else (display or ""),
        "text_source": (
            "textOriginal" if original is not None else "textDisplay"
        ),
        "published_at": snippet.get("publishedAt"),
        "updated_at": snippet.get("updatedAt"),
        "collected_at": page["collected_at"],
        "like_count": snippet.get("likeCount"),
        "reported_reply_count": reported_reply_count,
        "source_file": path.relative_to(raw_directory).as_posix(),
    }


def prepare_table(rows):
    table = pd.DataFrame(rows, columns=COLUMNS)
    input_count = len(table)

    string_columns = [
        "video_id",
        "comment_id",
        "parent_id",
        "text_original",
        "text_display",
        "text_raw",
        "text_source",
        "source_file",
    ]

    for column in string_columns:
        table[column] = table[column].astype("string")

    table["is_reply"] = table["is_reply"].astype("boolean")

    for column in ["like_count", "reported_reply_count"]:
        table[column] = pd.to_numeric(
            table[column], errors="raise"
        ).astype("Int64")

        if table[column].dropna().lt(0).any():
            raise ValueError(f"Ditemukan nilai negatif pada {column}.")

    for column in ["published_at", "updated_at", "collected_at"]:
        table[column] = pd.to_datetime(
            table[column],
            format="ISO8601",
            utc=True,
            errors="raise",
        )

        if table[column].isna().any():
            raise ValueError(f"Ditemukan timestamp kosong pada {column}.")

    # Satu ID tidak boleh merujuk ke induk yang berbeda.
    for _, group in table.groupby("comment_id", sort=False):
        if group["parent_id"].nunique(dropna=False) != 1:
            raise ValueError(
                "ID komentar yang sama memiliki komentar induk berbeda."
            )

    ordered = table.sort_values(
        ["collected_at", "source_file"],
        kind="stable",
    )

    # Simpan semua observasi ID berulang untuk audit.
    duplicate_observations = ordered.loc[
        ordered.duplicated("comment_id", keep=False)
    ].copy()

    # Pertahankan observasi yang diambil paling akhir.
    table = ordered.drop_duplicates(
        subset="comment_id",
        keep="last",
    ).copy()

    table["is_empty_text"] = (
        table["text_raw"].fillna("").str.strip().eq("")
    )

    # Teks sama dengan ID berbeda ditandai, bukan dihapus.
    table["has_repeated_exact_text"] = (
        table["text_raw"].duplicated(keep=False)
        & ~table["is_empty_text"]
    )

    table["is_edited"] = table["published_at"].ne(table["updated_at"])

    table["published_date_utc"] = (
        table["published_at"].dt.strftime("%Y-%m-%d").astype("string")
    )

    table = table.sort_values(
        ["published_at", "comment_id"],
        kind="stable",
    ).reset_index(drop=True)

    summary = {
        "input_entries": input_count,
        "unique_comments": len(table),
        "duplicate_entries_removed": input_count - len(table),
        "empty_text": int(table["is_empty_text"].sum()),
        "comments_with_repeated_exact_text": int(
            table["has_repeated_exact_text"].sum()
        ),
        "edited_comments": int(table["is_edited"].sum()),
        "published_min_utc": (
            table["published_at"].min().isoformat()
            if len(table) else None
        ),
        "published_max_utc": (
            table["published_at"].max().isoformat()
            if len(table) else None
        ),
    }

    return table, duplicate_observations, summary


def save_table(table, directory, name):
    table.to_parquet(
        directory / f"{name}.parquet",
        engine="pyarrow",
        compression="snappy",
        index=False,
    )

    table.to_csv(
        directory / f"{name}.csv",
        index=False,
        encoding="utf-8-sig",
    )


def prepare_dataset(args):
    raw_directory = Path(args.input).resolve()

    if not raw_directory.is_dir():
        raise ValueError(f"Folder input tidak ditemukan: {raw_directory}")

    main_directory = select_session(
        raw_directory,
        f"comments_{args.video_id}_",
        args.main_session,
    )

    reply_directory = select_session(
        raw_directory,
        f"replies_{args.video_id}_",
        args.reply_session,
    )

    metadata_path = raw_directory / f"video_{args.video_id}.json"
    metadata = read_json(metadata_path)

    if metadata["video"]["id"] != args.video_id:
        raise ValueError("ID pada metadata video tidak sesuai.")

    source_files = [metadata_path]

    # 1. Baca dan ratakan komentar utama.
    main_pages = load_pages(
        main_directory.glob("page_*.json"),
        args.video_id,
    )

    main_rows = []

    for path, page in main_pages:
        source_files.append(path)

        for thread in page["response"]["items"]:
            snippet = thread["snippet"]

            main_rows.append(
                flatten_comment(
                    comment=snippet["topLevelComment"],
                    page=page,
                    path=path,
                    raw_directory=raw_directory,
                    is_reply=False,
                    reported_reply_count=snippet.get("totalReplyCount"),
                )
            )

    main_table, main_duplicates, main_summary = prepare_table(main_rows)

    # 2. Kelompokkan file balasan menurut komentar induk.
    reply_groups = defaultdict(list)

    for path in sorted(reply_directory.glob("parent_*/page_*.json")):
        page = read_json(path)
        reply_groups[page["parent_id"]].append(path)

    expected_parents = set(
        main_table.loc[
            main_table["reported_reply_count"].gt(0),
            "comment_id",
        ]
    )

    observed_parents = set(reply_groups)

    if expected_parents != observed_parents:
        raise ValueError(
            "Cakupan induk balasan tidak sesuai. "
            f"Belum diproses: {len(expected_parents - observed_parents)}. "
            f"Tidak diharapkan: {len(observed_parents - expected_parents)}."
        )

    # 3. Validasi pagination dan ratakan balasan.
    reply_rows = []
    reply_page_count = 0

    for parent_id, paths in reply_groups.items():
        pages = load_pages(paths, args.video_id, parent_id)
        reply_page_count += len(pages)

        for path, page in pages:
            source_files.append(path)

            for comment in page["response"]["items"]:
                reply_rows.append(
                    flatten_comment(
                        comment=comment,
                        page=page,
                        path=path,
                        raw_directory=raw_directory,
                        is_reply=True,
                    )
                )

    reply_table, reply_duplicates, reply_summary = prepare_table(reply_rows)

    # 4. Periksa hubungan komentar utama dan balasan.
    if not reply_table["parent_id"].isin(main_table["comment_id"]).all():
        raise ValueError("Ditemukan balasan tanpa komentar induk.")

    if reply_table["comment_id"].isin(main_table["comment_id"]).any():
        raise ValueError(
            "Ada ID yang muncul sebagai komentar utama sekaligus balasan."
        )

    # 5. Audit jumlah balasan setelah deduplikasi komentar utama.
    observed_counts = reply_table.groupby("parent_id").size()

    reply_audit = main_table[
        ["video_id", "comment_id", "reported_reply_count"]
    ].rename(columns={"comment_id": "parent_id"}).copy()

    reply_audit["observed_reply_count"] = (
        reply_audit["parent_id"]
        .map(observed_counts)
        .fillna(0)
        .astype("Int64")
    )

    reply_audit["difference"] = (
        reply_audit["observed_reply_count"]
        - reply_audit["reported_reply_count"]
    )

    # 6. Ringkasan jumlah komentar per tanggal publikasi.
    combined = pd.concat(
        [main_table, reply_table],
        ignore_index=True,
    )

    daily_counts = (
        combined.groupby(["published_date_utc", "is_reply"])
        .size()
        .reset_index(name="comment_count")
    )

    # 7. Tentukan folder keluaran baru.
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")

    output_directory = (
        Path(args.output).resolve()
        if args.output
        else Path("data/processed").resolve()
        / f"prepared_{args.video_id}_{run_id}"
    )

    if output_directory.exists() and any(output_directory.iterdir()):
        raise ValueError(
            "Folder output tidak kosong. Pilih folder baru."
        )

    # Hitung hash sumber sebelum menulis hasil.
    inventory = []

    for path in sorted(set(source_files)):
        raw = path.read_bytes()

        inventory.append({
            "path": path.relative_to(raw_directory).as_posix(),
            "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
        })

    summary = {
        "video_id": args.video_id,
        "prepared_at": datetime.now(timezone.utc).isoformat(),
        "main_session": main_directory.name,
        "reply_session": reply_directory.name,
        "main_pages": len(main_pages),
        "reply_pages": reply_page_count,
        "parents_with_replies_processed": len(reply_groups),
        "main_comments": main_summary,
        "replies": reply_summary,
        "total_unique_comments": len(main_table) + len(reply_table),
        "reported_replies_after_main_deduplication": int(
            main_table["reported_reply_count"].sum()
        ),
        "parents_with_reply_count_difference": int(
            reply_audit["difference"].ne(0).sum()
        ),
        "metadata_comment_count": (
            metadata["video"].get("statistics", {}).get("commentCount")
        ),
        "ignored_pilot_files": sorted(
            path.name for path in raw_directory.glob("comment_threads_*.json")
        ),
        "pagination_chains_validated": True,
        "notes": [
            "Data dapat berubah selama pengambilan melalui API.",
            "Jumlah balasan dan statistik video diamati pada waktu berbeda.",
            "Teks komentar yang diedit adalah versi saat pengambilan.",
            "Bahasa, spam, dan relevansi belum diklasifikasikan.",
            "Teks kosong dan berulang ditandai, belum dihapus.",
        ],
    }

    # 8. Simpan semua keluaran.
    output_directory.mkdir(parents=True, exist_ok=True)

    tables = [
        ("comments_main", main_table),
        ("comments_replies", reply_table),
        ("reply_count_audit", reply_audit),
        ("daily_counts", daily_counts),
        ("duplicate_main_observations", main_duplicates),
        ("duplicate_reply_observations", reply_duplicates),
    ]

    for name, table in tables:
        save_table(table, output_directory, name)

    save_json(output_directory / "video_metadata.json", metadata)
    save_json(output_directory / "summary.json", summary)

    save_json(
        output_directory / "manifest.json",
        {
            "prepared_at": summary["prepared_at"],
            "deduplication_rule": (
                "comment_id; latest collected_at within selected session"
            ),
            "script_sha256": hashlib.sha256(
                Path(__file__).read_bytes()
            ).hexdigest(),
            "input_files": inventory,
        },
    )

    # Penanda bahwa seluruh keluaran sudah berhasil ditulis.
    (output_directory / "SUCCESS").write_text(
        "Preparation completed.\n",
        encoding="utf-8",
    )

    print("Dataset berhasil disiapkan.")
    print(f"Komentar utama unik : {len(main_table)}")
    print(f"Balasan unik        : {len(reply_table)}")
    print(f"Total unik          : {len(combined)}")
    print(
        "Duplikasi dihapus   : "
        f"{main_summary['duplicate_entries_removed'] + reply_summary['duplicate_entries_removed']}"
    )
    print(f"Folder hasil        : {output_directory}")


def main():
    parser = argparse.ArgumentParser(
        description="Prepare dataset komentar YouTube dari JSON lokal."
    )

    parser.add_argument(
        "--input",
        default="data/raw",
        help="Folder yang berisi metadata dan folder sesi pengumpulan.",
    )
    parser.add_argument(
        "--video-id",
        default="Lf5oqGOCRCM",
    )
    parser.add_argument(
        "--main-session",
        help="Nama folder sesi komentar utama jika tersedia beberapa sesi.",
    )
    parser.add_argument(
        "--reply-session",
        help="Nama folder sesi balasan jika tersedia beberapa sesi.",
    )
    parser.add_argument(
        "--output",
        help="Folder output baru atau kosong.",
    )

    args = parser.parse_args()

    try:
        prepare_dataset(args)

    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        ImportError,
    ) as error:
        print(f"Prepare gagal: {error}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())