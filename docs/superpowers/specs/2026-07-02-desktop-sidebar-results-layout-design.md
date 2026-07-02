# Desktop Sidebar and Results Layout Design

## Goal

Fix the results page visual overflow shown in the screenshot and update navigation so desktop uses a wider collapsible sidebar while mobile keeps the existing bottom navigation.

## Scope

- Desktop navigation becomes a left sidebar with a brand area at the top, wider expanded width, lower navigation button placement, and a collapsible icon-only state.
- Mobile navigation keeps the current bottom tab bar behavior and does not gain a drawer.
- The results page layout is corrected so filters, action buttons, table, and detail panel stay inside their containers across desktop, tablet, and mobile widths.
- Existing API calls, page IDs, button handlers, auth behavior, and no-build static frontend architecture remain unchanged.

## Root Cause Summary

The screenshot shows the results filter grid using too many fixed tracks for the available content width. The final action buttons can overflow the card and visually collide with the detail panel. The desktop nav also uses the same compact rail width intended for a simple icon/text strip, leaving no room for brand content or comfortable labels.

## Design

### Navigation

Desktop (`min-width: 900px`) will use an expanded sidebar around `184px` wide. The sidebar will include:

- Brand block at the top with the existing search logo, product name `BidMonitor`, and subtitle `招标信息监控系统`.
- A collapse toggle near the brand block.
- Navigation buttons placed below the brand area with additional top spacing.
- Active and hover states that match the existing orange/neutral token system.

Collapsed desktop state will use an icon-only rail around `72px` wide:

- Text labels and subtitle are visually hidden.
- The brand reduces to the logo mark.
- Nav buttons keep `title` and `aria-label` affordances.
- The state is persisted in `localStorage`.

Mobile (`max-width: 720px`) keeps the bottom navigation. The desktop brand block and collapse toggle are hidden on mobile.

### Results Page

The results page will use a resilient layout:

- The filter bar will wrap controls using responsive grid tracks instead of one long fixed row.
- Search keeps priority width, select/text filters share compact tracks, and action buttons stay within the grid.
- The results shell will avoid horizontal page overflow by allowing the table wrapper to scroll internally and by bounding the detail panel.
- At narrower breakpoints, table and detail panel stack as they do today.

### JavaScript

Add small sidebar state functions:

- Initialize collapsed state on load from `localStorage`.
- Toggle `appShell`/`body` state class from the collapse button.
- Keep `showPage` behavior unchanged for navigation and page loading.

No backend API behavior changes are required.

## Testing

Add/update static frontend tests for:

- Sidebar brand markup exists.
- Collapse toggle exists and JavaScript persists state with `localStorage`.
- Desktop CSS has expanded and collapsed sidebar widths.
- Mobile CSS keeps bottom navigation.
- Results filter bar uses wrapping/responsive tracks and action buttons remain inside the filter grid.

Run the existing static frontend test suite and a targeted visual/manual check with the app served locally.
