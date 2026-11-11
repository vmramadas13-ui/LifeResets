# LifeResets visual requirements

## Direction

Use the supplied Inkpop concept as the visual direction: warm paper surfaces, deep ink outlines, flat color, rounded type, sticker-like hard shadows, and a small number of saturated accents. Keep the layout calm, predictable, and responsive, with one clear visual focus on the daily screen. New characters, illustrations, names, and effects must be original to LifeResets.

The daily planner is the primary return screen. It should make the date, available time, energy, selected actions, and next choices easy to scan. Empty states should offer one encouraging action. The sprout guide is a gentle reminder of a fresh start; it must never judge missed activity or obscure controls.

## Accessibility and behavior

- Keep all actions keyboard usable with a visible focus indicator and touch targets of at least 44 CSS pixels.
- Show status in text as well as color. Use clear labels for task actions and recovery suggestions.
- Support light and dark themes, reduced motion, and a persistent standard-language mode.
- Respect the operating system's reduced-motion setting by default; do not use shaking or alarming motion for missed days.
- Keep responsive layouts usable on desktop and mobile without clipping at larger text sizes.
- Check text contrast. The supplied pink accent does not support light text at WCAG AA, so use deep ink text on pink controls. Accessibility requirements take precedence over the concept's suggested text pairing.

## Product boundaries

The product requirements document governs behavior and accessibility. The visual concept does not change data collection, planning, progression, privacy, or recovery rules. Do not introduce streak loss, negative rewards, shame language, or automatic task carry-forward. Game terms and illustrations remain optional presentation layers; plain labels preserve the same functionality.

The user clarified on 11 November 2026 that iPhone is the primary device; this supersedes the earlier Mac-first assumption. LifeResets is iPhone-first with full Mac support. Keep streak assumptions out of the product. Do not use existing anime characters, settings, logos, or art.

Discovery Q104/Q112/Q114 also asks for a dark, cinematic System interface and an evolving original Hunter character. This differs from the supplied warm Inkpop visual concept. Keep the current daily planner calm and legible; record a separate, optional System/character appearance as future design work. It must preserve the same controls and behavior and use original art. Neither the optional skin nor cinematic effects are implemented yet.

## iPhone priority

- Keep primary actions reachable with one hand; use a compact bottom navigation for the main screens.
- Respect display cutouts and home-indicator safe areas; keep controls at least 44 CSS pixels high.
- Avoid horizontal scrolling and prevent iOS input zoom by keeping form text at 16px or larger.
- Keep the PWA useful at narrow phone widths and in standalone display mode; Mac remains a supported workspace.
- Voice input must use confirmed on-device recognition only. If unavailable, point to iOS keyboard dictation; never silently fall back to cloud recognition.
- Spoken answers start only after the user taps Read aloud.

## Implemented in the daily-planning increment

- Inkpop color tokens, ink outlines, hard shadows, rounded cards, and an original static sprout illustration.
- Responsive capacity and energy planner with clear task selection, completion, deferral, and drop controls.
- Light/dark appearance, reduced-motion, and standard-language controls saved in the current browser.
- Recovery suggestions that require an explicit user choice, with no missed-day penalty or automatic carry-forward.
- iPhone-safe viewport, bottom navigation, and a compact character profile with skills, milestones, and visible rank rules.
- Voice entry uses the Web Speech API only when its on-device mode is available; the transcript stays editable and unsaved until submission.

Animation, haptics, a full mascot expression set, theme customization, scalable text validation to 200%, physical iPhone screen-reader testing, and user testing remain future design work.
