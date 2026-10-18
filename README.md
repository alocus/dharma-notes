# 講經筆記

A static site of Dharma talks: study notes (學習筆記), full transcripts (逐字稿), related talks, a 名相/人物/地名 index, a sutra index and client-side search. No database or server is needed.

## How it works

```
../mani  ──scripts/export.py──▶  content/ + public/data/  ──astro build + pagefind──▶  dist/
```

### `site.config.json`

| Key | Meaning |
|---|---|
| `title` | Site name |
| `tagline` | Home-page intro |
| `channels` | Which mani channels to publish. Any channel with notes works. |
| `entity_min_talks` | A name gets its own page only if it appears in at least this many talks. |
| `entity_max_share` | A name that appears in more than this share of talks gets no page (it would just list everything). |
| `entity_stoplist` | Dictionary words that are ambiguous in these notes, such as 會通 or 法寶 being typed as people. |

### `scripts/export.py`

The exporter reads `../mani` and never writes there.

- **Notes:** written to `content/notes/<channel>/<series>/<NN>.md`, after rewriting into the public voice (next section).
- **Per-talk data:** `content/lessons/…json` holds the verified quotes, related talks and the talk's main names.
- **Indexes:**
  - `content/sutras.json` maps each CBETA id to the talks that quote or cite it.
  - `content/entities.json` maps each 名相, 人物 and 地名 to the talks that mention it, plus a 丁福保《佛學大辭典》 gloss.
- **Transcripts:** `public/data/…json` holds the transcript lines and the line → video time map.
- **Sources:**
  - Used: only what the site publishes (notes, transcripts, verified quotes), mani's entity dictionary and the 丁福保 glosses.
  - Never read: mani's private insight graph (`insight_edges`, `圖譜.json`).

### `scripts/public_voice.py`

The teacher speaks without notes, so a quotation recalled from memory can differ from the canon in wording or source. The notes keep the canonical text and its CBETA source, but no verdict about the teacher:

- A difference is shown as a neutral **※** (原文對照), never as a mistake.
- Teacher-directed wording is rewritten, for example 法師誤稱 → 法師稱 and 出處誤植 → 出處另見.
- QA-only sections (校勘, 逐字稿瑕疵, 待覆核 lists) and verification-tool jargon are dropped.
- Machine errors (OCR) are left as written.

Every export ends by printing any line that still pairs the teacher with 誤 (`public voice? …`), so new wording can be caught and a rule added.

## Commands

```sh
npm run export    # re-snapshot from ../mani (uses mani's venv)
npm run dev       # local dev server
npm run build     # astro build + sitemap + pagefind index → dist/
npm run preview   # serve dist/ at http://localhost:4321/dharma-notes/
```

After `npm run export`, commit `content/` and `public/data/`. CI builds from the committed snapshot.

## Routes

| Route | Page |
|---|---|
| `/` | Home: channels and their series |
| `/<channel>/<series>/` | Table of contents for a series |
| `/<channel>/<series>/<NN>/` | Note reader |
| `/<channel>/<series>/<NN>/transcript/` | Transcript |
| `/e/`, `/e/<名相\|人物\|地名>/<name>/` | Name index and name pages |
| `/sutra/`, `/sutra/<CBETA id>/` | Sutra index and sutra pages |
| `/search/` | Search |
| `/guide/` | Reading guide (閱讀說明) |
| `/sitemap-index.xml` | Sitemap |

## Deploy

`.github/workflows/deploy.yml` builds and deploys to GitHub Pages on every push to `main`. To set it up, go to Settings → Pages and set Source to "GitHub Actions". The base path is `/dharma-notes` (see `astro.config.mjs`).
