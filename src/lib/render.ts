// Note markdown -> HTML, with 〔行N〕 citations folded into quiet markers.
// The citation grammar is ported from decorate() in mani/webui/static/js/notes.js.
import { marked } from "marked";
import { url, sutraData, sutraUrl, entityUrl, hasEntity, cbetaUrl } from "./data";

export interface TocItem { id: string; text: string }

const RANGE = /(?:^|[、，,\s])行(\d+)(?:[-–—／/~～](\d+))?/g;

function citeMarker(inner: string): string {
  const ranges: string[] = [];
  for (const m of ("、" + inner).matchAll(RANGE)) {
    const s = m[1], e = m[2] && Number(m[2]) > Number(s) ? m[2] : s;
    ranges.push(s === e ? s : `${s}-${e}`);
  }
  if (!ranges.length) return `〔${inner}〕`;
  const label = "逐字稿 行" + ranges.join("、").replace(/-/g, "–");
  // any words beside the 行 refs ("逐字稿藏經塊") move into the popover
  const rest = inner.replace(RANGE, "").replace(/^[、，,\s]+|[、，,\s]+$/g, "");
  const note = rest ? ` data-note="${rest.replace(/"/g, "&quot;")}"` : "";
  const first = ranges[0].split("-")[0];
  return `<a class="c" href="transcript/#L${first}" data-r="${ranges.join(",")}"${note} aria-label="${label}" title="${label}"></a>`;
}

const sutraId = (name: string) => sutraData.alias[name.split(/[·・〈]/)[0].trim()];

function decorate(html: string): string {
  html = html.replace(/〔(行\d[^〕<]*)〕/g, (_m, inner) => citeMarker(inner));
  // 《sutra》 → sutra index; 〔person〕 / ［place］ → entity page, when one exists
  html = html.replace(/《([^《》<]{1,24})》/g, (m, n) => {
    const id = sutraId(n);
    return id ? `《<a class="ent" href="${sutraUrl(id)}">${n}</a>》` : m;
  });
  html = html.replace(/〔([^〕<]{1,12})〕/g, (m, n) =>
    hasEntity("人物", n) ? `〔<a class="ent" href="${entityUrl("人物", n)}">${n}</a>〕` : m);
  html = html.replace(/［([^］<]{1,16})］/g, (m, n) =>
    hasEntity("地名", n) ? `［<a class="ent" href="${entityUrl("地名", n)}">${n}</a>］` : m);
  html = html.replace(/✓\s*CBETA\s*([TXBJ]\d{4}[A-Z]?)/g,
    (m, id) => `<a class="cbeta" href="${cbetaUrl(id)}" target="_blank" rel="noopener">${m}</a>`);
  html = html.replace(/※/g, '<span class="ref-mark" title="字句或出處與藏經原文有別，見原文對照">※</span>');
  html = html.replace(/href="@\/([^"]*)"/g, (_m, p) => `href="${url(p)}"`);
  return html;
}

export function renderNote(md: string): { html: string; toc: TocItem[] } {
  let html = marked.parse(md, { async: false, gfm: true }) as string;
  const toc: TocItem[] = [];
  let i = 0;
  html = html.replace(/<h2>(.*?)<\/h2>/g, (_m, inner) => {
    const id = `s${++i}`;
    toc.push({ id, text: inner.replace(/<[^>]+>/g, "").replace(/〔行[^〕]*〕/g, "") });
    return `<h2 id="${id}">${inner}</h2>`;
  });
  html = html.replace(/<table>/g, '<div class="table-wrap"><table>').replace(/<\/table>/g, "</table></div>");
  return { html: decorate(html), toc };
}

// one transcript line: keep the preprocessor's **entity** bold, escape the rest
export function renderLine(text: string): string {
  const esc = text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  return esc.replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>");
}
