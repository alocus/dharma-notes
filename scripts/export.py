"""Snapshot the channels listed in site.config.json from mani into this site.

Reads ../mani (never writes there) and writes:
  content/site.json                    site title + channels -> series -> lessons
  content/notes/<ch>/<s>/<NN>.md       note body in the public voice (scripts/public_voice.py)
  content/lessons/<ch>/<s>/<NN>.json   verified quotes, related talks, the talk's main names
  content/sutras.json                  CBETA id -> title, quoting/citing talks; 《name》 -> id
  content/entities.json                名相 / 人物 / 地名 -> gloss + talks that mention them
  public/data/<ch>/<s>/<NN>.json       transcript lines + line times (build + lazy popover)

Everything published is derived from the notes, their transcripts and verified
quotes, plus mani's entity dictionary and 丁福保《佛學大辭典》 glosses. mani's
private insight graph (insight_edges, 圖譜.json) is never read.

Run with mani's venv (it needs PyYAML and mani's lesson_key):
  ../mani/pipelines/knowledgebase/.venv/bin/python scripts/export.py
"""
import argparse
import csv
import json
import math
import re
import shutil
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

import yaml

SITE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import public_voice  # noqa: E402

CONTENT = SITE / "content"
PUBLIC_DATA = SITE / "public" / "data"

FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
BULLET_RE = re.compile(r"^-\s+\*\*(講師|講者|本經|本講範圍|影片)\*\*\s*[:：]\s*(.*)$")
VIDEO_ID_RE = re.compile(r"(?:[?&]v=|youtu\.be/|/embed/)([A-Za-z0-9_-]{11})")
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
DUR_RE = re.compile(r"時長\s*([\d:]+)")
HDR_RE = {k: re.compile(rf"^-\s+\*\*{k}\*\*\s*[:：]\s*(\S+)", re.MULTILINE)
          for k in ("上傳日期", "時長", "連結")}
WIKILINK_RE = re.compile(r"\[\[([^\]|]+?)(?:\\?\|([^\]]+))?\]\]")
CBETA_ID_RE = re.compile(r"\b([TXBJ]\d{4}[A-Z]?)\b")
SUTRA_RE = re.compile(r"《([^《》\n]{1,24})》")
SUTRA_ID_RE = re.compile(r"《([^《》\n]{1,24})》\s*([TXBJ]\d{4}[A-Z]?)")
PERSON_RE = re.compile(r"〔([^〕\n\d行][^〕\n]{0,11})〕")
PLACE_RE = re.compile(r"［([^］\n]{1,16})］")
PUNCT_RE = re.compile(r"[\s，。、；：「」『』！？（）()《》〈〉…—・·,.;:!?\"'\-*]+")
CJK_NAME_RE = re.compile(r"^[㐀-鿿]{2,8}$")
HONORIFIC_RE = re.compile(r"(?:法師|禪師|大師|國師|和尚|上人|居士|尊者|菩薩|祖師|導師|老人)$")

ENTITY_TYPES = {"concept": "名相", "person": "人物", "teacher": "人物", "location": "地名"}


def slugify(name: str) -> str:
    s = re.sub(r"[\s()（）/\\?#%]+", "-", name).strip("-")
    return re.sub(r"-{2,}", "-", s)


def nn(no: str) -> str:
    return no.zfill(2)


def read_header(text: str) -> dict:
    """上傳日期 / 時長 / 連結 bullets of a transcript header."""
    head = "\n".join(text.splitlines()[:30])
    return {k: m.group(1) for k, rx in HDR_RE.items() if (m := rx.search(head))}


def split_note(text: str):
    """(frontmatter, header bullets, body) of a 學習筆記.md: H1 and header bullets removed."""
    meta, body = {}, text
    m = FRONTMATTER_RE.match(text)
    if m:
        meta = yaml.safe_load(m.group(1)) or {}
        body = text[m.end():]
    lines, bullets, i = body.splitlines(), {}, 0
    while i < len(lines) and (not lines[i].strip() or lines[i].startswith("# ")):
        i += 1
    while i < len(lines) and (bm := BULLET_RE.match(lines[i])):
        bullets[bm.group(1)] = bm.group(2).strip()
        i += 1
    while i < len(lines) and lines[i].strip() in ("", "---"):
        i += 1
    if "講者" in bullets and "講師" not in bullets:
        bullets["講師"] = bullets["講者"]
    return meta, bullets, "\n".join(lines[i:]).rstrip() + "\n"


def teacher_short(teacher: str | None) -> str | None:
    return re.split(r"[（(；;，,]", teacher)[0].strip() if teacher else None


def short_title(title: str, strip: list[str]) -> str:
    t = title or ""
    for s in strip:
        if s:
            t = re.sub(r"^\s*" + re.escape(s) + r"\s*", "", t)
    return re.sub(r"\s*學習筆記$", "", t).strip(" —-")


def line_times(lesson_key, final: Path, sidecar: Path | None) -> dict:
    """{line: [start_sec, interpolated 0/1]} from the timing map, gaps filled by the
    note's 時間軸 sidecar (which also times cited lines the map skipped)."""
    out = {}
    tmap = lesson_key.timing_map_file(final)
    if tmap:
        for k, v in (json.loads(tmap.read_text(encoding="utf-8")).get("lines") or {}).items():
            if v.get("start") is not None:
                out[int(k)] = [round(v["start"]), 0 if v.get("confidence") == "matched" else 1]
    if sidecar:
        for k, v in (json.loads(sidecar.read_text(encoding="utf-8")).get("lines") or {}).items():
            if v.get("start") is not None and int(k) not in out:
                out[int(k)] = [round(v["start"]), 0 if v.get("confidence") in ("matched", "measured") else 1]
    return {str(k): out[k] for k in sorted(out)}


# 校對 sidecars are agent-typed and their quote keys drift; normalize the common ones
_TEXT_KEYS = ("text", "quote", "q", "frag")
_ATTR_KEYS = ("attrib", "attributed", "attr", "claimed", "claim", "claimed_source",
              "cited_source", "sutra", "src", "source", "labeled")
_VERDICT_KEYS = ("verify", "status", "verdict", "result", "flag", "mark")


def normalize_quote(q) -> dict | None:
    """A verified quote as {text, attrib, cbeta, line}; anything else is not published."""
    if not isinstance(q, dict):
        return None
    text = next((q[k] for k in _TEXT_KEYS if isinstance(q.get(k), str) and q[k].strip()), None)
    if not text:
        return None
    verdict = " ".join(str(q[k]) for k in _VERDICT_KEYS if q.get(k) is not None)
    if not verdict.upper().startswith("VERIFIED") and "✓" not in verdict:
        return None
    cb = q.get("cbeta")
    if not (isinstance(cb, str) and CBETA_ID_RE.fullmatch(cb.strip())):
        m = CBETA_ID_RE.search(" ".join(str(q.get(k) or "") for k in ("cbeta", "ref", "verify")))
        cb = m.group(1) if m else None
    attrib = next((q[k] for k in _ATTR_KEYS if isinstance(q.get(k), str) and q[k].strip()), "")
    line = q.get("line")
    if not isinstance(line, int):
        m = re.search(r"\d+", str(line or q.get("lines") or ""))
        line = int(m.group(0)) if m else None
    return {"text": text.strip(), "attrib": public_voice.apply(attrib).strip(), "cbeta": cb, "line": line}


def cbeta_meta(mani: Path, cid: str, cache: dict) -> dict:
    """{title, by} from the CBETA file's frontmatter (first lines only)."""
    if cid not in cache:
        out = {"title": None, "by": None}
        f = mani / "reference" / "cbeta" / re.match(r"[A-Z]+", cid).group(0) / f"{cid}.md"
        if f.exists():
            with f.open(encoding="utf-8") as fh:
                for _, line in zip(range(20), fh):
                    if line.startswith("title_zh:"):
                        out["title"] = line.split(":", 1)[1].strip()
                    elif line.startswith("translator:"):
                        out["by"] = line.split(":", 1)[1].strip() or None
        cache[cid] = out
    return cache[cid]


def clean_sutra_name(name: str) -> str:
    """《維摩詰所說經·文殊師利問疾品》 -> 維摩詰所說經."""
    return re.split(r"[·・〈]", name)[0].strip()


# ---------------------------------------------------------------- per channel

def export_channel(ch: str, mani: Path, lesson_key, lessons: dict) -> dict:
    notes_root = mani / "notes" / ch
    art_root = mani / "notes-artifacts" / ch
    out_root = mani / "outputs" / ch
    raw_root = mani / "data" / "transcripts" / ch
    ch_slug = slugify(ch)
    channel = {"slug": ch_slug, "name": ch, "teacher": None, "series": []}
    teachers = Counter()

    playlists = sorted({p.name for root in (notes_root, out_root, raw_root) if root.is_dir()
                        for p in root.iterdir() if p.is_dir() and not p.name.startswith("_")})
    for pl in playlists:
        s = {"slug": slugify(pl), "name": pl, "teacher": None,
             "home_sutra": None, "home_sutra_id": None, "lessons": []}
        index = {}
        # 1. notes
        for f in sorted((notes_root / pl).glob(f"*{lesson_key.NOTE_SUFFIX}")):
            no = lesson_key.lesson_no(f.name)
            if not no:
                print(f"  skip (no lesson number): {f.name}", file=sys.stderr)
                continue
            meta, bullets, body = split_note(f.read_text(encoding="utf-8"))
            video = bullets.get("影片", "")
            vm, dm, durm = VIDEO_ID_RE.search(video), DATE_RE.search(video), DUR_RE.search(video)
            s["teacher"] = s["teacher"] or bullets.get("講師") or meta.get("teacher")
            s["home_sutra"] = s["home_sutra"] or bullets.get("本經")
            s["home_sutra_id"] = s["home_sutra_id"] or meta.get("home_sutra")
            index[nn(no)] = {
                "no": nn(no), "title": meta.get("title") or f.stem,
                "scope": public_voice.apply(bullets.get("本講範圍", "")).strip(),
                "has_note": True, "has_transcript": False,
                "video_id": vm.group(1) if vm else None,
                "date": dm.group(0) if dm else None, "duration": durm.group(1) if durm else None,
                "_note": f, "_meta": meta, "_body": public_voice.apply(body), "_pl": pl,
            }
        # 2. cleaned transcripts
        for f in sorted((out_root / pl / "1-pre-processed").glob("*-5-final.md")):
            no = lesson_key.lesson_no(f.name)
            if not no:
                continue
            e = index.setdefault(nn(no), {"no": nn(no), "title": lesson_key.final_stem(f),
                                          "scope": "", "has_note": False, "_pl": pl})
            e["has_transcript"], e["_final"], e["raw"] = True, f, False
        # 3. raw OCR transcripts for talks with no cleaned one
        raws = sorted((raw_root / pl).glob("*.md"))
        for f in raws:
            # a single-talk playlist may carry no number at all
            no = lesson_key.lesson_no(f.name) or ("01" if len(raws) == 1 and not index else None)
            if not no or nn(no) in index:
                continue
            index[nn(no)] = {"no": nn(no), "title": f.stem, "scope": "", "has_note": False,
                             "has_transcript": True, "_final": f, "raw": True, "_pl": pl}
        # a series is published once it has notes; transcript-only ones wait
        if not any(e["has_note"] for e in index.values()):
            continue

        tshort = teacher_short(s["teacher"])
        if tshort:
            teachers[s["teacher"]] += len(index)
        for no in sorted(index, key=int):
            e = index[no]
            e["title"] = short_title(e["title"], [ch, tshort or ""])
            key = f"{ch_slug}/{s['slug']}/{no}"
            final = e.get("_final")
            if final:
                text = final.read_text(encoding="utf-8")
                hdr = read_header(text)
                vm = VIDEO_ID_RE.search(hdr.get("連結", ""))
                e["video_id"] = e.get("video_id") or (vm.group(1) if vm else None)
                e["date"] = e.get("date") or hdr.get("上傳日期")
                e["duration"] = e.get("duration") or hdr.get("時長")
                sidecar = lesson_key.find_lesson_file(art_root / pl, "*時間軸.json", no)
                data = {"lines": text.splitlines(),
                        "t": {} if e.get("raw") else line_times(lesson_key, final, sidecar)}
                p = PUBLIC_DATA / f"{key}.json"
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
            e["_art"] = art_root / pl
            lessons[key] = e
            s["lessons"].append({k: v for k, v in e.items() if not k.startswith("_")})
        channel["series"].append(s)

    channel["teacher"] = teachers.most_common(1)[0][0] if teachers else None
    channel["series"].sort(key=lambda s: (-sum(l["has_note"] for l in s["lessons"]), s["name"]))
    return channel


# ---------------------------------------------------------------- entities

def load_dictionary(mani: Path) -> tuple[dict, dict]:
    """(name -> 名相/人物/地名, name -> 丁福保 gloss) from catalog.db, read-only."""
    db = mani / "outputs" / "kb" / "catalog.db"
    if not db.exists():
        return {}, {}
    conn = sqlite3.connect(f"file:{db}?mode=ro&immutable=1", uri=True)
    names, glosses = {}, {}
    # a name typed several ways: person > place > concept; a sutra title is never a name
    rank = {"人物": 0, "地名": 1, "名相": 2}
    sutra_titles = {n.strip() for (n,) in conn.execute("SELECT name FROM entities WHERE type='sutra'")}
    for eid, ty, name in conn.execute("SELECT id, type, name FROM entities WHERE type IN (?,?,?,?)",
                                      tuple(ENTITY_TYPES)):
        name, label = name.strip(), ENTITY_TYPES[ty]
        if not CJK_NAME_RE.match(name) or name in sutra_titles or re.search(r"[經論疏鈔觀]$", name) and label == "名相":
            continue
        if label == "名相" and HONORIFIC_RE.search(name) and len(name) > 2:
            label = "人物"   # 賢首國師 / 觀自在菩薩 are typed as concepts in the dictionary
        if name not in names or rank[label] < rank[names[name]]:
            names[name] = label
    for name, gloss in conn.execute(
            "SELECT e.name, g.gloss FROM entity_glosses g JOIN entities e ON e.id = g.entity_id"
            " WHERE g.source = '丁福保佛學大辭典' AND e.type IN (?,?,?,?)", tuple(ENTITY_TYPES)):
        glosses.setdefault(name.strip(), gloss.strip())
    conn.close()
    return names, glosses


def scan_names(text: str, names: dict, by_len: list[int]) -> Counter:
    """Longest-match dictionary scan: name -> mentions."""
    hits, i, n = Counter(), 0, len(text)
    while i < n:
        for L in by_len:
            if text[i:i + L] in names:
                hits[text[i:i + L]] += 1
                i += L
                break
        else:
            i += 1
    return hits


def snippet(text: str, name: str, width: int = 36) -> str:
    i = text.find(name)
    if i < 0:
        return ""
    s = text[max(0, i - width): i + len(name) + width]
    # citations (whole or cut off at either edge), markup, list numbering
    s = re.sub(r"〔行[^〕]*〕|〔行[^〕]*$|^[^〔〕]*〕|\*\*|[#|>`]|(?:^|\s)\d+\.\s", " ", s)
    s = re.sub(r"\s+", " ", s).strip(" ，、；：")
    j = s.find(name)
    s = s[max(0, j - width // 2): j + len(name) + width // 2]
    return "…" + s.strip() + "…"


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mani", default=str(SITE.parent / "mani"))
    ap.add_argument("--config", default=str(SITE / "site.config.json"))
    args = ap.parse_args()
    mani = Path(args.mani).resolve()
    cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
    sys.path.insert(0, str(mani / "pipelines" / "knowledgebase"))
    from src import lesson_key  # the one owner of lesson numbering

    for d in (CONTENT / "notes", CONTENT / "lessons", PUBLIC_DATA):
        shutil.rmtree(d, ignore_errors=True)
        d.mkdir(parents=True)

    lessons: dict = {}
    channels = [export_channel(ch, mani, lesson_key, lessons) for ch in cfg["channels"]]
    noted = {k: e for k, e in lessons.items() if e.get("has_note")}
    stem_to_key = {e["_note"].stem: k for k, e in noted.items()}

    # ---- verified quotes ----
    proofs, passage_index = {}, defaultdict(set)
    for k, e in noted.items():
        f = lesson_key.find_lesson_file(e["_art"], "*校對.json", e["no"])
        quotes = []
        if f:
            try:
                raw = json.loads(f.read_text(encoding="utf-8"))
            except ValueError:
                raw = {}
            for q in raw.get("quotes", []) if isinstance(raw, dict) else []:
                if nq := normalize_quote(q):
                    quotes.append(nq)
        proofs[k] = quotes
        for q in quotes:
            norm = PUNCT_RE.sub("", q["text"])
            if q["cbeta"] and len(norm) >= 8:
                passage_index[(q["cbeta"], norm[:10])].add(k)

    # ---- names: marked-up sutras/people/places + dictionary concepts/people ----
    dictionary, glosses = load_dictionary(mani)
    # the channels' own teachers are in every talk; the stoplist holds dictionary words
    # that are ambiguous in these notes (會通, 法寶 typed as people)
    stop = set(cfg.get("entity_stoplist", [])) | {teacher_short(c["teacher"]) for c in channels if c["teacher"]}
    by_len = sorted({len(n) for n in dictionary}, reverse=True)
    mentions = {}          # key -> Counter("type:name")
    for k, e in noted.items():
        body = e["_body"]
        c = Counter()
        c.update("經:" + clean_sutra_name(s) for s in SUTRA_RE.findall(body))
        c.update("地名:" + s for s in PLACE_RE.findall(body))
        for p in PERSON_RE.findall(body):
            if p not in stop and (dictionary.get(p) == "人物" or HONORIFIC_RE.search(p)):
                c["人物:" + p] += 1
        # scan prose only: not headings (template words) or sutra titles (金剛 in 《金剛經》)
        prose = SUTRA_RE.sub("《》", re.sub(r"^#.*$", "", body, flags=re.M))
        for name, n in scan_names(prose, dictionary, by_len).items():
            if name not in stop:
                c[f"{dictionary[name]}:{name}"] += n
        for cid in e["_meta"].get("canon_cited") or []:
            c["藏:" + str(cid)] += 1
        mentions[k] = c

    # ---- related talks: idf-weighted shared names, same quoted passage, wiki links ----
    df = Counter(t for c in mentions.values() for t in c)
    n_docs = max(1, len(mentions))
    idf = {t: math.log(n_docs / c) for t, c in df.items() if 1 < c < n_docs * 0.5}

    def ref(k):
        return {"key": k, "title": lessons[k]["title"]}

    for k, e in noted.items():
        mine = mentions[k]
        scores = []
        for other, oc in mentions.items():
            if other == k:
                continue
            shared = [(t, idf[t] * math.log1p(min(mine[t], oc[t]))) for t in mine.keys() & oc.keys() if t in idf]
            if not shared:
                continue
            top = [t.split(":", 1)[1] for t, _ in sorted(shared, key=lambda x: -x[1])
                   if not t.startswith("藏:")][:3]
            scores.append((sum(w for _, w in shared), other, top))
        scores.sort(key=lambda x: (-x[0], x[1]))
        same_topic = [{**ref(o), "shared": top} for _, o, top in scores[:8]]

        same_passage = {}
        for q in proofs[k]:
            if not q["cbeta"]:
                continue
            for other in sorted(passage_index.get((q["cbeta"], PUNCT_RE.sub("", q["text"])[:10]), ())):
                if other != k and other not in same_passage:
                    same_passage[other] = {**ref(other), "quote": q["text"][:40], "cbeta": q["cbeta"]}

        links = []

        def wiki(m):
            target = stem_to_key.get(m.group(1).strip())
            label = (m.group(2) or "").strip() or (lessons[target]["title"] if target else m.group(1))
            if target:
                links.append(ref(target))
                return f"[{label}](@/{target}/)"
            return label
        e["_body"] = WIKILINK_RE.sub(wiki, e["_body"])

        names = [t for t, _ in sorted(((t, mine[t] * idf.get(t, 0)) for t in mine
                                       if t.split(":")[0] in ("名相", "人物")), key=lambda x: -x[1])][:14]
        out = {"proof": proofs[k],
               "related": {"same_topic": same_topic,
                           "same_passage": list(same_passage.values())[:12], "linked": links},
               "canon_cited": [str(c) for c in e["_meta"].get("canon_cited") or []],
               "names": [{"type": t.split(":", 1)[0], "name": t.split(":", 1)[1]} for t in names]}
        for path, payload in ((CONTENT / "lessons" / f"{k}.json", json.dumps(out, ensure_ascii=False, indent=1)),
                              (CONTENT / "notes" / f"{k}.md", e["_body"])):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(payload, encoding="utf-8")

    # ---- sutra index ----
    cache = {}
    alias_votes = defaultdict(Counter)
    for e in noted.values():
        for name, cid in SUTRA_ID_RE.findall(e["_body"]):
            alias_votes[clean_sutra_name(name)][cid] += 1
    sutras = defaultdict(lambda: {"quotes": defaultdict(list), "cited": set(), "home": set()})
    for k, e in noted.items():
        for q in proofs[k]:
            if q["cbeta"]:
                sutras[q["cbeta"]]["quotes"][k].append({"text": q["text"], "line": q["line"]})
        for cid in e["_meta"].get("canon_cited") or []:
            sutras[str(cid)]["cited"].add(k)
        if e["_meta"].get("home_sutra"):
            sutras[str(e["_meta"]["home_sutra"])]["home"].add(k)
    sutra_out, alias = {}, {}
    for cid, v in sutras.items():
        if not CBETA_ID_RE.fullmatch(cid):
            continue
        meta = cbeta_meta(mani, cid, cache)
        talks = sorted(set(v["quotes"]) | v["cited"] | v["home"])
        sutra_out[cid] = {
            "title": meta["title"], "by": meta["by"],
            "talks": [{"key": t, "home": t in v["home"], "quotes": v["quotes"].get(t, [])[:8]} for t in talks],
        }
        if meta["title"]:
            alias.setdefault(meta["title"], cid)
    for name, votes in alias_votes.items():
        cid, n = votes.most_common(1)[0]
        if cid in sutra_out and (n >= 2 or name not in alias):
            alias.setdefault(name, cid)

    # ---- entity pages: names in >= min_talks talks ----
    min_talks = cfg.get("entity_min_talks", 2)
    per_name = defaultdict(dict)
    for k, c in mentions.items():
        for t, n in c.items():
            ty, name = t.split(":", 1)
            if ty in ("名相", "人物", "地名"):
                per_name[(ty, name)][k] = n
    # a name in most talks (眾生, 菩薩) gives a page that lists everything: skip it
    max_talks = max(min_talks, int(len(noted) * cfg.get("entity_max_share", 0.5)))
    entities = defaultdict(dict)
    for (ty, name), talks in per_name.items():
        if not min_talks <= len(talks) <= max_talks:
            continue
        ranked = sorted(talks.items(), key=lambda x: (-x[1], x[0]))
        entities[ty][name] = {
            "gloss": glosses.get(name),
            "talks": [{"key": t, "n": n, "snip": snippet(noted[t]["_body"], name)} for t, n in ranked],
        }

    site = {"title": cfg.get("title"), "tagline": cfg.get("tagline"), "channels": channels}
    for name, payload in (("site.json", site),
                          ("sutras.json", {"sutras": sutra_out, "alias": alias}),
                          ("entities.json", entities)):
        (CONTENT / name).write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    for old in ("series.json",):
        (CONTENT / old).unlink(missing_ok=True)

    flagged = [(k, l) for k, e in noted.items() for l in public_voice.audit(e["_body"])
               if re.search(r"(?:法師|師)[^。，；]{0,8}(?<!無)誤(?!導|讀|會|解)", l)]
    for k, l in flagged[:20]:
        print(f"  public voice? {k}: {l[:100]}", file=sys.stderr)
    print(f"{len(channels)} channel(s), {sum(len(c['series']) for c in channels)} series, "
          f"{len(noted)} notes, {sum(1 for e in lessons.values() if e.get('has_transcript'))} transcripts, "
          f"{sum(len(v) for v in proofs.values())} verified quotes, {len(sutra_out)} sutras, "
          + ", ".join(f"{len(v)} {k}" for k, v in entities.items())
          + f"; {len(flagged)} line(s) for public-voice review")


if __name__ == "__main__":
    main()
