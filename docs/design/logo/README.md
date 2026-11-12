# Logo

**Chosen: v7, the always-on bd.** The b and d of botdesk share one loop, an infinity sign: your bots never clock off.

- Overview sheet: [v7/bd.png](v7/bd.png)
- Every file at a glance: [v7/assets.png](v7/assets.png)
- In real use: [v7/mockups.png](v7/mockups.png)

## The mark

- **Bowls:** two true circles, radius 15.5, centres 36 apart.
- **Crossing:** the inner tangent lines of the two circles, unbroken.
- **Stems:** rise from the outermost point of each circle, where it is exactly vertical, so there is no joint.
- **Line:** one even weight, round ends. 10.5 of 100 on its own; 14 inside the horizontal lockup so it matches the Geist SemiBold wordmark; 12–13 below 64px so it stays open.
- **Wordmark:** `botdesk`, lowercase, Geist SemiBold, tracking −0.045em, converted to outlines (no font needed).
- **Colours:** black `#000000`, white `#FFFFFF`, ultramarine `#3B30FF`.

All geometry lives in [v7/mark.js](v7/mark.js).

## Files (`v7/`)

| Need | Use |
|---|---|
| Logo on a website or doc | `svg/lockup-black.svg`, `svg/lockup-white.svg` (dark backgrounds), `svg/lockup-ultramarine.svg` |
| Square or tall space | `svg/lockup-stacked-black.svg`, `svg/lockup-stacked-white.svg` |
| The mark alone | `svg/mark-{black,white,ultramarine}.svg`, `png/mark-*-{64,128,256,512,1024}.png` (transparent) |
| Name alone | `svg/wordmark-{black,white}.svg` |
| App icon | `svg/app-icon.svg` (+ `-ultramarine`, `-white`), `png/app-icon-{16…1024}.png` (rounded corners) |
| iOS / app stores | `png/apple-touch-icon.png` (180, square), `png/app-store-1024.png` (square; the OS rounds it) |
| Browser tab | `favicon.ico` (16/32/48), `svg/favicon.svg` (switches black/white with the browser's theme) |
| Link previews | `png/og-image-1200x630.png`, `png/github-social-1280x640.png` |
| Social profiles | `png/avatar-800.png`, `png/banner-1500x500.png` |
| Raster lockups | `png/lockup-{black,white}-200h.png`, `png/lockup-stacked-{black,white}-600h.png` |
| Mockups | `mockups/*.png`: website hero, desktop dock, notification, sign-in, phone splash, social profile, laptop stickers, email signature |

## Rules

- Keep clear space of one bowl-height around the logo.
- Use the mark alone only at 16–64px or where the name is already present (app sidebar, favicon).
- Don't stretch, rotate, outline, add effects, or recolour outside black, white and ultramarine.

## Regenerating

1. Serve the design folder: `cd docs/design && python -m http.server 8765`.
2. Open `http://127.0.0.1:8765/logo/v7/tools/export.html` and run `JSON.stringify(await build())` in the console (or via Playwright); save the result as `export.json`.
3. `python docs/design/logo/v7/tools/write.py export.json` writes `svg/`, `png/` and `favicon.ico`.
4. Re-screenshot `bd.html`, `assets.html` and `mockups.html` (1600px wide, device scale); mockups are saved per element (`#landing`, `#dock`, …).

The export page loads opentype.js 1.3.4 and Geist 1.3.1 (SIL OFL) from jsDelivr.

## How we got here

Rounds v1–v6 were deleted once v7 was chosen. What they taught:

- Plain flat shapes and glossy gradient icons both felt cheap.
- A woven gap at the crossing read as a cut.
- Pointed, lemniscate-shaped bowls read as narrowed, sly eyes.
- Pen calligraphy didn't suit the brand.
- What worked: one bold, even line, round open bowls, nothing hidden.
