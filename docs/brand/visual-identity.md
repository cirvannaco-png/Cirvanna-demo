# Cirvanna visual identity

**Direction:** Primal Atelier × Living Couture  
**Brand character:** premium, cinematic, intimate, confident, human, and quietly expressive.

Cirvanna's visual language should feel carefully composed rather than ostentatious. It combines the permanence of an atelier with the movement and individuality of personal style. Luxury comes from proportion, material, typography, consistency and considered detail—not from filling every surface with gold.

## Primary brand palette

| Role | Colour | Hex | Application |
|---|---|---:|---|
| Primary dark | Obsidian black | \`#080808\` | Main canvas, navigation, immersive product surfaces |
| Primary metallic | Cirvanna gold | \`#D6AE62\` | Actions, borders, selected states, emphasis and signature details |
| Primary light | White | \`#FFFFFF\` | Wordmark, high-contrast typography, clean surfaces and controls |

White is a core Cirvanna colour, not merely a temporary text colour. It gives the black-and-gold system clarity, air and precision.

## Supporting palette

| Role | Colour | Hex | Application |
|---|---|---:|---|
| Warm white | Atelier ivory | \`#F7F3ED\` | Softer light surfaces and warm editorial moments |
| Muted text | Warm grey | \`#B8B1A5\` | Secondary labels and explanatory copy on dark surfaces |
| Gold light | Champagne gold | \`#F3D99A\` | Gold highlights and accessible focus treatment |
| Gold deep | Bronze | \`#8E682F\` | Restrained borders and metallic depth |
| Purple | Atelier plum | \`#76518F\` | Secondary creative and sanctuary accents |
| Deep purple | Aubergine | \`#30213E\` | Supporting panels and atmospheric gradients |
| Blue Flame | Electric blue | \`#39A7FF\` | Reserved for the Blue Flame / Twin identity motif only |

The colour roles should remain stable across web and mobile. A feature may emphasize a subset of the palette, but it must not invent a competing product identity.

## Marketplace expression

The Marketplace is intentionally **black and gold first**, with white as its clarity layer:

- Obsidian is the dominant page and navigation canvas.
- Gold is reserved for primary actions, active states, pricing emphasis, outlines and small editorial details.
- White carries the wordmark, headings, product names and key information.
- Inputs and controls may use white or warm-white surfaces with dark text so they remain easy to scan and operate.
- Product photography must remain faithful to the actual product; avoid gold filters or overlays that distort colour.
- Purple is not a default Marketplace surface colour. It can appear only as a restrained accent where a connected Cirvanna experience calls for it.
- Blue is not a Marketplace accent and must not be used to imitate Twin availability.

## Wider Cirvanna experience

The primary black, gold and white identity applies across the platform. Supporting ivory, purple and material neutrals provide range between the Sanctuary, Wardrobe, PNELLY, Marketplace and Experience Lab without making each feature feel like a separate company.

The Blue Flame must remain the pre-Twin state until a persistent user-specific Twin has been generated, independently validated, stored privately, and rendered through a verified end-to-end lifecycle. Electric blue must not imply that those capabilities are active when they are not.

## Typography and composition

- Use an editorial serif for major statements and section titles.
- Use a highly legible sans-serif for navigation, controls, metadata, product details and body copy.
- Preserve generous spacing and strong hierarchy. Do not make every heading oversized.
- Prefer restrained radii, thin gold rules, controlled gradients and quiet material textures.
- Keep product imagery prominent and colour-accurate.
- Avoid dense gold-on-black body text at small sizes; white and warm neutrals carry longer copy.

## Interaction and accessibility

- Design mobile first, with usable touch targets and no horizontal page overflow at narrow widths.
- Provide visible keyboard focus, semantic labels, live status feedback and accessible names for icon-only controls.
- Respect \`prefers-reduced-motion\`; motion should explain hierarchy or state, not distract.
- Maintain sufficient contrast for text, borders, and disabled states. Gold is an accent, not a substitute for readable body text.
- Colour alone must never communicate status or authorization.

## Source tokens

The Sanctuary design tokens live in \`apps/demo-web/assets/cirvanna-sanctuary.css\`. The Marketplace's focused theme is declared in the inline style block in \`apps/demo-web/marketplace.html\`. Keep these token roles aligned when extending the shared design system.
