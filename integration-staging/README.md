# Cirvanna source reconstruction staging

This directory contains extracted candidates from the merged source file. It is deliberately isolated from canonical application paths.

## Safety status
- No existing application file was overwritten.
- The CDIC v5 source fragment originally extracted as `requirements.txt` begins with a Python docstring delimiter and is not an installable pip requirements file. Its exact bytes are preserved as `source-fragment.txt`, and the source manifest records the original declared path separately from the staged path so dependency tooling does not attempt to install source text.
- Each source document/version has a separate directory.
- Repeated paths within a source section receive `.__duplicate_N` suffixes.
- These files are not yet certified, integrated, or production-ready.
- Some candidate configurations contain embedded local database/broker development credentials; externalize them through environment/configuration management and review them before promoting any candidate. The lightweight pattern scan does not certify database/broker URI safety.
- Review `source-manifest.json` before selecting canonical versions.

## Extraction counts

| Source section | Extracted candidates |
|---|---:|
| `./CDIC .txt` | 27 |
| `./CDIC V4.txt` | 0 |
| `./CDIC v5.txt` | 22 |
| `./CDIC.txt` | 15 |
| `./CFRP V6.txt` | 46 |
| `./EEPL V2.0.txt` | 12 |
| `./EEPL.txt` | 8 |
| `./FCI  (1).txt` | 0 |
| `./FCI .txt` | 11 |
| `./FCI V2.0.txt` | 14 |
| `./Fit Confidence Index repository .txt` | 11 |
| `./NPL V2.txt` | 8 |
| `./Tari improved .txt` | 20 |
| `./We have now.txt` | 27 |
| `./Xyra.txt` | 26 |
| `./``` fci-repo-.txt` | 0 |
| `./```.txt` | 20 |
| `./cirvanna skeleton 🩻🩻.txt` | 38 |
| `./cultural identity module .txt` | 26 |
| `./identity decision engine .txt` | 27 |
| `./skin analysis .txt` | 0 |
| `./skin analysis repo .txt` | 14 |
| `./virtual Tryon  (1).txt` | 27 |
| `./virtual Tryon  (2).txt` | 27 |
| `./virtual Tryon .txt` | 27 |
| `./virtual Tryon improved.txt` | 27 |
| `./virtual Twin .txt` | 0 |
| `./virtual twin  (1).txt` | 0 |
| `./virtual twin mixed format .txt` | 0 |
| `./wardrobe 2,3 and 4 .txt` | 52 |
| `./wardrobe part 1.txt` | 12 |

**Total extracted candidate files:** 544
