# User Style Index (USI)

**Status:** explicit-preference alignment kernel implemented; profile persistence and outcome-based threshold validation are not certified.

USI compares a candidate's explicit attribute metadata with a user's active, declared positive style preferences. It produces a transparent alignment score and maps the result to a CaTaCaCi identity-alignment signal.

## Contract boundaries

- USI uses explicit style preferences only; it does not infer identity or culture from appearance or demographic proxies.
- NPL owns hard dislikes and permanent exclusions. USI cannot create or override NPL hard vetoes.
- Missing preferences or incomplete candidate metadata produce `UNKNOWN`/review.
- A below-threshold style match is a non-veto review signal, not a permanent block.
- The default threshold is an engineering default, not a calibrated probability or proven business optimum.
- Only CaTaCaCi CAL `SHOW` can authorize display.

## Verification

```bash
python -m unittest discover -s tests/architecture -v
python scripts/validate_architecture.py
```

Production promotion requires profile persistence/versioning, preference correction lifecycle, threshold validation against user outcomes, bias checks, and end-to-end CAL tests.
