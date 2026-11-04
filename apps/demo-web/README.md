# Demo web application

**Owner:** Presentation layer. **Status:** Static browser surfaces backed by service-owned APIs.

- `marketplace.html` is the public product-offer browser.
- `brand-portal.html` is the authenticated Brand Partner Portal.
- `founder-console.html` is the authenticated Founder Commerce Console.
- `assets/` contains shared presentation styles and portal API clients.

The Marketplace BFF serves these pages and assets from the same origin. Keep UI state, rendering, accessibility and API clients here. Do not implement preference enforcement, fit logic, database access, merchant authorization, product-display arbitration or founder policy in browser code. No privileged service tokens or mock production records belong here.
