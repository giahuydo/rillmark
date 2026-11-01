// Copies the plan from docs/part2 (the single source of truth, readable on
// GitHub) into Starlight's content collection. Generated files are git-ignored.
//
// Per file: the H1 becomes the frontmatter title, the GitHub prev/next nav
// lines are dropped (Starlight has its own), and links between plan files are
// rewritten to site routes.
import { readFileSync, writeFileSync, readdirSync, mkdirSync, rmSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const SRC = join(here, '..', '..', 'docs', 'part2');
const OUT = join(here, '..', 'src', 'content', 'docs', 'plan');

const slugOf = (file) =>
  file === 'README.md' ? 'summary' : file.replace(/\.md$/, '').replace(/^\d+-/, '');

const DESCRIPTIONS = {
  summary: 'What we would build, in what order, how long it takes, and why.',
  'scio-today': 'What we observed in a real SCIO trial, with evidence labels, and what is still unknown.',
  scope: 'In scope, the decisions the brief leaves open, and non-goals.',
  architecture: 'Modular monolith, file storage (blobs, previews, quota) and queue, with rejected alternatives.',
  'data-model-and-authorization': 'Entities, the authorize() decision, folder permission bits and decisions D2–D5.',
  lifecycles: 'Upload, pairing, Move To Team, and assignment through Edit Screen and Push.',
  'security-and-tests': 'Threats covered and representative negative tests.',
  milestones: 'M0–M9, dependency graph, calendar, critical path and cut order.',
  estimate: 'Three delivery levels, the AI-assisted forecast, and what was cut from planning.',
  'risks-and-open-questions': 'Risks with fallbacks, and questions that do not block the start.',
};

const isNavLine = (line) => /\[Overview\]\(README\.md\)/.test(line);

const rewriteLinks = (text) =>
  text.replace(/\]\(((?:\d+-[\w-]+|README)\.md)(#[^)]*)?\)/g, (_, file, hash = '') =>
    `](/plan/${slugOf(file)}/${hash})`,
  );

rmSync(OUT, { recursive: true, force: true });
mkdirSync(OUT, { recursive: true });

const files = readdirSync(SRC).filter((f) => f.endsWith('.md')).sort();
for (const file of files) {
  const slug = slugOf(file);
  let lines = readFileSync(join(SRC, file), 'utf8').split('\n');

  const h1 = lines.findIndex((l) => l.startsWith('# '));
  let title = lines[h1].slice(2).trim();
  lines.splice(h1, 1);

  lines = lines.filter((l) => !isNavLine(l));
  if (slug === 'summary') {
    title = 'Summary';
    lines = lines.filter((l) => l.trim() !== '## 1. Summary');
  }

  let body = lines.join('\n').trim();
  body = body.replace(/\n+---\s*$/, '').trim(); // separator left before the bottom nav
  body = rewriteLinks(body);

  const fm = [
    '---',
    `title: ${JSON.stringify(title)}`,
    `description: ${JSON.stringify(DESCRIPTIONS[slug] ?? '')}`,
    '---',
    '',
  ].join('\n');
  writeFileSync(join(OUT, `${slug}.md`), `${fm}\n${body}\n`);
}
console.log(`synced ${files.length} files from docs/part2 → src/content/docs/plan`);
