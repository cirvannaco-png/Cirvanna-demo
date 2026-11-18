# Cirvanna demo web application

**Owner:** Presentation layer. **Status:** responsive Sanctuary and Twin-onboarding experience plus separate Marketplace and Wardrobe demo surfaces.

## Pages and route ownership

- `sanctuary.html`: Primal Atelier × Living Couture entry experience, served by the Marketplace BFF at `/sanctuary.html`.
- `twin-onboarding.html`: authenticated capability check plus an owner-scoped, metadata-only saved-Twin lookup, served by the BFF at `/twin-onboarding.html`.
- `wardrobe.html`: owner-scoped Wardrobe, PNELLY styling and explicit learning controls, served by the BFF at `/wardrobe` and `/wardrobe.html`.
- `marketplace.html`: CAL-governed Marketplace, PNELLY discovery and the separate Look It workflow, served at `/` and `/marketplace.html`.

## Design and safety boundaries

The shared Sanctuary design tokens preserve Cirvanna's obsidian black, warm white, gold and purple palette. Electric blue is reserved for the human-shaped Blue Flame / Twin identity transition.

The onboarding page reads the authenticated `GET /api/virtual-twin/capabilities` and `GET /api/virtual-twin/me` BFF routes. The second route returns only owner-scoped registry metadata after consent and private asset checks; it does not return mesh/source asset IDs or preview bytes. The page does not collect, upload or persist images or video and does not create consent receipts. Its capture action is intentionally disabled: the current Virtual Twin API supports only a single still-image ephemeral pose skeleton, rejects video, and does not generate or persist a full-body Twin. Persistent generation, independent mesh validation, owner-scoped registry access, private asset storage and the complete capture BFF workflow remain release blockers.

Keep presentation code in this directory. Do not put identity arbitration, consent authority, image retention, fit logic, database access, product truth or CAL policy in browser code.

## Validation

Run the page contract and responsive browser suites from the repository root:

```bash
python -m pip install pytest playwright
python -m playwright install chromium
python -m pytest apps/demo-web/test_sanctuary_contract.py apps/demo-web/test_twin_onboarding_contract.py apps/demo-web/test_mobile_layouts.py -q
node --check apps/demo-web/assets/cirvanna-sanctuary.js
node --check apps/demo-web/assets/cirvanna-twin-onboarding.js
```

The BFF route tests live in `services/marketplace-bff/tests/test_main.py`. These checks validate page behavior and current API contract boundaries; they do not prove that a production identity provider or persistent Twin pipeline is deployed.
