# Nextplay design system

## Scene and register

A PC player browses after an evening gaming session in a dim room, looking for a
new game without the glare of a bright page. The user explicitly chose a dark,
compact, Steam-like product interface. Design serves the recommendation workflow.

## Color strategy

Restrained: pure neutral near-black surfaces, green for actions and selection, and
a pale amber accent for the demo-data disclosure. The Impeccable palette seed was
green at hue 150; the primary action color retains that hue with sufficient contrast.
All tokens use OKLCH. Body and secondary text must retain AA contrast on their surfaces.

## Typography

Use the platform system sans stack. A fixed rem scale runs from 0.75rem metadata
to a 1.875rem main heading. Keep paragraphs under 70ch. Game titles are compact,
with enough room to wrap and remain readable.

## Layout

Desktop uses a 216px navigation rail and a flexible catalogue. Game covers form a
responsive gallery; recommendations add rank and a concise reason. At narrow widths,
navigation becomes horizontal rows that wrap on phones, and the catalogue reduces its column count.
Search uses an inline form rather than a modal.

## Components

- Game tiles: recognizable cover, title, tags, an expandable description, native
  1-5 radio ratings, a clear-rating action, and a Steam store link.
- Navigation: Discover, content recommendations, similar-player recommendations,
  description search, and saved ratings. Current location is marked semantically.
- Filters: a labeled title search and genre/tag select, with pagination and counts.
- Source disclosure: a concise demo badge and expandable provenance detail.
- Search: description input, example prompts, engine choice, and actual method label.
- Feedback: visible saving/error state, polite status announcements, skeleton loading,
  actionable empty states, and server-confirmed rating changes.

## Assets and motion

Steam-hosted cover images are remote and optional; each cover has a readable title
fallback for offline use or failed images. No cover download or generated art is
needed. Simple SVGs serve only as interface icons. Motion lasts 150-180ms and conveys
hover, focus, or saving state; reduced-motion preferences disable it.

