import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';
import mermaid from 'astro-mermaid';

// Part 2 slice plan site. Content lives in docs/part2 and is synced into
// src/content/docs/plan by scripts/sync-docs.mjs before dev and build.
export default defineConfig({
  integrations: [
    // Must come before starlight(): rewrites ```mermaid fences before
    // Expressive Code sees them; autoTheme follows light/dark.
    mermaid({ theme: 'default', autoTheme: true }),
    starlight({
      title: 'SCIO Slice Plan · Brief B',
      description:
        'Plan for building the Teams, Roles, Permissions, Assets and Screens slice of SCIO: what, in what order, how long, and why.',
      // Candidate material: keep it out of search engines.
      head: [{ tag: 'meta', attrs: { name: 'robots', content: 'noindex, nofollow' } }],
      lastUpdated: false,
      sidebar: [
        {
          label: 'Overview',
          items: [
            { label: 'Home', link: '/' },
            { label: 'Summary', link: '/plan/summary/' },
          ],
        },
        {
          label: 'Product today',
          items: [{ label: 'How SCIO works today', link: '/plan/scio-today/' }],
        },
        {
          label: 'Design',
          items: [
            { label: 'Scope & decisions', link: '/plan/scope/' },
            { label: 'Architecture', link: '/plan/architecture/' },
            { label: 'Data model & authorization', link: '/plan/data-model-and-authorization/' },
            { label: 'Lifecycles', link: '/plan/lifecycles/' },
          ],
        },
        {
          label: 'Delivery',
          items: [
            { label: 'Security & tests', link: '/plan/security-and-tests/' },
            { label: 'Milestones & calendar', link: '/plan/milestones/' },
            { label: 'Estimate & AI', link: '/plan/estimate/' },
            { label: 'Risks & open questions', link: '/plan/risks-and-open-questions/' },
          ],
        },
      ],
    }),
  ],
});
