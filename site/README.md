# Part 2 plan site

Static site for the Part 2 slice plan, built with Astro + Starlight. The content source is [`docs/part2`](../docs/part2/README.md). `scripts/sync-docs.mjs` copies it into `src/content/docs/plan/` before every dev or build run. Those generated files are git-ignored, so edit the Markdown in `docs/part2`, not here. Only the landing page (`src/content/docs/index.mdx`) is written for the site.

```bash
cd site
npm install
npm run dev      # http://localhost:4600
npm run build    # static output in dist/
```

Mermaid fences render through `astro-mermaid`, which follows the light and dark theme. Pages carry `noindex, nofollow`.
