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

import json
import os
import re
import difflib
import subprocess
import sys
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MOVIE_DIR = os.path.join(BASE_DIR, "25_yan_lu")
SAMPLE15M_PATH = os.path.join(MOVIE_DIR, "sample15m_cues.json")
RAW_VISUAL_PATH = os.path.join(MOVIE_DIR, "full_visual_cues_raw.json")
CACHE_DIR = os.path.join(MOVIE_DIR, "temp", "scene_cache")
MASTER_OUT_PATH = os.path.join(MOVIE_DIR, "all_cues_master.json")

os.makedirs(CACHE_DIR, exist_ok=True)

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

def translate_batch(batch_cues, batch_idx, total_batches):
    cache_file = os.path.join(CACHE_DIR, f"batch_{batch_idx:04d}.json")
    if os.path.exists(cache_file) and os.path.getsize(cache_file) > 100:
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                cached = json.load(f)
            if len(cached) == len(batch_cues):
                print(f"[{batch_idx}/{total_batches}] Loaded from cache ({len(cached)} cues).")
                return cached
        except Exception:
            pass

    minimal_input = [{"id": c["id"], "chinese": c["chinese"]} for c in batch_cues]
    prompt = f"{DRAMA_INSTRUCTIONS}\n\nCues:\n{json.dumps(minimal_input, ensure_ascii=False)}"
    print(f"[{batch_idx}/{total_batches}] Translating scene ({len(batch_cues)} cues: IDs {batch_cues[0]['id']}..{batch_cues[-1]['id']})...")

    cmd = [
        'agy',
        '--model', 'gemini-3.8-flash-low',
        '--disable-slash-commands',
        '--dangerously-skip-permissions',
        '--print',
        prompt
    ]
    for attempt in range(3):
        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=90)
            data = extract_json_from_output(res.stdout)
            if data and len(data) == len(batch_cues):
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
                        "speaker": trans.get("speaker", "Yan Jin"),
                        "voice": v,
                        "pitch": trans.get("pitch", "-4Hz"),
                        "rate": trans.get("rate", "+10%"),
                        "sub_start": orig["start"],
                        "sub_end": orig["end"],
                        "speech_start": max(0.0, round(orig["start"] - 0.15, 2)),
                        "speech_end": round(orig["end"] + 0.1, 2)
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
    with open(SAMPLE15M_PATH, "r", encoding="utf-8") as f:
        verified_15m = json.load(f)
    print(f"[+] Loaded {len(verified_15m)} verified cues up to {verified_15m[-1]['end']}s.")

    # 2. Ingest raw visual cues after 896.75s, requiring at least 2 Chinese characters
    with open(RAW_VISUAL_PATH, "r", encoding="utf-8") as f:
        raw_cues = json.load(f)

    post_900 = [c for c in raw_cues if c["start"] >= 896.75 and len(re.findall(r'[\u4e00-\u9fff]', c.get('chinese', ''))) >= 2]

    # Smart deduplication of OCR jitter
    merged = []
    for c in post_900:
        zh = c["chinese"].strip()
        norm = re.sub(r'[\s，。！？“”"\'\-—]+', '', zh)
        if merged:
            last = merged[-1]
            last_norm = re.sub(r'[\s，。！？“”"\'\-—]+', '', last["chinese"])
            sim = difflib.SequenceMatcher(None, norm, last_norm).ratio()
            gap = c["start"] - last["end"]
            if (sim > 0.6 or norm in last_norm or last_norm in norm) and gap < 1.8:
                last["end"] = max(last["end"], c["end"])
                if len(zh) > len(last["chinese"]):
                    last["chinese"] = zh
                continue
        merged.append({
            "start": round(c["start"], 2),
            "end": round(c["end"], 2),
            "duration": round(c["end"] - c["start"], 2),
            "chinese": zh
        })

    # Smart sentence rejoining of broken fragments
    sentences = []
    for m in merged:
        zh = m["chinese"].strip()
        if sentences:
            last = sentences[-1]
            last_zh = last["chinese"]
            gap = m["start"] - last["end"]
            if gap < 0.6 and not re.search(r'[。！？?!]$', last_zh) and (len(last_zh) + len(zh)) <= 22:
                last["end"] = m["end"]
                last["duration"] = round(last["end"] - last["start"], 2)
                last["chinese"] = f"{last_zh} {zh}"
                continue
        sentences.append(dict(m))

    for idx, s in enumerate(sentences, len(verified_15m) + 1):
        s["id"] = idx

    print(f"[+] Consolidated {len(raw_cues)} raw visual frames into {len(sentences)} natural full sentences (896s to {sentences[-1]['end']}s).", flush=True)

    # 3. Batch into scene blocks of 10 cues
    BATCH_SIZE = 10
    batches = [sentences[i:i + BATCH_SIZE] for i in range(0, len(sentences), BATCH_SIZE)]
    print(f"[*] Total scene batches to translate: {len(batches)} (Workers=3 concurrent)", flush=True)

    from concurrent.futures import ThreadPoolExecutor
    def process_indexed_batch(item):
        idx, b = item
        return idx, translate_batch(b, idx, len(batches))

    indexed_batches = list(enumerate(batches, 1))
    batch_results = {}
    with ThreadPoolExecutor(max_workers=3) as executor:
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

    with open(MASTER_OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(master_cues, f, ensure_ascii=False, indent=2)

    print(f"\n🎉 SUCCESS: Wrote {len(master_cues)} authentic drama cues to {MASTER_OUT_PATH}!")

if __name__ == "__main__":
    main()
