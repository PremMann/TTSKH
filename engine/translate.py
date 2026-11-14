#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_movie25_authentic.py
Rebuilds the entire 2-hour-07-minute master dialogue for Movie 25:
«Lawyer Yan, Your First Love Has Returned» (宴律，你的白月光回国了)
Strictly adheres to the 5-Stage Khmer CDrama Production Checklist:
1. Ingests first 142 curated cues (0 to 896s).
2. Filters non-spoken on-screen text, deduplicates OCR jitter, and rejoins split dialogue fragments.
3. Translates using `agy --dangerously-skip-permissions --print` in 10-cue scene batches.
4. Enforces 100% natural colloquial drama dubbing dialogue and authentic character casting.
5. Caches each scene batch to `25_yan_lu/temp/scene_cache/` for instant resumption.
6. Writes final master cues to `25_yan_lu/all_cues_master.json`.
"""

import hashlib
import json
import os
import re
import difflib
import subprocess
import sys
import time
if sys.platform == 'darwin':
    _extra = ['/Applications/Gemini.app/Contents/Helpers', os.path.expanduser('~/.local/bin'), '/opt/homebrew/bin', '/usr/local/bin']
elif os.name == 'nt':
    _extra = [os.path.join(os.environ.get('LOCALAPPDATA', os.path.expanduser('~\\AppData\\Local')), 'agy', 'bin')]
else:
    _extra = [os.path.expanduser('~/.local/bin')]
os.environ['PATH'] = os.pathsep.join([p for p in _extra if os.path.isdir(p)] + [os.environ.get('PATH', '')])


def agy_command():
    """Full path of agy (on Windows it may be agy.exe or an agy.cmd shim)."""
    import shutil
    return shutil.which('agy') or 'agy'

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MOVIE_DIR = os.path.join(BASE_DIR, "25_yan_lu")
SAMPLE15M_PATH = os.path.join(MOVIE_DIR, "sample15m_cues.json")
RAW_VISUAL_PATH = os.path.join(MOVIE_DIR, "full_visual_cues_raw.json")
CACHE_DIR = os.path.join(MOVIE_DIR, "temp", "scene_cache")
MASTER_OUT_PATH = os.path.join(MOVIE_DIR, "all_cues_master.json")



MODEL = "gemini-3.8-flash-low"

DRAMA_INSTRUCTIONS = """Translate these Chinese CDrama sentences into natural colloquial Cambodian drama dubbing dialogue (ភាសានិយាយរឿងភាគធម្មជាតិ).
Drama: 《宴律，你的白月光回国了》 (Lawyer Yan, Your First Love Has Returned)
Main Characters:
- Yan Jin (宴律 / 宴谨 / 宴先生): Elite defense lawyer, authoritative, calm, deeply protective of Xingwan.
  -> Voice: km-KH-PisethNeural, pitch: -4Hz, rate: +10%
- Gu Xingwan (顾星晚 / 顾律师): Former top lawyer who served prison time to protect family. Proud, wounded, dignified.
  -> Voice: km-KH-SreymomNeural, pitch: +0Hz, rate: +12%
- Xia Meng (夏梦 / 夏小姐): Wealthy antagonist, arrogant, jealous rival trying to marry Yan Jin.
  -> Voice: km-KH-SreymomNeural, pitch: +2Hz, rate: +12%
- Shi Yue (施悦): Xingwan's loyal, warm female best friend.
  -> Voice: km-KH-SreymomNeural, pitch: +2Hz, rate: +12%
- Jingxi (景熙 / 顾景熙): Xingwan's young sweet child.
  -> Voice: km-KH-SreymomNeural, pitch: +6Hz, rate: +15%
- Lu Yiqing / Colleague / Assistant: Law firm colleague.
  -> If female: SreymomNeural (+2Hz, +14%). If male: PisethNeural (+1Hz, +12%)
- Judge / Presiding Judge (审判长 / 法官): Formal legal authority in courtroom.
  -> Voice: km-KH-PisethNeural, pitch: -2Hz, rate: +8%

RULES:
1. Translate into authentic spoken Khmer drama dialogue (colloquial, emotional, punchy). Never literal word-for-word translation.
2. Honorifics: Gu Xingwan calls him 'លោកមេធាវី អៀន' or 'លោក', Yan Jin calls her 'នាង' or 'ស៊ីងវ៉ាន់'.
3. CONSECUTIVE LINE INTEGRITY: If a character speaks multiple sentences in a row, ALL of those sentences MUST keep that character's name, gender, and voice! Never alternate blindly!
4. Return ONLY a valid JSON array of objects with keys: id, speaker, voice, pitch, rate, khmer_spoken, khmer_sub.
5. No markdown backticks, no explanatory prose."""

KHMER_CHARS_PER_SECOND = 13   # Edge TTS Khmer voices speak about 12-14 characters per second


def max_khmer_chars(seconds):
    """Longest Khmer line (spaces not counted) that the voice can say in `seconds` without speed-up."""
    return max(8, int(round(seconds * KHMER_CHARS_PER_SECOND)))


def extract_json_from_output(raw_text: str):
    raw_text = raw_text.strip()
    start = raw_text.find('[')
    end = raw_text.rfind(']')
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(raw_text[start:end+1])
        except Exception:
            pass
    return None

def translate_batch(batch_cues, batch_idx, total_batches, context=None):
    cache_file = os.path.join(CACHE_DIR, f"batch_{batch_idx:04d}_{hashlib.sha256(json.dumps([DRAMA_INSTRUCTIONS, batch_cues, MODEL, context], sort_keys=True).encode()).hexdigest()[:16]}.json")
    if os.path.exists(cache_file) and os.path.getsize(cache_file) > 100:
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                cached = json.load(f)
            if isinstance(cached,list) and [c.get("id") for c in cached] == [c["id"] for c in batch_cues]:
                print(f"[{batch_idx}/{total_batches}] Loaded from cache ({len(cached)} cues).")
                return cached
        except Exception:
            pass

    minimal_input = [{"id": c["id"], "chinese": c["chinese"], "seconds": round(c["end"] - c["start"], 2),
                      "max_khmer_chars": max_khmer_chars(c["end"] - c["start"])} for c in batch_cues]
    prompt = (f"{DRAMA_INSTRUCTIONS}\nClassify each entry: add is_spoken_dialogue=false for signs, credits, or other unspoken screen text; use empty khmer_spoken but translate khmer_sub. Keep brief one-character spoken replies. If speaker is uncertain use Unknown; do not invent certainty.\n"
              f"Each entry is ONE subtitle line from the screen; different lines may be different speakers, so decide the speaker of every line separately and never move words between lines.\n"
              f"TIMING: the Khmer voice must fit the time the Chinese line is on screen (\"seconds\"). Keep khmer_spoken within max_khmer_chars Khmer characters (spaces not counted): use short natural spoken wording, drop filler words and repeated names, keep the meaning and emotion. khmer_sub may be slightly fuller but no more than 1.3x that length.\n\n"
              f"Context (do not translate these again): {json.dumps(context or [], ensure_ascii=False)}\n\nCues:\n{json.dumps(minimal_input, ensure_ascii=False)}")
    print(f"[{batch_idx}/{total_batches}] Translating scene ({len(batch_cues)} cues: IDs {batch_cues[0]['id']}..{batch_cues[-1]['id']})...")

    cmd = [
        agy_command(),
        '--model', MODEL,
        '--disable-slash-commands',
        '--print',
        prompt
    ]
    for attempt in range(3):
        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace', timeout=90)
            res.check_returncode()
            data = extract_json_from_output(res.stdout)
            if data and len(data) == len(batch_cues) and [d.get("id") for d in data] == [c["id"] for c in batch_cues] and all(d.get("is_spoken_dialogue") is False or (d.get("khmer_spoken", "").strip() and d.get("speaker", "").strip() and d.get("voice") in ("km-KH-PisethNeural", "km-KH-SreymomNeural")) for d in data):
                result = []
                for orig, trans in zip(batch_cues, data):
                    v = trans.get("voice", "km-KH-PisethNeural")
                    if v and not v.startswith("km-KH-"):
                        v = f"km-KH-{v}"
                    item = {
                        "id": orig["id"],
                        "start": orig["start"],
                        "end": orig["end"],
                        "duration": orig["duration"],
                        "chinese": orig["chinese"],
                        "khmer_sub": trans.get("khmer_sub", trans.get("khmer_spoken", "")),
                        "khmer_spoken": trans.get("khmer_spoken", trans.get("khmer_sub", "")),
                        "speaker": trans.get("speaker", "Pei Yi"),
                        "voice": v,
                        "pitch": trans.get("pitch", "+0Hz"),
                        "rate": trans.get("rate", "+10%"),
                        "sub_start": orig["start"],
                        "sub_end": orig["end"],
                        "speech_start": orig["start"],
                        "speech_end": orig["end"],
                        "speaker_reviewed": False,
                        "is_spoken_dialogue": trans.get("is_spoken_dialogue", True),
                        "original_ids": orig.get("original_ids", [orig["id"]])
                    }
                    result.append(item)
                with open(cache_file, "w", encoding="utf-8") as f:
                    json.dump(result, f, ensure_ascii=False, indent=2)
                print(f"  [+] Saved batch {batch_idx} ({len(result)} cues).", flush=True)
                return result
            else:
                print(f"  [Attempt {attempt+1}] Parse mismatch (expected {len(batch_cues)}, got {len(data) if data else 0}). Retrying...", flush=True)
                time.sleep(2)
        except Exception as e:
            print(f"  [Attempt {attempt+1}] Error: {e}. Retrying...", flush=True)
            time.sleep(2)

    print(f"  [!] Failed batch {batch_idx} after 3 attempts.", flush=True)
    return None

def main():
    print("=" * 60)
    print("🚀 PRODUCING AUTHENTIC MOVIE 25 MASTER CUES (Movie 25)")
    print("=" * 60)

    # 1. Load verified 15-minute cues (1 to 142)
    os.makedirs(CACHE_DIR, exist_ok=True)
    verified_15m = json.load(open(SAMPLE15M_PATH, encoding='utf-8')) if SAMPLE15M_PATH else []
    cutoff = max((c["end"] for c in verified_15m), default=0)
    print(f"Loaded {len(verified_15m)} curated cues; continuing from {cutoff}s")

    # Deduplicate OCR jitter and rejoin broken fragments into natural spoken turns
    with open(RAW_VISUAL_PATH, encoding='utf-8') as handle:
        raw_cues = json.load(handle)
    valid_cues = [c for c in raw_cues if c.get('end', 0) > cutoff and re.search(r'[\u4e00-\u9fff]', c.get('chinese', ''))]

    # Step A: merge OCR repeats only: the same line read twice (one or two characters misread),
    # or a single-frame partial read next to the full line. Real short replies stay separate.
    merged = []
    for c in valid_cues:
        zh = c.get('chinese', '').strip()
        norm = re.sub(r'[^\w\u4e00-\u9fff]+', '', zh)
        if not norm:
            continue
        if merged:
            last = merged[-1]
            last_norm = re.sub(r'[^\w\u4e00-\u9fff]+', '', last['chinese'])
            sim = difflib.SequenceMatcher(None, norm, last_norm).ratio()
            gap = c['start'] - last['end']
            blip = min(c['end'] - c['start'], last['duration']) <= 0.3
            if gap < 0.3 and (sim >= 0.85 or (blip and (norm in last_norm or last_norm in norm))):
                last['end'] = max(last['end'], c['end'])
                last['duration'] = round(last['end'] - last['start'], 2)
                if len(zh) > len(last['chinese']):
                    last['chinese'] = zh
                last['original_ids'].append(c.get('id', 0))
                continue
        merged.append({
            'start': round(c['start'], 2),
            'end': round(c['end'], 2),
            'duration': round(c['end'] - c['start'], 2),
            'chinese': zh,
            'original_ids': [c.get('id', 0)]
        })

    # Each subtitle line stays its own cue. Joining lines into sentences merged two speakers
    # into one voice; Gemini gets the neighbouring lines as context instead.
    sentences = [dict(m) for m in merged]

    for idx, s in enumerate(sentences, len(verified_15m) + 1):
        s["id"] = idx

    print(f"[+] Consolidated {len(raw_cues)} raw visual frames into {len(sentences)} natural spoken sentences after {cutoff}s.", flush=True)

    # 3. Batch into scene blocks of 10 cues
    BATCH_SIZE = 10
    batches = [sentences[i:i + BATCH_SIZE] for i in range(0, len(sentences), BATCH_SIZE)]
    print(f"[*] Total scene batches to translate: {len(batches)} (Workers=3 concurrent)", flush=True)

    from concurrent.futures import ThreadPoolExecutor
    def process_indexed_batch(item):
        idx, b = item
        offset = (idx - 1) * BATCH_SIZE
        context = [{"chinese": c["chinese"]} for c in sentences[max(0, offset-5):offset]] + [{"chinese": c["chinese"]} for c in sentences[offset+len(b):offset+len(b)+3]]
        return idx, translate_batch(b, idx, len(batches), context)

    indexed_batches = list(enumerate(batches, 1))
    batch_results = {}
    with ThreadPoolExecutor(max_workers=8) as executor:
        for idx, res in executor.map(process_indexed_batch, indexed_batches):
            if not res:
                print(f"[CRITICAL ERROR] Batch {idx} failed. Aborting.", flush=True)
                sys.exit(1)
            batch_results[idx] = res

    all_post_900 = []
    for idx in range(1, len(batches) + 1):
        all_post_900.extend(batch_results[idx])

    # 4. Combine into final master cues
    master_cues = verified_15m + all_post_900
    for idx, c in enumerate(master_cues, 1):
        c["id"] = idx

    with open(MASTER_OUT_PATH + ".pending", "w", encoding="utf-8") as f:
        json.dump(master_cues, f, ensure_ascii=False, indent=2)

    os.replace(MASTER_OUT_PATH + ".pending", MASTER_OUT_PATH)

    print(f"\n🎉 SUCCESS: Wrote {len(master_cues)} authentic drama cues to {MASTER_OUT_PATH}!")

if __name__ == "__main__":
    main()
