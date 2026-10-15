# Cultural Identity Policy

**Status:** explicit-declaration-only policy kernel implemented; cultural rule catalog and service integration are not certified.

This module evaluates only requirements a user has explicitly declared. It supports hard required attributes, hard forbidden attributes, and soft preferences. A hard conflict blocks; incomplete candidate metadata routes a required check to review; soft conflicts remain explanatory and never become hard vetoes.

## Safety invariants

- Never infer culture, religion, ethnicity, or modesty requirements from appearance, skin tone, name, location, or demographic proxies.
- Keep each requirement tied to a user and declaration ID.
- One user's requirements cannot affect another user.
- A known hard forbidden-attribute conflict blocks even when other candidate metadata is incomplete.
- Passing this module is not display authorization. The consumer must combine it with other required gates and require CaTaCaCi CAL `SHOW`.

## Verification

```bash
python -m unittest discover -s tests/architecture -v
python scripts/validate_architecture.py
```

Production promotion requires a reviewed, versioned rule catalog, consent/declaration lifecycle, candidate metadata quality guarantees, audit delivery, and end-to-end CAL integration.
