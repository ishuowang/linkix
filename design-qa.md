# Linkix Design QA

## Evidence

- Source visual truth: `docs/reference/linkix-home-source.png`
- Browser-rendered desktop: `docs/screenshots/linkix-home-desktop.png`
- Browser-rendered mobile: `docs/screenshots/linkix-home-mobile.png`
- Full side-by-side comparison: `docs/screenshots/linkix-design-comparison.png`
- Focused hero comparison: `docs/screenshots/linkix-design-comparison-hero.png`
- Focused bot comparison: `docs/screenshots/linkix-design-comparison-bot.png`
- Comparison convention: source is on the left; implementation is on the right.

## Normalization

- Desktop CSS viewport: 1400 × 903 at device scale factor 1.
- Source pixels: 1400 × 903 after cropping the supplied 3680 × 2392 browser capture to the product canvas.
- Implementation pixels: 1400 × 903.
- Full comparison pixels: 2800 × 903.
- Mobile CSS viewport and implementation pixels: 390 × 844 at device scale factor 1; the full-page capture is 390 × 844.
- State: light theme, signed-out home, empty resolver, one representative local-history row.
- No density resampling was needed for the final desktop comparison.

## Findings

No actionable P0, P1, or P2 differences remain.

- Fonts and typography: the implementation uses local Noto Serif SC Variable and Noto Sans SC Variable files. Display/body hierarchy, optical weight, wrapping, line height, and letter spacing follow the source. The implementation is slightly crisper than the rasterized source capture, which is expected.
- Spacing and layout rhythm: the 756 px page frame, 520 px resolver/history column, hero position, rules, history density, bot grid, and footer align with the source at 1400 × 903. The mobile layout remains readable without horizontal overflow.
- Colors and tokens: warm ivory paper, near-black ink, muted body copy, terracotta action color, pale rules, and cyan status dot match the source. Muted and accent text are marginally darker to preserve legibility.
- Image quality and asset fidelity: the source contains upload placeholders rather than finished bot assets. The implementation replaces only those placeholders with a sharp, real Telegram QR linking to `@vid_dld_bot`; it does not fake a QR or product image. The DingTalk slot is explicitly disabled and uses a Phosphor icon.
- Copy and content: the primary Chinese copy is preserved. Dynamic history time differs from the static source time by design.

## Focused Evidence

- Hero comparison confirms the headline, platform row, input baseline, action alignment, hint, and history row at readable scale.
- Bot comparison confirms the divider, heading/body rhythm, 100 px card geometry, labels, QR treatment, and footer alignment.
- The only material content deviation in the bot region is intentional: a functional Telegram QR and an honest “即将接入” DingTalk state replace the design tool’s upload placeholders.

## Comparison History

1. Pre-comparison browser capture measured 1400 × 909 because the footer added six pixels beyond the source canvas. `page-frame` bottom padding was reduced from 26 px to 20 px. The revised browser capture is exactly 1400 × 903 and is the implementation used in all final comparisons.
2. The first 390 px responsive capture wrapped “再次查看” onto two lines. The final history action track was widened from 42 px to 50 px and the timestamp was right-aligned. The revised mobile evidence shows one-line controls and no horizontal overflow.
3. The final full-view and focused comparisons found no remaining P0/P1/P2 mismatch, so no further visual iteration was required.

## Interaction and Runtime Checks

- Tested filling the built-in example, submitting the resolver, loading the success state, updating local history, revisiting a history item, and rendering the disabled demo download state.
- Verified desktop and mobile responsive states in the browser.
- Browser console checked after the final navigation: 0 errors and 0 warnings.
- Frontend unit tests, production build, and static worker tests pass.

## Follow-up Polish

- P3: a future real DingTalk integration should replace the disabled card while retaining the current 100 px geometry.
- P3: capture a dedicated mobile design source if pixel-level mobile fidelity becomes a release requirement.

## Final Result

final result: passed
