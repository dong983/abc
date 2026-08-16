# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

This is a single-page static HTML site: a personal self-introduction page (자기소개) for a middle school student, written in Korean. There is no build system, package manager, or test suite — the entire site is one self-contained file.

## Development

- The site is a single file: `index.html`. All markup, CSS (in a `<style>` block), and content live there — there is no separate JS, CSS, or asset pipeline.
- To view changes, open `index.html` directly in a browser (or use a simple static file server / VS Code Live Server). There is no build/compile/lint/test step.

## Architecture notes

- **Theming**: Colors are defined as CSS custom properties on `:root` in three layers — a light-mode default, a `@media (prefers-color-scheme: dark)` override guarded by `:root:not([data-theme="light"])`, and an explicit `:root[data-theme="dark"]` override. When editing colors, update all three blocks consistently so light/dark/system-theme stay in sync.
- **Layout**: A single `.container` (max-width 600px, centered) holds a header (avatar + name + school badge), a 2-column `.info-grid` of stat cards, several `.section` blocks (소개/관심사/강점) using a shared card pattern with `.section-icon` + `.section-title` + `.section-content`, and a closing `.message-box` quote.
- **Responsive**: A single breakpoint at `max-width: 480px` collapses the info grid to one column and reduces padding/font sizes.
- Accessibility touches already in place: `focus-visible` outlines and a `prefers-reduced-motion` override — preserve these when restyling interactive elements or animations.
