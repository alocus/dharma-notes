// Build-time access to the snapshot written by scripts/export.py.
import fs from "node:fs";
import path from "node:path";

const ROOT = process.cwd();
const read = (p: string) => fs.readFileSync(path.join(ROOT, p), "utf-8");
const json = <T>(p: string): T => JSON.parse(read(p));

export interface Lesson {
  no: string;
  title: string;
  scope: string;
  has_note: boolean;
  has_transcript: boolean;
  raw?: boolean;
  video_id?: string | null;
  date?: string | null;
  duration?: string | null;
}

export interface Series {
  slug: string;
  name: string;
  teacher: string | null;
  home_sutra: string | null;
  home_sutra_id: string | null;
  lessons: Lesson[];
}

export interface Channel { slug: string; name: string; teacher: string | null; series: Series[] }
export interface Site { title: string; tagline: string; channels: Channel[] }

export interface Ref { key: string; title: string }
export interface Quote { text: string; attrib: string; cbeta: string | null; line: number | null }
export interface LessonExtra {
  proof: Quote[];
  related: {
    same_topic: (Ref & { shared: string[] })[];
    same_passage: (Ref & { quote: string; cbeta: string })[];
    linked: Ref[];
  };
  canon_cited: string[];
  names: { type: string; name: string }[];
}
export interface TranscriptData { lines: string[]; t: Record<string, [number, number]> }
export interface SutraEntry {
  title: string | null;
  by: string | null;
  talks: { key: string; home: boolean; quotes: { text: string; line: number | null }[] }[];
}
export interface EntityEntry { gloss: string | null; talks: { key: string; n: number; snip: string }[] }

export const site = json<Site>("content/site.json");
export const sutraData = json<{ sutras: Record<string, SutraEntry>; alias: Record<string, string> }>("content/sutras.json");
export const entities = json<Record<string, Record<string, EntityEntry>>>("content/entities.json");
export const ENTITY_TYPES = ["名相", "人物", "地名"] as const;

export const allChannels = () => site.channels;
export const allSeries = () => site.channels.flatMap((c) => c.series.map((s) => ({ c, s })));

export const noteMarkdown = (key: string) => read(`content/notes/${key}.md`);
export const lessonExtra = (key: string): LessonExtra => json(`content/lessons/${key}.json`);
export const transcript = (key: string): TranscriptData => json(`public/data/${key}.json`);

export interface Located { c: Channel; s: Series; l: Lesson; key: string }
let _byKey: Map<string, Located> | null = null;
export function lessonByKey(key: string): Located | null {
  if (!_byKey) {
    _byKey = new Map();
    for (const c of site.channels)
      for (const s of c.series)
        for (const l of s.lessons) {
          const k = `${c.slug}/${s.slug}/${l.no}`;
          _byKey.set(k, { c, s, l, key: k });
        }
  }
  return _byKey.get(key) ?? null;
}
export const allLessons = () => { lessonByKey(""); return [..._byKey!.values()]; };

// source titles are inconsistent ("達磨血脈論01", "第三講 —"); show one shape
export function lessonTitle(s: Series, l: Lesson): string {
  if (s.lessons.length === 1) return l.title;
  const tail = l.title.match(/[（(](上|下|圓滿)[)）]/)?.[0] ?? "";
  return `${s.name} 第${Number(l.no)}講${tail}`;
}
export const refTitle = (key: string) => {
  const x = lessonByKey(key);
  return x ? lessonTitle(x.s, x.l) : key;
};
// with several channels a bare series name is ambiguous: prefix the teacher
export const multiChannel = site.channels.length > 1;
export const channelLabel = (c: Channel) => teacherShort(c.teacher) ?? c.name;
export const teacherShort = (t: string | null) => t?.split(/[（(；;，,]/)[0].trim() ?? null;

export function clip(text: string, n: number): string {
  const t = (text || "").replace(/\*\*/g, "");
  return t.length > n ? t.slice(0, n) + "…" : t;
}

// site-absolute URL under the configured base
export function url(p: string): string {
  const base = import.meta.env.BASE_URL.replace(/\/$/, "");
  return base + "/" + p.replace(/^\//, "");
}
export const lessonUrl = (key: string) => url(`${key}/`);
export const transcriptUrl = (key: string) => url(`${key}/transcript/`);
export const seriesUrl = (c: Channel, s: Series) => url(`${c.slug}/${s.slug}/`);
export const entityUrl = (type: string, name: string) => url(`e/${type}/${name}/`);
export const sutraUrl = (id: string) => url(`sutra/${id}/`);
export const cbetaUrl = (id: string) => `https://cbetaonline.dila.edu.tw/zh/${id}`;

export function hasEntity(type: string, name: string) { return !!entities[type]?.[name]; }

export function fmtTime(sec: number): string {
  const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), s = Math.floor(sec % 60);
  const mm = String(m).padStart(2, "0"), ss = String(s).padStart(2, "0");
  return h ? `${h}:${mm}:${ss}` : `${m}:${ss}`;
}
