"""Public voice: how a mani study note reads on the public site.

The teacher speaks without a script, so a quotation or attribution recalled from
memory can differ from the canon in wording or source. mani's notes record each
difference in QA language (誤述 / 誤稱 / 出處誤植 / ⚠ / 待覆核 ...). The site keeps
the scholarship (the canonical text and its CBETA source) and drops the verdict:
a difference is shown as a neutral reference mark, ※, never as a mistake.

Rules, applied in order:
  1. drop QA-only sections (校勘 / 逐字稿瑕疵 / 源頭缺陷 / 片尾字幕) and QA blocks
     inside a section (a 待覆核 list, an 教師誤述 item, pipeline notes);
  2. rewrite teacher-directed wording to neutral wording (法師誤稱 → 法師稱 ...);
  3. ⚠ → ※.
Machine errors (OCR, subtitles) are left as written: they are not about the teacher.
`audit()` lists lines that still pair the teacher with 誤/錯, for review.
"""
import re

MARK = "※"

# whole ## sections that only record QA
DROP_SECTION = re.compile(r"校勘|逐字稿瑕疵|源頭缺陷|片尾.{0,4}字幕|更正|口誤|待覆核")

# a list item / paragraph / table row that is QA bookkeeping
DROP_LINE = re.compile(
    r"^\s*(?:[-*]|\d+\.)?\s*\**(?:待覆核|講師誤述|教師誤述|教師誤記|教師誤讀|法師誤記|出處誤記|更正)"
    r"|Stage\s*2|sidecar|誤植塊|誤植清單|誤植紀錄|標記誤植|KB 解說|teacher_mis|^\s*\**小計"
)

TEACHER = r"(法師|教師|講師|南師|師)"
# verb kept, verdict dropped
VERB = {"誤稱": "稱", "誤記": "記", "誤引": "引", "誤述": "所述", "誤讀": "讀", "口誤": "口述",
        "誤作": "作", "誤以為": "以為", "誤說": "說"}
INLINE = [
    # (teacher) 誤稱 / 誤記為 ... → (teacher) 稱 / 記為
    (re.compile(TEACHER + r"(本講|此處|此)?(" + "|".join(VERB) + ")"),
     lambda m: m.group(1) + (m.group(2) or "") + VERB[m.group(3)]),
    # any other (teacher)誤X: 法師誤標為 / 師誤繫 → 法師標為 / 師繫
    (re.compile(TEACHER + r"(本講|此處|此|將|把)?誤(?=[\u4e00-\u9fff])(?!會|解)"),
     lambda m: m.group(1) + (m.group(2) or "")),
    # 出處誤植 / 出處誤記 → 出處另見
    (re.compile(r"出處(?:誤植|誤記|誤稱|誤述|有誤)"), lambda m: "出處另見"),
    # pointers to dropped blocks: （見§教師誤述） / 見 §12 待覆核
    (re.compile(r"[（(]?\s*(?:見|入|詳)\s*§\s*(?:\d+\s*)?(?:教師|講師)?(?:誤述|誤讀|誤記|待覆核)項?\s*[）)]?"),
     lambda m: ""),
    # "not a mistake" disclaimers: ，非誤引 / 不判為誤述。/ 非法師之誤
    (re.compile(r"[，,；]?\s*(?:並?非|不判為|不列|無)(?:事實|法師|教師|師述|義理|內容)?(?:之)?"
                r"(?:誤述|誤記|誤引|口誤|誤讀|之誤|有誤|錯誤)(?:項)?(?=[，,。；|）)\s]|$)"),
     lambda m: ""),
    (re.compile(r"[（(]\s*teacher[^）)]*[）)]", re.I), lambda m: ""),
    (re.compile(r"(?:教師|講師)誤(?:述|讀|記)項?"), lambda m: "出處補註"),
    (re.compile(r"待覆核"), lambda m: "待考"),
    (re.compile(r"⚠️?"), lambda m: MARK),
    # standalone verdict tags: 【誤記】 / **誤引** / ※ 誤記 → 出處補註
    (re.compile(r"(?<=[【※*\s（(])(?:teacher\s*)?誤(?:記|引|稱|述|植|標|繫)(?:出處)?(?=[】*\s：:）)|，]|$)", re.I),
     lambda m: "出處補註"),
    (re.compile(r"出處誤(?:繫|標|植|記|稱|述)?"), lambda m: "出處另見"),
    (re.compile(r"(?<!錯)誤(稱|記|引|標|繫)"), lambda m: m.group(1)),
    (re.compile(r"訂正(?=法師|教師|講師)"), lambda m: "對照"),
    (re.compile(r"誤述"), lambda m: "所述"),
    (re.compile(r"口誤"), lambda m: "口語"),
    (re.compile(r"(?<![A-Za-z])teacher(?![A-Za-z_])", re.I), lambda m: "法師"),
    # verification-tool jargon → plain words
    (re.compile(r"卷首\s*YAML\s*✓[；;，,]?\s*"), lambda m: ""),
    (re.compile(r"`?(?:kb_query\s*)?--verify`?(?:\s*→)?\s*"), lambda m: ""),
    (re.compile(r"`?NOT FOUND(?: IN CANON)?`?"), lambda m: "藏內未見"),
    (re.compile(r"(?<![A-Za-z])VERIFIED(?![A-Za-z])"), lambda m: "✓"),
    (re.compile(r"(?<![A-Za-z])FLAGGED(?![A-Za-z])"), lambda m: MARK),
    (re.compile(r"`?reference/cbeta/[^`\s）)|]*`?"), lambda m: "CBETA"),
    (re.compile(r"canon[-_ ]verify", re.I), lambda m: "CBETA 核對"),
    (re.compile(r"(?<![A-Za-z])UNVERIFIED(?![A-Za-z])"), lambda m: "未核"),
    (re.compile(r"Pre-flight\s*", re.I), lambda m: ""),
    (re.compile(TEACHER + r"([^，。；|\n]{0,6})有誤"), lambda m: m.group(1) + m.group(2) + "與原典不同"),
    # 教師將《大乘義章》誤歸吉藏 → 教師將《大乘義章》歸吉藏
    (re.compile(TEACHER + r"([^，。；|\n]{1,14})誤(?=歸|作|植|記|稱|引|標|繫|為)"), lambda m: m.group(1) + m.group(2)),
    (re.compile(r"[，,]?\s*(?:並?非全|非)誤(?=[）)，。；|]|$)"), lambda m: ""),
    (re.compile(r"」誤[，,]\s*應為"), lambda m: "」，原典作"),
    (re.compile(TEACHER + r"誤(?=[，,；])"), lambda m: m.group(1) + "述"),
    (re.compile(r"教師"), lambda m: "法師"),
    (re.compile(r"師誤\s*[·・]\s*經義更正|\**師誤\**(?=\s*[：:）)])"), lambda m: "原文對照"),
    (re.compile(r"[，,]?\s*非必為(?:法師)?之誤"), lambda m: ""),
    (re.compile(r"已於\s*(§[\d\-、§\s]+?)\s*更正"), lambda m: "見" + m.group(1)),
    (re.compile(r"師述誤[一-鿿]?"), lambda m: "原文對照"),
    # 法師說「德宗」有誤 / 師稱「唐末」為誤 → …「德宗」，與原典有別
    (re.compile(r"(」[^，。；」]{0,3})(?:有|為)誤"), lambda m: m.group(1) + "，與原典有別"),
]

H2 = re.compile(r"^##\s")


def _drop_sections(md: str) -> str:
    out, skipping = [], False
    for line in md.splitlines():
        if H2.match(line):
            skipping = bool(DROP_SECTION.search(line))
        if not skipping:
            out.append(line)
    return "\n".join(out)


def _drop_blocks(md: str) -> str:
    """Drop QA lines; a dropped list item takes its nested children with it."""
    out, drop_indent = [], None
    for line in md.splitlines():
        indent = len(line) - len(line.lstrip())
        if drop_indent is not None:
            if line.strip() and indent > drop_indent:
                continue
            drop_indent = None
        if DROP_LINE.search(line):
            if re.match(r"\s*(?:[-*]|\d+\.)\s", line):
                drop_indent = indent
            continue
        out.append(line)
    return "\n".join(out)


def apply(md: str) -> str:
    md = _drop_blocks(_drop_sections(md))
    for rx, fn in INLINE:
        md = rx.sub(fn, md)
    md = re.sub(r"[（(]\s*[）)]", "", md)          # parentheses emptied by the rules
    md = re.sub(r"\n{3,}", "\n\n", md)
    return md.rstrip() + "\n"


AUDIT = re.compile(TEACHER + r"[^。，；|\n]{0,6}(誤|錯)|teacher", re.I)
DOCTRINE = re.compile(r"誤認|誤會|誤解|誤以|錯誤的(?:願|選擇|行為|見)|糾正")


def audit(md: str) -> list[str]:
    return [l.strip()[:140] for l in md.splitlines()
            if AUDIT.search(l) and not DOCTRINE.search(l)]
