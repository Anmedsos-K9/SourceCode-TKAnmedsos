import argparse
import functools
import hashlib
import json
import math
import re
import unicodedata
import warnings
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd

try:
    import emoji
except ImportError:
    emoji = None
try:
    import ftfy
except ImportError:
    ftfy = None
try:
    import phonenumbers
except ImportError:
    phonenumbers = None
try:
    import tldextract
except ImportError:
    tldextract = None
try:
    from urlextract import URLExtract
except ImportError:
    URLExtract = None
try:
    from wordfreq import available_languages, tokenize, zipf_frequency
except ImportError:
    available_languages = tokenize = zipf_frequency = None
try:
    from vaderSentiment import vaderSentiment as vader
except ImportError:
    vader = None
try:
    from lingua import Language, LanguageDetectorBuilder
except ImportError:
    Language = LanguageDetectorBuilder = None

REQUIRED_PACKAGES = {
    "emoji": "emoji", "ftfy": "ftfy", "phonenumbers": "phonenumbers",
    "tldextract": "tldextract", "URLExtract": "urlextract",
    "zipf_frequency": "wordfreq", "LanguageDetectorBuilder": "lingua-language-detector",
    "vader": "vaderSentiment",
}

PROJECT_ROOT = Path(__file__).resolve().parent.parent
INTERIM_ROOT = PROJECT_ROOT / "data" / "interim"
PROCESSED_ROOT = PROJECT_ROOT / "data" / "processed"

def default_video_id():
    try:
        from dotenv import load_dotenv
        load_dotenv(PROJECT_ROOT / ".env")
    except ImportError:
        pass
    import os
    return os.getenv("YOUTUBE_VIDEO_ID", "").strip() or None

REQUIRED_INTERIM_FILES = [
    "comments_main.parquet",
    "comments_replies.parquet",
    "video_metadata.json",
    "summary.json",
    "SUCCESS",
]

VIDEO_CONTEXT_FILE = INTERIM_ROOT / "video_context.json"

from cleaning_rules import (
    EMOJI_NAME_LANGUAGE,
    SKIN_TONE_MODIFIERS,
    MIN_LETTERS_FOR_LANGUAGE,
    LANGUAGE_REVIEW_RATIO,
    LATIN_SHARE_MIN,
    PRIOR_MIN_TOKENS,
    WORD_MODEL_REVIEW_MARGIN,
    LINGUA_TO_WORDFREQ_CODE,
    SPAM_STRONG_PATTERNS,
    SPAM_WEAK_PATTERNS,
    SPAM_REVIEW_ALONE,
    REFERENCE_DOMAINS,
    REFERENCE_SUFFIX_LABELS,
    PHONE_DEFAULT_REGION,
    URL_WORD_LABEL_MIN_ZIPF,
    URL_WORD_TLD_MIN_ZIPF,
    REPEATED_TEXT_MIN_COUNT,
    REPEATED_TEXT_MIN_WORDS,
    AI_TERMS,
    AI_REFERENCE,
    IMPLICIT_USE,
    WORK_EXCLUSION_PHRASES,
    PERSONA_ROLE_WORDS,
    PERSONA_JOKE_ROLES,
    PERSONA_REPLACEMENT_JOKE,
    PERSONA_CREDENTIAL,
    CLAIM_TERMS,
    MENTION_PATTERN,
    HASHTAG_PATTERN,
    VIDEO_TIMESTAMP_PATTERN,
    MENTION_PLACEHOLDER,
    MENTION_REPLACE_PATTERN,
    VIDEO_TIMESTAMP_REMOVAL,
    INTENSIFIED_TAG,
    CAPS_WORD_MIN_ZIPF,
    CAPS_ACRONYM_SHARE,
    CAPS_MIN_EVIDENCE,
    ELONGATION_MIN_ZIPF,
    ELONGATION_MIN_GAIN,
    WORD_TOKEN,
    ELONGATED_RUN,
    BOLD_PATTERN,
    ITALIC_PATTERN,
    EMPTY_BRACKETS,
    SPACE_BEFORE_PUNCTUATION,
    FRAMES,
)

def compile_patterns(patterns):
    return [re.compile(pattern) for pattern in patterns]

AI_REGEX = compile_patterns(AI_TERMS)
AI_REFERENCE_REGEX = compile_patterns(AI_REFERENCE)
IMPLICIT_USE_REGEX = compile_patterns(IMPLICIT_USE)
WORK_EXCLUSION_REGEX = compile_patterns(WORK_EXCLUSION_PHRASES)
CLAIM_REGEX = compile_patterns(CLAIM_TERMS)
FRAME_NAMES = tuple(FRAMES)
FRAME_REGEX = {
    name: {
        "strong": compile_patterns(spec["strong"]),
        "weak": compile_patterns(spec["weak"]),
        "pairs": [(re.compile(a), re.compile(b)) for a, b in spec["pairs"]],
        "requires_ai": spec["requires_ai"],
    }
    for name, spec in FRAMES.items()
}

SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")
SPAM_STRONG_REGEX = {k: re.compile(v) for k, v in SPAM_STRONG_PATTERNS.items()}
SPAM_WEAK_REGEX = {k: re.compile(v) for k, v in SPAM_WEAK_PATTERNS.items()}

def check_dependencies():
    missing = sorted({package for name, package in REQUIRED_PACKAGES.items()
                      if globals().get(name) is None})
    if missing:
        raise ImportError("Library belum terpasang: " + ", ".join(missing)
                          + ". Jalankan: pip install " + " ".join(missing))

_SHARED = {}

def url_extractor():
    if "url" not in _SHARED:
        _SHARED["url"] = URLExtract()
    return _SHARED["url"]

def domain_extractor():
    if "domain" not in _SHARED:

        _SHARED["domain"] = tldextract.TLDExtract(suffix_list_urls=(), cache_dir=None)
    return _SHARED["domain"]

def ftfy_config():
    if "ftfy" not in _SHARED:

        _SHARED["ftfy"] = ftfy.TextFixerConfig(
            uncurl_quotes=False, unescape_html=False, normalization="NFC", explain=False)
    return _SHARED["ftfy"]

def candidate_languages():
    wordfreq_codes = set(available_languages())
    selected = []
    for language in Language.all():
        code = language.iso_code_639_1.name.lower()
        if LINGUA_TO_WORDFREQ_CODE.get(code, code) in wordfreq_codes:
            selected.append(language)
    return sorted(selected, key=lambda language: language.name)

def word_tokens(text):
    return [t for t in tokenize(text, "en") if any(ch.isalpha() for ch in t)]

def guess_people_from_title(title):
    if not title or "|" not in title:
        return []
    candidate = title.rsplit("|", 1)[-1].strip()
    words = candidate.split()
    if 2 <= len(words) <= 4 and all(w[:1].isupper() for w in words):
        return [{"name": candidate, "role": "guest", "source": "title_heuristic"}]
    return []

def name_aliases(person):
    names = {person["name"]} | set(person.get("aliases", []))
    for name in list(names):
        names.update(part for part in name.split() if len(part) >= 2)
    return sorted({n.lower() for n in names}, key=len, reverse=True)

def configure_video_context(video_id, metadata, people_override=None):
    context = {}
    if VIDEO_CONTEXT_FILE.exists():
        context.update(read_json(VIDEO_CONTEXT_FILE).get(video_id, {}))

    if people_override:
        context["people"] = [{"name": name, "role": "unspecified", "source": "cli"}
                             for name in people_override]
    if not context.get("people"):
        title = metadata["video"].get("snippet", {}).get("title")
        context["people"] = guess_people_from_title(title)

    aliases = [alias for person in context.get("people", []) for alias in name_aliases(person)]
    subjects = [re.escape(word) for word in PERSONA_ROLE_WORDS]
    subjects += [re.escape(alias) + r"(?:'s)?" for alias in aliases]
    subject_pattern = "|".join(sorted(subjects, key=len, reverse=True))

    _SHARED["persona_subject"] = re.compile(rf"\b({subject_pattern})\b")

    joke_subjects = [re.escape(w) for w in PERSONA_JOKE_ROLES]
    joke_subjects += [re.escape(alias) for alias in aliases]
    _SHARED["persona_joke"] = re.compile(PERSONA_REPLACEMENT_JOKE.format(
        subjects="|".join(sorted(joke_subjects, key=len, reverse=True))))
    context["persona_aliases"] = aliases
    return context

def read_json(path):
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)

def save_json(path, data):
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2, default=str)

def save_table(table, directory, name):
    table.to_parquet(directory / f"{name}.parquet", engine="pyarrow",
                     compression="snappy", index=False)
    table.to_csv(directory / f"{name}.csv", index=False, encoding="utf-8-sig")

def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def join_unique(values):
    return "; ".join(dict.fromkeys(v for v in values if v))

def matched_terms(regex_list, text):
    hits = []
    for regex in regex_list:
        match = regex.search(text)
        if match:
            hits.append(match.group(0).strip())
    return hits

def find_interim_directory(video_id, requested=None):
    if requested:
        path = Path(requested)
        candidate = path if path.is_absolute() else INTERIM_ROOT / requested
        if not candidate.is_dir():
            raise ValueError(f"Folder interim tidak ditemukan: {candidate}")
        return candidate.resolve()

    if not INTERIM_ROOT.is_dir():
        raise ValueError(
            f"Folder {INTERIM_ROOT} belum ada. Jalankan 04_prepare_dataset.py dulu."
        )

    candidates = sorted(
        path for path in INTERIM_ROOT.glob(f"prepared_{video_id}_*")
        if path.is_dir() and (path / "SUCCESS").exists()
    )
    if not candidates:
        raise ValueError(
            f"Tidak ada sesi interim lengkap untuk video {video_id} di {INTERIM_ROOT}. "
            "Jalankan 04_prepare_dataset.py dulu."
        )
    return candidates[-1]

def load_interim(directory, video_id):
    missing = [name for name in REQUIRED_INTERIM_FILES if not (directory / name).exists()]
    if missing:
        raise ValueError(f"File interim tidak lengkap di {directory}: {missing}")

    summary = read_json(directory / "summary.json")
    metadata = read_json(directory / "video_metadata.json")

    if summary.get("video_id") != video_id or metadata["video"]["id"] != video_id:
        raise ValueError("ID video pada data interim tidak sesuai dengan --video-id.")

    main = pd.read_parquet(directory / "comments_main.parquet")
    replies = pd.read_parquet(directory / "comments_replies.parquet")

    if main["comment_id"].duplicated().any() or replies["comment_id"].duplicated().any():
        raise ValueError("Data interim masih memiliki comment_id ganda.")
    if not replies["parent_id"].isin(main["comment_id"]).all():
        raise ValueError("Data interim memiliki balasan tanpa komentar induk.")

    input_files = [
        {"path": name, "sha256": sha256(directory / name)}
        for name in ["comments_main.parquet", "comments_replies.parquet",
                     "video_metadata.json", "summary.json"]
    ]

    return main, replies, metadata, summary, input_files

def remove_invisible_format_characters(text):
    protected = set()
    for match in emoji.emoji_list(text):
        protected.update(range(match["match_start"], match["match_end"]))
    return "".join(ch for i, ch in enumerate(text)
                   if i in protected or unicodedata.category(ch) != "Cf")

def clean_text(text):
    if text is None or text is pd.NA or (isinstance(text, float) and pd.isna(text)):
        return ""
    text = ftfy.fix_text(str(text), config=ftfy_config())
    text = remove_invisible_format_characters(text)
    lines = (" ".join(line.split()) for line in text.splitlines())
    return "\n".join(line for line in lines if line)

def matching_text(text_clean):
    text = ftfy.fixes.uncurl_quotes(text_clean)
    text = unicodedata.normalize("NFKC", text).casefold()
    return "\n".join(" ".join(line.split()) for line in text.splitlines() if line.strip())

def emoji_readable_name(character):
    base = SKIN_TONE_MODIFIERS.sub("", character)
    for candidate in (base, base.replace("\ufe0f", ""), character):
        if emoji.is_emoji(candidate):
            name = emoji.demojize(candidate, delimiters=("", ""),
                                  language=EMOJI_NAME_LANGUAGE)
            break
    else:
        name = emoji.demojize(character, delimiters=("", ""), language=EMOJI_NAME_LANGUAGE)

    name = re.sub(r"[^\w]+", "_", name.strip()).strip("_").lower()
    if len(base) == 2 and all(0x1F1E6 <= ord(c) <= 0x1F1FF for c in base):
        return f"flag_{name}"
    return name

def emoji_to_text(text):
    found = emoji.emoji_list(text)
    if not found:
        return text, []

    pieces, names = [], []
    cursor = index = 0
    while index < len(found):
        item = found[index]
        start, char = item["match_start"], item["emoji"]
        run, run_end = 1, item["match_end"]
        while (index + run < len(found)
               and found[index + run]["emoji"] == char
               and found[index + run]["match_start"] == run_end):
            run_end = found[index + run]["match_end"]
            run += 1

        name = emoji_readable_name(char)
        label = name + (f" x{run}" if run > 1 else "")
        prefix = text[cursor:start]
        if prefix:
            pad = "" if prefix.endswith((" ", "\n")) else " "
        else:
            pad = " " if pieces else ""
        pieces.append(f"{prefix}{pad}{label}")
        names.append(name)
        cursor = run_end
        index += run

    rest = text[cursor:]
    pieces.append(("" if not rest or rest.startswith((" ", "\n")) else " ") + rest)
    return "".join(pieces), names

@functools.lru_cache(maxsize=None)
def find_urls(text):
    if "." not in text:
        return ()
    found = url_extractor().find_urls(text, get_indices=True)
    return tuple(item for item in found if is_plausible_url(item[0]))

def is_plausible_url(url):
    if re.match(r"(?i)(https?://|www\.)", url):
        return True
    host, *rest = re.split(r"[/?#:]", url, maxsplit=1)
    labels = host.split(".")
    if len(labels) < 2 or labels[-1][:1].isupper() or labels[-2].isdigit():
        return False
    if rest:
        return True

    label, tld = labels[-2].lower(), labels[-1].lower()
    if len(label) == 1:
        return False
    return not (zipf_frequency(label, "en") >= URL_WORD_LABEL_MIN_ZIPF
                and zipf_frequency(tld, "en") >= URL_WORD_TLD_MIN_ZIPF)

def remove_urls(text):
    for _, (start, end) in sorted(find_urls(text), key=lambda item: -item[1][0]):
        text = text[:start] + " " + text[end:]
    return text

def build_caps_profile(texts):
    counts = {}
    for text in texts:
        for token in WORD_TOKEN.findall(strip_noise(text)):
            if len(token) < 2:
                continue
            caps, lower, total = counts.get(token.lower(), (0, 0, 0))
            counts[token.lower()] = (caps + token.isupper(), lower + token.islower(), total + 1)
    _SHARED["caps_profile"] = counts

def vader_resources():
    if "vader" not in _SHARED:
        analyzer = vader.SentimentIntensityAnalyzer()
        words = set(analyzer.lexicon) | set(vader.BOOSTER_DICT) | set(vader.NEGATE)
        _SHARED["vader"] = {word.lower() for word in words}
    return _SHARED["vader"]

def is_mixed_case_comment(text):
    words = vader.SentiText(text).words_and_emoticons
    return bool(words) and vader.allcap_differential(words)

def is_acronym(token):
    caps, lower, total = _SHARED.get("caps_profile", {}).get(token.lower(), (0, 0, 0))
    return total >= CAPS_MIN_EVIDENCE and caps / total > CAPS_ACRONYM_SHARE

def is_emphatic_caps(token):
    if len(token) < 2 or not token.isupper():
        return False
    word = token.lower().replace("'", "")
    if word in vader_resources() or token.lower() in vader_resources():
        return True
    if len(token) < 3 or zipf_frequency(token.lower(), "en") < CAPS_WORD_MIN_ZIPF:
        return False
    caps, lower, total = _SHARED.get("caps_profile", {}).get(token.lower(), (0, 0, 0))
    if total >= CAPS_MIN_EVIDENCE:
        titled = total - caps - lower
        if caps / total > CAPS_ACRONYM_SHARE:
            return False
        if titled > lower and lower + titled >= CAPS_MIN_EVIDENCE:
            return False
    return True

def de_elongate(token):
    if not ELONGATED_RUN.search(token):
        return None
    lower = token.lower()
    original_zipf = zipf_frequency(lower, "en")
    runs = list(ELONGATED_RUN.finditer(lower))[:4]
    best, best_zipf = None, 0.0
    for keep in range(1 << len(runs)):
        pieces, cursor = [], 0
        for i, run in enumerate(runs):
            pieces.append(lower[cursor:run.start()])
            pieces.append(run.group(1) * (2 if keep >> i & 1 else 1))
            cursor = run.end()
        candidate = "".join(pieces) + lower[cursor:]
        candidate = ELONGATED_RUN.sub(lambda m: m.group(1), candidate)
        value = zipf_frequency(candidate, "en")
        if value > best_zipf:
            best, best_zipf = candidate, value
    if best_zipf >= ELONGATION_MIN_ZIPF and best_zipf - original_zipf >= ELONGATION_MIN_GAIN:
        return best
    return None

def mark_intensity(line, caps_counts=True):
    def tag_formatted(match):
        content = match.group(1)
        body = content.rstrip(".,!?;:")
        return body + INTENSIFIED_TAG + content[len(body):]

    line = BOLD_PATTERN.sub(tag_formatted, line)
    line = ITALIC_PATTERN.sub(tag_formatted, line)

    def replace(match):
        token = match.group(0)
        if token == "User":
            return token
        stretched = de_elongate(token)
        if stretched is not None:
            return stretched + INTENSIFIED_TAG
        if caps_counts and is_emphatic_caps(token):
            return token.lower() + INTENSIFIED_TAG
        return token

    in_phrase = set()
    if caps_counts:
        tokens = list(WORD_TOKEN.finditer(line))
        run = []
        for index, match in enumerate(tokens + [None]):
            is_caps = match is not None and match.group(0).isupper()
            joined = (run and match is not None
                      and re.fullmatch(r"[\s,'\-–—]*", line[tokens[run[-1]].end():match.start()]))
            if is_caps and (not run or joined):
                run.append(index)
                continue
            multi = [i for i in run if len(tokens[i].group(0)) >= 2]
            if len(multi) >= 2:
                in_phrase.update(tokens[i].start() for i in run)
            run = [index] if is_caps else []

    def replace_in_phrase(match):
        token = match.group(0)
        if match.start() not in in_phrase:
            return replace(match)
        if len(token) == 1:
            return token.lower()
        if is_acronym(token):
            return token
        return (de_elongate(token) or token.lower()) + INTENSIFIED_TAG

    line = WORD_TOKEN.sub(replace_in_phrase, line)
    return re.sub(r"(" + re.escape(INTENSIFIED_TAG) + r")+", INTENSIFIED_TAG, line)

def analysis_text(text_normalized):
    text = remove_urls(text_normalized)
    text = VIDEO_TIMESTAMP_REMOVAL.sub(" ", text)
    text = MENTION_REPLACE_PATTERN.sub(f" {MENTION_PLACEHOLDER} ", text)

    mixed_case = is_mixed_case_comment(text)
    text = "\n".join(mark_intensity(line, caps_counts=mixed_case) for line in text.splitlines())
    text, _ = emoji_to_text(text)
    lines = []
    for line in text.splitlines():
        line = EMPTY_BRACKETS.sub(" ", line)
        line = " ".join(line.split())
        line = re.sub(r"(\[User\]\s*)+", MENTION_PLACEHOLDER + " ", line).strip()
        line = SPACE_BEFORE_PUNCTUATION.sub(r"\1", line)
        line = re.sub(r"^[\s,;:\-–—]+", "", line)
        if line:
            lines.append(line)
    return "\n".join(lines)

def has_content(text_clean):
    rest = text_clean.replace(MENTION_PLACEHOLDER, "").replace(INTENSIFIED_TAG, "")
    return bool(re.search(r"\w", rest))

def url_domain(url):
    parts = domain_extractor()(url)
    return (parts.top_domain_under_public_suffix or parts.fqdn or url).lower()

def is_reference_domain(url):
    parts = domain_extractor()(url)
    domain = (parts.top_domain_under_public_suffix or "").lower()
    suffix_labels = set(parts.suffix.lower().split("."))
    return domain in REFERENCE_DOMAINS or bool(suffix_labels & set(REFERENCE_SUFFIX_LABELS))

def strip_noise(text):
    text = remove_urls(text)
    text = MENTION_PATTERN.sub(" ", text)
    text = HASHTAG_PATTERN.sub(" ", text)
    return VIDEO_TIMESTAMP_PATTERN.sub(" ", text)

def has_phone_number(text):
    matcher = phonenumbers.PhoneNumberMatcher(
        strip_noise(text), PHONE_DEFAULT_REGION, leniency=phonenumbers.Leniency.VALID)
    return matcher.has_next()

def text_features(text_clean):
    urls = [url for url, _ in find_urls(text_clean)]
    domains = [url_domain(u) for u in urls]
    tokens = word_tokens(text_clean)
    return {
        "char_count": len(text_clean),
        "word_count": len(tokens),
        "emoji_count": emoji.emoji_count(text_clean),
        "has_url": bool(urls),
        "url_domains": join_unique(domains),
        "has_non_reference_url": any(not is_reference_domain(u) for u in urls),
        "mention_count": len(MENTION_PATTERN.findall(text_clean)),
        "hashtags": join_unique(HASHTAG_PATTERN.findall(text_clean)),
        "has_video_timestamp": bool(VIDEO_TIMESTAMP_PATTERN.search(text_clean)),
        "has_phone_number": has_phone_number(text_clean),
    }

def build_language_detector():
    return LanguageDetectorBuilder.from_languages(*candidate_languages()).build()

def language_input(text_clean):
    text = strip_noise(text_clean)
    text = emoji.replace_emoji(text, replace=" ")
    return " ".join(text.split())

def word_model_score(tokens, code, log_prior):
    code = LINGUA_TO_WORDFREQ_CODE.get(code, code)
    return sum(zipf_frequency(token, code) for token in tokens) + log_prior

def word_model_available(code):
    code = LINGUA_TO_WORDFREQ_CODE.get(code, code)
    try:
        zipf_frequency("test", code)
        return True
    except Exception:
        return False

def corpus_language_priors(top_codes, token_counts):
    reliable = pd.Series([c for c, n in zip(top_codes, token_counts) if n >= PRIOR_MIN_TOKENS])
    codes = [l.iso_code_639_1.name.lower() for l in candidate_languages()]
    codes = [code for code in codes if word_model_available(code)]
    counts = reliable.value_counts().reindex(codes, fill_value=0) + 1
    return (counts / counts.sum()).map(math.log10).to_dict()

def detect_languages(texts):
    detector = build_language_detector()
    prepared = [language_input(t) for t in texts]
    results = [None] * len(prepared)
    to_detect = []

    for index, text in enumerate(prepared):
        if sum(ch.isalpha() for ch in text) < MIN_LETTERS_FOR_LANGUAGE:
            results[index] = {"lang_label": "und", "lang_detected": None,
                              "lang_en_confidence": None, "lang_method": "too_few_letters",
                              "lang_needs_review": False}
        else:
            to_detect.append(index)

    confidence_lists = detector.compute_language_confidence_values_in_parallel(
        [prepared[i] for i in to_detect])
    tokens_list = [word_tokens(prepared[i]) for i in to_detect]
    top_codes = [values[0].language.iso_code_639_1.name.lower() for values in confidence_lists]
    log_priors = corpus_language_priors(top_codes, [len(t) for t in tokens_list])

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for index, values, tokens, top_code in zip(
                to_detect, confidence_lists, tokens_list, top_codes):
            text = prepared[index]
            top = values[0]
            second_value = values[1].value if len(values) > 1 else 0.0
            en_value = next((v.value for v in values if v.language == Language.ENGLISH), 0.0)
            letters = [ch for ch in text if ch.isalpha()]
            latin_share = sum(ch.isascii() for ch in letters) / len(letters) if letters else 0

            if top.language == Language.ENGLISH:
                label, method = "en", "lingua"
                review = second_value > 0 and top.value / second_value < LANGUAGE_REVIEW_RATIO
            elif latin_share > LATIN_SHARE_MIN and tokens:

                scores = {code: word_model_score(tokens, code, prior)
                          for code, prior in log_priors.items()}
                best_other = max(score for code, score in scores.items() if code != "en")
                if scores["en"] >= best_other:
                    label, method = "en", "word_frequency_model"
                else:
                    label, method = "non_en", "lingua+word_frequency_model"
                review = abs(scores["en"] - best_other) < WORD_MODEL_REVIEW_MARGIN
            else:
                label, method = "non_en", "lingua"
                review = en_value > 0 and top.value / en_value < LANGUAGE_REVIEW_RATIO

            results[index] = {"lang_label": label, "lang_detected": top_code,
                              "lang_en_confidence": round(float(en_value), 4),
                              "lang_method": method, "lang_needs_review": bool(review)}

    language_priors = {code: round(10 ** value, 5) for code, value in log_priors.items()}
    return pd.DataFrame(results), language_priors

def spam_flags(row):
    text = row["text_match_no_mentions"]
    strong = [name for name, rx in SPAM_STRONG_REGEX.items() if rx.search(text)]
    weak = [name for name, rx in SPAM_WEAK_REGEX.items() if rx.search(text)]
    reasons, review = list(strong), []

    if row["has_phone_number"]:
        reasons.append("contact_phone_number")

    if row["has_non_reference_url"]:
        if strong or weak:
            reasons.append("promotional_url")
        else:
            review.append("non_reference_url")

    if row["duplicate_text_count"] >= REPEATED_TEXT_MIN_COUNT:
        if weak or strong:
            reasons.append("repeated_promotional_text")
        elif row["word_count"] >= REPEATED_TEXT_MIN_WORDS:
            review.append("repeated_long_text")

    if not reasons and (len(weak) >= 2 or set(weak) & SPAM_REVIEW_ALONE):
        review.append("weak_promo_signals:" + "+".join(weak))

    return pd.Series({
        "spam_reasons": "; ".join(dict.fromkeys(reasons)),
        "spam_review_reasons": "; ".join(review),
        "spam_weak_signals": "; ".join(weak),
        "is_spam": bool(reasons),
        "spam_needs_review": bool(review) and not reasons,
    })

def relevance_flags(text):
    persona_subject = _SHARED["persona_subject"]
    masked = _SHARED["persona_joke"].sub(" ", text)
    for regex in WORK_EXCLUSION_REGEX:
        masked = regex.sub(" ", masked)
    sentences = [x for x in SENTENCE_SPLIT.split(masked) if x.strip()]
    ai_in_sentence = [bool(matched_terms(AI_REFERENCE_REGEX, x)) for x in sentences]

    found = {frame: [] for frame in FRAME_NAMES}
    link = {frame: None for frame in FRAME_NAMES}
    for sentence, has_ai in zip(sentences, ai_in_sentence):
        persona = bool(persona_subject.search(sentence) and PERSONA_CREDENTIAL.search(sentence))
        for frame, spec in FRAME_REGEX.items():
            if persona and frame != "replacement":
                continue
            strong = matched_terms(spec["strong"], sentence)
            weak = matched_terms(spec["weak"], sentence)
            for first, second in spec["pairs"]:
                a, b = first.search(sentence), second.search(sentence)
                if a and b:
                    weak.append(f"{a.group(0)} + {b.group(0)}")
            if spec["requires_ai"] and not has_ai:
                continue
            if (strong or weak) and has_ai:
                link[frame] = "ai_linked"
            elif strong and link[frame] is None:
                link[frame] = "strong"
            elif (frame == "use_at_work" and weak and link[frame] is None
                  and matched_terms(IMPLICIT_USE_REGEX, sentence)):
                link[frame] = "implicit"
            else:
                continue
            found[frame] += strong + weak

    frames = [frame for frame in FRAME_NAMES if link[frame]]
    ai = matched_terms(AI_REGEX, text)
    claim = matched_terms(CLAIM_REGEX, text)

    if frames:
        label = "ai_work"
        confidence = "high" if any(link[f] == "ai_linked" for f in frames) else "low"
    elif (claim and ai) or len(claim) >= 2:
        label, confidence = "ai_claim", pd.NA
    elif ai:
        label, confidence = "ai_general", pd.NA
    else:
        label, confidence = "none", pd.NA

    return pd.Series({
        "ai_terms": join_unique(ai),
        "work_terms": join_unique(term for f in frames for term in found[f]),
        "claim_terms": join_unique(claim),
        "work_exclusion_phrases": join_unique(
            matched_terms(WORK_EXCLUSION_REGEX + [_SHARED["persona_joke"]], text)),
        "narrative_frame": ";".join(frames),
        **{f"frame_{name}": name in frames for name in FRAME_NAMES},
        "relevance_link": join_unique(link[f] for f in frames),
        "relevance_label": label,
        "relevance_confidence": confidence,
    })

def parse_bool(value):
    if value is None or pd.isna(value) or str(value).strip() == "":
        return None
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "ya"}:
        return True
    if text in {"0", "false", "no", "n", "tidak"}:
        return False
    raise ValueError(f"Nilai boolean tidak dikenali pada overrides: {value}")

def apply_overrides(table, overrides_path):
    table["manual_override_applied"] = False
    table["manual_is_relevant"] = pd.Series(pd.NA, index=table.index, dtype="boolean")
    report = {"file": None, "rows": 0, "language_changed": 0,
              "spam_changed": 0, "relevance_changed": 0}
    if not overrides_path:
        return table, report

    overrides = pd.read_csv(overrides_path, dtype=str, encoding="utf-8-sig")
    if "comment_id" not in overrides.columns:
        raise ValueError("File overrides wajib memiliki kolom comment_id.")
    report["file"] = str(overrides_path)

    position = pd.Series(table.index, index=table["comment_id"])
    for _, row in overrides.iterrows():
        cid = str(row["comment_id"]).strip()
        if cid not in position.index:
            continue
        i = position[cid]
        changed = False

        language = str(row.get("manual_language", "") or "").strip()
        if language and language.lower() != "nan":
            if language not in {"en", "non_en", "und"}:
                raise ValueError(f"manual_language tidak valid: {language}")
            report["language_changed"] += int(table.at[i, "lang_label"] != language)
            table.at[i, "lang_label"] = language
            table.at[i, "lang_method"] = "manual"
            changed = True

        spam = parse_bool(row.get("manual_is_spam"))
        if spam is not None:
            report["spam_changed"] += int(bool(table.at[i, "is_spam"]) != spam)
            table.at[i, "is_spam"] = spam
            changed = True

        relevant = parse_bool(row.get("manual_is_relevant"))
        if relevant is not None:
            table.at[i, "manual_is_relevant"] = relevant
            changed = True

        if changed:
            table.at[i, "manual_override_applied"] = True
            report["rows"] += 1

    return table, report

def run(args):
    check_dependencies()
    interim_directory = find_interim_directory(args.video_id, args.interim_session)
    main_table, reply_table, metadata, interim_summary, input_files = load_interim(
        interim_directory, args.video_id)
    context = configure_video_context(args.video_id, metadata, args.people)

    steps = []

    def record(step, before, after_table, note, flagged=None):
        steps.append({
            "step": step, "rows_before": int(before), "rows_after": int(len(after_table)),
            "removed": int(before - len(after_table)),
            "flagged_not_removed": None if flagged is None else int(flagged),
            "main_after": int((~after_table["is_reply"]).sum()),
            "reply_after": int(after_table["is_reply"].sum()),
            "note": note,
        })

    raw_entries = (interim_summary["main_comments"]["input_entries"]
                   + interim_summary["replies"]["input_entries"])

    table = pd.concat([main_table, reply_table], ignore_index=True)
    table = table.drop(columns=["is_empty_text", "has_repeated_exact_text"], errors="ignore")
    record("1-3 flatten + validasi + deduplikasi (script 04)", raw_entries, table,
           f"Dibaca dari interim: {interim_directory.name}")

    table["text_normalized"] = table["text_raw"].map(clean_text).astype("string")
    table["text_match"] = table["text_normalized"].map(matching_text)

    table["text_match_no_mentions"] = table["text_normalized"].map(
        lambda t: matching_text(strip_noise(t)))
    changed = int(table["text_normalized"].ne(table["text_raw"].fillna("")).sum())
    features = pd.DataFrame(table["text_normalized"].map(text_features).tolist())
    table = pd.concat([table, features], axis=1)
    record("5 text cleaning", len(table), table,
           "ftfy, karakter tak terlihat, normalisasi spasi/line break.", flagged=changed)

    table["emoji_names"] = (table["text_normalized"].map(lambda t: emoji_to_text(t)[1])
                            .map(join_unique).astype("string"))
    build_caps_profile(table["text_normalized"].fillna(""))
    table["text_clean"] = table["text_normalized"].map(analysis_text).astype("string")
    table["intensified_count"] = table["text_clean"].str.count(re.escape(INTENSIFIED_TAG))
    letters = table["text_normalized"].fillna("").map(
        lambda t: "".join(ch for ch in strip_noise(t) if ch.isalpha()))
    table["all_caps_comment"] = letters.str.len().ge(10) & letters.map(str.isupper)
    record("5b teks analisis", len(table), table,
           "URL dan timestamp video dihapus, mention -> [User], penekanan -> "
           "kata[Intensified], emoji -> nama library.",
           flagged=int(table["text_clean"].ne(table["text_normalized"]).sum()))

    table["is_empty_text"] = ~table["text_clean"].fillna("").map(has_content)
    nonempty = ~table["is_empty_text"]
    duplicate_counts = table.loc[nonempty, "text_match"].value_counts()
    table["duplicate_text_count"] = table["text_match"].map(duplicate_counts).fillna(0).astype("Int64")
    table["is_repeated_text"] = table["duplicate_text_count"].gt(1)

    table = table.sort_values(["published_at", "comment_id"], kind="stable").reset_index(drop=True)
    table["repeated_text_rank"] = table.groupby("text_match").cumcount().add(1).astype("Int64")

    language, language_priors = detect_languages(table["text_normalized"].fillna("").tolist())
    table = pd.concat([table, language], axis=1)

    table = pd.concat([table, table.apply(spam_flags, axis=1)], axis=1)

    table = pd.concat([table, table["text_match_no_mentions"].apply(relevance_flags)], axis=1)

    table, override_report = apply_overrides(table, args.overrides)

    allowed_labels = {"ai_work"}
    if args.relevance_scope == "work_and_claims":
        allowed_labels.add("ai_claim")

    selected_frames = set(args.frames)
    frame_selected = pd.Series(False, index=table.index)
    for frame in selected_frames:
        frame_selected |= table[f"frame_{frame}"]
    auto_relevant = (
        (table["relevance_label"].eq("ai_work") & frame_selected)
        | (table["relevance_label"].isin(allowed_labels - {"ai_work"}))
    )
    table["is_relevant"] = (
        table["manual_is_relevant"].astype("object")
        .where(table["manual_is_relevant"].notna(), auto_relevant).astype(bool)
    )
    override_report["relevance_changed"] = int(
        (table["manual_is_relevant"].notna() & table["is_relevant"].ne(auto_relevant)).sum())
    table["spam_needs_review"] = table["spam_needs_review"] & ~table["is_spam"]

    snippet = metadata["video"].get("snippet", {})

    video_published = pd.to_datetime(snippet.get("publishedAt"), utc=True)
    table["video_title"] = snippet.get("title")
    table["channel_title"] = snippet.get("channelTitle")
    table["video_published_at"] = video_published
    table["narrative_orientation"] = context.get("narrative_orientation", "unknown")
    table["narrative_orientation_source"] = context.get("narrative_orientation_source", "not_available")

    table["comment_type"] = table["is_reply"].map({False: "main", True: "reply"})
    table["thread_id"] = table["parent_id"].fillna(table["comment_id"]).astype("string")
    table["days_since_video_published"] = (
        (table["published_at"] - video_published).dt.total_seconds() / 86400).round(3)
    table["published_week_utc"] = (
        table["published_at"].dt.tz_convert(None).dt.to_period("W-SUN")
        .dt.start_time.dt.strftime("%Y-%m-%d").astype("string"))
    table["published_month_utc"] = table["published_at"].dt.strftime("%Y-%m").astype("string")

    parents = table.loc[~table["is_reply"]].set_index("comment_id")
    table["parent_text_clean"] = table["parent_id"].map(parents["text_clean"]).astype("string")
    table["parent_relevance_label"] = table["parent_id"].map(parents["relevance_label"]).astype("string")
    table = table.sort_values(["thread_id", "published_at", "comment_id"], kind="stable")
    table["reply_position"] = table.groupby("thread_id").cumcount()
    table.loc[~table["is_reply"], "reply_position"] = 0

    table["in_relevant_thread"] = (
        table["is_reply"] & ~table["is_relevant"]
        & table["parent_relevance_label"].isin(allowed_labels).fillna(False)
    )
    if args.include_thread_context:
        table.loc[table["in_relevant_thread"] & table["manual_is_relevant"].isna(),
                  "is_relevant"] = True

    reason = pd.Series("", index=table.index, dtype="object")
    reason = reason.mask(reason.eq("") & table["is_empty_text"], "empty_text")
    reason = reason.mask(reason.eq("") & table["lang_label"].eq("non_en"), "non_english")
    reason = reason.mask(reason.eq("") & table["lang_label"].eq("und"), "language_undetermined")
    reason = reason.mask(reason.eq("") & table["is_spam"], "spam")
    reason = reason.mask(reason.eq("") & ~table["is_relevant"], "not_relevant")
    table["exclusion_reason"] = reason.replace("", pd.NA).astype("string")
    table["include_in_analysis"] = table["exclusion_reason"].isna()

    funnel = table.copy()
    for step, code, note, flag_column in [
        ("4 missing values", "empty_text", "Teks kosong setelah cleaning dikeluarkan.", None),
        ("6 language filtering (non-Inggris)", "non_english",
         "Komentar non-Inggris dikeluarkan; flagged = perlu ditinjau.", "lang_needs_review"),
        ("6 language filtering (tidak dapat ditentukan)", "language_undetermined",
         f"Huruf < {MIN_LETTERS_FOR_LANGUAGE} (emoji/simbol saja).", None),
        ("7 spam filtering", "spam", "Hanya aturan kuat yang mengeluarkan baris.",
         "spam_needs_review"),
        ("8 relevance filtering", "not_relevant",
         f"Label: {sorted(allowed_labels)}; bingkai: {sorted(selected_frames)}"
         + ("; ditambah balasan di thread relevan." if args.include_thread_context else "."),
         None),
    ]:
        before = len(funnel)
        flagged = int(funnel[flag_column].sum()) if flag_column else None
        funnel = funnel.loc[funnel["exclusion_reason"].ne(code).fillna(True)]
        record(step, before, funnel, note, flagged=flagged)

    low_conf = funnel["relevance_confidence"].eq("low").fillna(False)
    record("12 dataset analisis akhir", len(funnel), funnel,
           "flagged = relevansi berkeyakinan rendah (prioritas validasi).",
           flagged=int(low_conf.sum()))

    analysis_columns = [
        "video_id", "video_title", "channel_title", "video_published_at",
        "narrative_orientation", "narrative_orientation_source",
        "comment_id", "thread_id", "parent_id", "is_reply", "comment_type",
        "reply_position", "text_raw", "text_clean",
        "parent_text_clean", "parent_relevance_label",
        "published_at", "updated_at", "collected_at", "is_edited",
        "published_date_utc", "published_week_utc", "published_month_utc",
        "days_since_video_published", "like_count", "reported_reply_count",
        "char_count", "word_count", "emoji_count", "emoji_names", "intensified_count", "all_caps_comment", "has_url",
        "url_domains", "mention_count", "hashtags", "has_video_timestamp",
        "lang_label", "lang_detected", "lang_en_confidence", "lang_method",
        "lang_needs_review", "is_repeated_text", "duplicate_text_count",
        "repeated_text_rank", "is_spam", "spam_reasons", "spam_needs_review",
        "spam_review_reasons", "ai_terms", "work_terms", "claim_terms",
        "work_exclusion_phrases", "narrative_frame",
        *[f"frame_{name}" for name in FRAME_NAMES], "relevance_link", "relevance_label",
        "relevance_confidence", "in_relevant_thread", "is_relevant", "manual_override_applied",
    ]
    audit_columns = analysis_columns + [
        "text_normalized", "text_original", "text_display", "text_source", "is_empty_text",
        "has_non_reference_url", "has_phone_number", "spam_weak_signals",
        "manual_is_relevant", "include_in_analysis", "exclusion_reason", "source_file",
    ]

    table = table.sort_values(["published_at", "comment_id"], kind="stable").reset_index(drop=True)
    all_flagged = table[audit_columns].copy()
    analysis = table.loc[table["include_in_analysis"], analysis_columns].reset_index(drop=True)

    validation = build_validation_sample(table, args.sample_size, args.seed)

    distributions = {
        "lang_label": table["lang_label"].value_counts().to_dict(),
        "lang_method": table["lang_method"].value_counts().to_dict(),
        "lang_detected_top10": table["lang_detected"].value_counts().head(10).to_dict(),
        "spam_reasons": table.loc[table["is_spam"], "spam_reasons"]
            .str.split("; ").explode().value_counts().to_dict(),
        "relevance_label_all": table["relevance_label"].value_counts().to_dict(),
        "relevance_label_after_lang_spam": table.loc[
            table["lang_label"].eq("en") & ~table["is_spam"] & ~table["is_empty_text"],
            "relevance_label"].value_counts().to_dict(),
        "narrative_frame_in_analysis": {
            frame: int(analysis[f"frame_{frame}"].sum()) for frame in FRAME_NAMES},
        "relevance_confidence_in_analysis": analysis["relevance_confidence"]
            .value_counts(dropna=False).astype(int).rename(str).to_dict(),
        "replies_in_relevant_thread_without_keywords": int(table["in_relevant_thread"].sum()),
        "exclusion_reason": table["exclusion_reason"].value_counts().to_dict(),
        "analysis_by_month": analysis["published_month_utc"].value_counts().sort_index().to_dict(),
        "top_emoji_names": table["emoji_names"].str.split("; ").explode()
            .loc[lambda s: s.ne("")].value_counts().head(15).to_dict(),
    }

    weekly = (table.groupby(["published_week_utc", "comment_type", "include_in_analysis"])
              .size().reset_index(name="comment_count"))

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
    output_directory = (Path(args.output).resolve() if args.output
                        else PROCESSED_ROOT / f"cleaned_{args.video_id}_{run_id}")
    if output_directory.exists() and any(output_directory.iterdir()):
        raise ValueError("Folder output tidak kosong. Pilih folder baru.")
    output_directory.mkdir(parents=True, exist_ok=True)

    save_table(analysis, output_directory, "comments_analysis")
    save_table(all_flagged, output_directory, "comments_all_flagged")
    save_table(pd.DataFrame(steps), output_directory, "cleaning_report")
    save_table(weekly, output_directory, "weekly_counts")
    validation.to_csv(output_directory / "validation_sample.csv", index=False, encoding="utf-8-sig")

    rules = {
        "relevance_scope": args.relevance_scope,
        "relevance_labels_kept": sorted(allowed_labels),
        "include_thread_context": args.include_thread_context,
        "emoji": {
            "library": f"emoji {getattr(emoji, '__version__', '')}",
            "name_language": EMOJI_NAME_LANGUAGE,
            "format": "nama_emoji (snake_case) atau 'nama_emoji xN' untuk deretan identik; "
                      "nama dari basis data Unicode/CLDR library emoji; "
                      "modifier warna kulit dihapus dari nama",
        },
        "language": {
            "detector": "lingua-language-detector",
            "candidate_languages": "lingua ∩ wordfreq: " + ", ".join(
                language.name for language in candidate_languages()),
            "min_letters": MIN_LETTERS_FOR_LANGUAGE,
            "review_ratio": LANGUAGE_REVIEW_RATIO,
            "tokenizer": "wordfreq.tokenize",
            "word_frequency_model": {
                "library": "wordfreq",
                "rule": "en bila sum Zipf_en + log10 P(en) >= max_L (sum Zipf_L + log10 P(L))",
                "applies_to": f"tebakan lingua non-Inggris dengan huruf Latin > {LATIN_SHARE_MIN}",
                "prior_source": f"sebaran tebakan lingua pada komentar >= {PRIOR_MIN_TOKENS} token, "
                                "add-one smoothing",
                "review_margin": WORD_MODEL_REVIEW_MARGIN,
                "estimated_priors_top10": dict(sorted(
                    language_priors.items(), key=lambda kv: -kv[1])[:10]),
            },
        },
        "spam": {
            "strong_patterns": SPAM_STRONG_PATTERNS,
            "weak_patterns": SPAM_WEAK_PATTERNS,
            "phone_detection": f"phonenumbers (libphonenumber), leniency VALID, "
                               f"default region {PHONE_DEFAULT_REGION}; "
                               "setelah URL, mention, hashtag, dan timestamp dibuang",
            "url_detection": "urlextract (TLD IANA); domain: tldextract (Public Suffix List)",
            "reference_domains": list(REFERENCE_DOMAINS),
            "reference_suffix_labels": list(REFERENCE_SUFFIX_LABELS),
            "repeated_text_min_count": REPEATED_TEXT_MIN_COUNT,
            "repeated_text_min_words": REPEATED_TEXT_MIN_WORDS,
            "identical_text_policy": "ditandai (is_repeated_text, repeated_text_rank), tidak dihapus",
        },
        "relevance": {
            "frames_kept": sorted(selected_frames),
            "ai_terms": AI_TERMS, "ai_reference": AI_REFERENCE, "implicit_use": IMPLICIT_USE,
            "frames": FRAMES,
            "rules_file_sha256": sha256(Path(__file__).with_name("cleaning_rules.py")),
            "work_exclusion_phrases": WORK_EXCLUSION_PHRASES,
            "persona_role_words": PERSONA_ROLE_WORDS,
            "persona_people": context.get("people", []),
            "persona_aliases": context.get("persona_aliases", []),
            "persona_credential": PERSONA_CREDENTIAL.pattern,
            "claim_terms": CLAIM_TERMS,
            "label_rules": {
                "ai_work": "minimal satu bingkai: sinyal kuat, atau sinyal (kuat/lemah) dalam "
                           "kalimat yang sama dengan AI_REFERENCE, atau rujukan implisit "
                           "untuk use_at_work; frasa pengecoh dibuang dulu; kalimat "
                           "kredensial Ed/host diabaikan (kecuali replacement)",
                "ai_claim": "(CLAIM dan AI) atau >= 2 istilah CLAIM",
                "ai_general": "hanya AI",
                "none": "tidak ada petunjuk",
            },
            "confidence_rules": {
                "high": "sinyal pekerjaan dalam kalimat yang sama dengan rujukan AI",
                "low": "hanya sinyal kuat tanpa kata AI, atau rujukan implisit",
            },
        },
        "text_cleaning": [
            f"ftfy {getattr(ftfy, '__version__', '')}: perbaikan mojibake, kontrol, BOM, "
            "line break, ligatur, lebar karakter; NFC; kutip melengkung dan HTML dibiarkan",
            "hapus karakter format Unicode (Cf) di luar urutan emoji",
            "whitespace Unicode dirapikan dengan str.split(); baris kosong dibuang",
            "text_clean: URL dihapus (urlextract), timestamp video dihapus "
            f"(pola: {VIDEO_TIMESTAMP_REMOVAL.pattern}), mention -> {MENTION_PLACEHOLDER}, "
            "emoji -> nama snake_case dari library emoji (deretan identik: 'nama xN')",
            f"penekanan -> kata{INTENSIFIED_TAG} per kata: *tebal*/_miring_; kata KAPITAL "
            "menurut aturan VADER (allcap_differential; leksikon, BOOSTER_DICT, NEGATE) "
            f"diperluas ke kata Inggris umum (wordfreq Zipf >= {CAPS_WORD_MIN_ZIPF}) "
            f"kecuali akronim (porsi kapital korpus > {CAPS_ACRONYM_SHARE}) dan nama diri; "
            "huruf berulang ('soooo' -> 'so', via wordfreq). Komentar seluruhnya kapital: "
            "kolom all_caps_comment",
            "kapital (selain penekanan), tanda baca, negasi, slang, hashtag dipertahankan",
        ],
    }
    save_json(output_directory / "cleaning_rules.json", rules)

    summary = {
        "video_id": args.video_id,
        "stage": "processed",
        "cleaned_at": datetime.now(timezone.utc).isoformat(),
        "interim_session": interim_directory.name,
        "raw_entries": raw_entries,
        "unique_comments": int(len(table)),
        "analysis_rows": int(len(analysis)),
        "analysis_main": int((~analysis["is_reply"]).sum()),
        "analysis_replies": int(analysis["is_reply"].sum()),
        "rows_needing_language_review": int(table["lang_needs_review"].sum()),
        "rows_needing_spam_review": int(table["spam_needs_review"].sum()),
        "analysis_rows_low_relevance_confidence": int(low_conf.sum()),
        "text_changed_by_cleaning": changed,
        "rows_with_emoji": int(table["emoji_names"].ne("").sum()),
        "published_min_utc": str(analysis["published_at"].min()) if len(analysis) else None,
        "published_max_utc": str(analysis["published_at"].max()) if len(analysis) else None,
        "manual_overrides": override_report,
        "distributions": distributions,
        "notes": [
            "Keputusan bahasa, spam, dan relevansi berbasis aturan; validasi manual "
            "dilakukan melalui validation_sample.csv lalu dijalankan ulang dengan --overrides.",
            "Teks identik dari ID berbeda hanya ditandai (is_repeated_text, repeated_text_rank).",
            "text_clean: URL dan timestamp video dihapus, mention -> [User], emoji -> "
            "nama resmi Unicode/CLDR dari library emoji (makna literal, bukan slang). "
            "Teks asli tetap di text_raw.",
            "Orientasi narasi video berasal dari anotasi manual, bukan dari API.",
            "Data pengguna (nama, channel ID) tidak dikumpulkan maupun diekspor; "
            "handle @mention di dalam teks komentar tetap ada.",
        ],
    }
    save_json(output_directory / "summary.json", summary)

    save_json(output_directory / "manifest.json", {
        "cleaned_at": summary["cleaned_at"],
        "script_sha256": sha256(Path(__file__)),
        "rules_sha256": sha256(Path(__file__).with_name("cleaning_rules.py")),
        "arguments": vars(args),
        "interim_directory": str(interim_directory),
        "interim_files": input_files,
    })
    (output_directory / "SUCCESS").write_text("Cleaning completed.\n", encoding="utf-8")

    print("Dataset analisis berhasil dibuat.")
    print(f"Sumber interim : {interim_directory}")
    print(pd.DataFrame(steps)[["step", "rows_before", "rows_after", "removed"]].to_string(index=False))
    print(f"\nDataset analisis    : {len(analysis)} baris "
          f"({summary['analysis_main']} utama, {summary['analysis_replies']} balasan)")
    print(f"Relevansi low conf. : {summary['analysis_rows_low_relevance_confidence']}")
    print(f"Perlu tinjau bahasa : {summary['rows_needing_language_review']}")
    print(f"Perlu tinjau spam   : {summary['rows_needing_spam_review']}")
    print(f"Folder hasil        : {output_directory}")

def build_validation_sample(table, size, seed):
    strata = [
        ("lang_non_en", table["lang_label"].eq("non_en")),
        ("lang_und", table["lang_label"].eq("und")),
        ("lang_word_model_to_en", table["lang_method"].eq("word_frequency_model")),
        ("lang_needs_review", table["lang_needs_review"]),
        ("spam_auto", table["is_spam"]),
        ("spam_needs_review", table["spam_needs_review"]),
        *[(f"ai_work_{name}", table[f"frame_{name}"]) for name in FRAME_NAMES],
        ("ai_work_low_confidence", table["relevance_label"].eq("ai_work")
         & table["relevance_confidence"].eq("low").fillna(False)),
        ("relevance_ai_claim", table["relevance_label"].eq("ai_claim")),
        ("relevance_ai_general", table["relevance_label"].eq("ai_general")),
        ("relevance_none", table["relevance_label"].eq("none")),
        ("reply_in_relevant_thread", table["in_relevant_thread"]),
    ]
    used, parts = set(), []
    for name, mask in strata:
        candidates = table.loc[mask & ~table["comment_id"].isin(used) & ~table["is_empty_text"]]
        sample = candidates.sample(n=min(size, len(candidates)), random_state=seed)
        used.update(sample["comment_id"])
        parts.append(sample.assign(stratum=name))

    sample = pd.concat(parts, ignore_index=True)
    columns = [
        "stratum", "comment_id", "is_reply", "text_clean",
        "parent_text_clean", "lang_label", "lang_detected", "lang_method",
        "is_spam", "spam_reasons", "spam_review_reasons", "relevance_label",
        "narrative_frame", "relevance_confidence", "ai_terms", "work_terms",
        "claim_terms", "is_relevant",
    ]
    sample = sample[columns].copy()
    for column in ["manual_language", "manual_is_spam", "manual_is_relevant",
                   "manual_narrative_frame", "reviewer_note"]:
        sample[column] = ""
    return sample

def main():
    parser = argparse.ArgumentParser(
        description="Cleaning dan transformasi komentar YouTube (data/interim -> data/processed)."
    )
    parser.add_argument("--video-id", default=default_video_id(),
                        help="ID video (default: YOUTUBE_VIDEO_ID di .env).")
    parser.add_argument("--interim-session",
                        help="Nama/path folder interim dari script 04 (default: sesi terbaru).")
    parser.add_argument("--output", help="Folder output baru atau kosong.")
    parser.add_argument("--relevance-scope", choices=["work", "work_and_claims"], default="work",
                        help="work: hanya komentar AI dan pekerjaan; "
                             "work_and_claims: ditambah kritik/klaim industri AI.")
    parser.add_argument("--frames", nargs="+", choices=list(FRAME_NAMES),
                        default=list(FRAME_NAMES),
                        help="Bingkai AI-dan-pekerjaan yang dipertahankan "
                             "(default: semua bingkai).")
    parser.add_argument("--people", nargs="+",
                        help='Nama orang di video, mis. --people "Nama Tamu" "Nama Host". '
                             "Menimpa VIDEO_CONTEXT dan video_context.json.")
    parser.add_argument("--include-thread-context", action="store_true",
                        help="Ikutkan balasan tanpa kata kunci pada thread yang induknya relevan.")
    parser.add_argument("--overrides", help="CSV hasil validasi manual (format validation_sample.csv).")
    parser.add_argument("--sample-size", type=int, default=30, help="Sampel validasi per strata.")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    if not args.video_id:
        parser.error("isi --video-id atau YOUTUBE_VIDEO_ID di .env")

    try:
        run(args)
    except (OSError, ValueError, KeyError, TypeError, ImportError) as error:
        print(f"Cleaning gagal: {error}")
        return 1
    return 0

if __name__ == "__main__":
    raise SystemExit(main())