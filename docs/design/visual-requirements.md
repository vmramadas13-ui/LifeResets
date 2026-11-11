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

The concept's mobile-first audience and streak assumptions are not adopted as product requirements. LifeResets remains a Mac-first, responsive personal workspace. Do not use existing anime characters, settings, logos, or art.

## Implemented in the daily-planning increment

- Inkpop color tokens, ink outlines, hard shadows, rounded cards, and an original static sprout illustration.
- Responsive capacity and energy planner with clear task selection, completion, deferral, and drop controls.
- Light/dark appearance, reduced-motion, and standard-language controls saved in the current browser.
- Recovery suggestions that require an explicit user choice, with no missed-day penalty or automatic carry-forward.

Animation, haptics, a full mascot expression set, theme customization, scalable text validation to 200%, and user testing remain future design work.
