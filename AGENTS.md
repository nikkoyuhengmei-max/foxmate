# AGENTS.md

## Cursor Cloud specific instructions

This repo is the **FoxMate AI marketing website** — a single Next.js 14 (App Router) + TypeScript + Tailwind CSS static site. There is no backend, database, API, or environment variables; it's a purely static frontend. Standard commands live in `package.json` (`dev`, `build`, `start`, `lint`).

- **Run dev server:** `npm run dev` serves on http://localhost:3000. This is the only service.
- **Build:** `npm run build` also runs TypeScript type-checking and validity checks, so it's the most reliable correctness gate.
- **Lint:** `npm run lint` (`next lint`) is **not configured** in this repo — running it triggers an interactive ESLint setup prompt and will hang in non-interactive environments. Rely on `npm run build` for type/validity checking unless you intentionally add an ESLint config.
- **Static export caveat:** `vercel.json` sets `outputDirectory: "out"`, but there is no `next.config.js` with `output: 'export'`, so `npm run build` produces a `.next` build, not an `out/` directory. The README references a `next.config.js` that does not exist.
- **Committed build artifacts:** Pre-exported static files (`index.html`, `about.html`, `features.html`, `download.html`, `404.html`, `_next/`, and many image assets) are checked into the repo root alongside the `app/` source. These are stale exports, not the live dev output — edit source in `app/`, `components/`, and `lib/`.
- **i18n note:** Language infrastructure exists (`components/LanguageContext.tsx`, `lib/translations.ts`) but there is no language-switcher UI in the navbar; switching languages from the UI is not currently wired up.
