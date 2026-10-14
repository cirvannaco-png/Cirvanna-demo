# Wardrobe service

**Owner:** User wardrobe and wardrobe-item lifecycle. **Status:** scaffold only.

Own wardrobe records and user-authorized item relationships. Reuse catalog contracts; do not clone garment domain models or let other services write directly to wardrobe tables. Treat user photos, body measurements and wardrobe history as sensitive personal data.