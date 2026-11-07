# Living Filters — Physical Android Acceptance Checklist

**Status: not physically verified.** Automated viewport emulation is not a substitute for running the feature on a real Android device.

## Target test environment

- Device: Android 10 handset (primary target: the user's TECNO KB8).
- Browser: production-supported Chrome version; record the exact version.
- Orientations: portrait and landscape.
- Network: normal Wi-Fi/mobile data, throttled connection, offline, then reconnect.
- Build: record Git commit SHA, deployed URL and test date.

## Acceptance checklist

| ID | Test | Expected result | Evidence |
|---|---|---|---|
| LF-01 | Cold launch in portrait | Filter view loads without clipped controls or horizontal scrolling | Screenshot |
| LF-02 | Rotate to landscape and back | Controls reflow; selected filters and state remain intact | Screen recording |
| LF-03 | Open/close filter panels | No trapped scroll, clipped modal, or inaccessible close action | Screen recording |
| LF-04 | Apply, clear, and re-apply filters | Results and selected-state indicators remain consistent | Screenshot |
| LF-05 | Use sliders, chips, and multi-select controls | Touch targets respond reliably; no accidental adjacent selection | Screen recording |
| LF-06 | Open keyboard on text/search fields | Inputs remain visible; submit and clear actions are reachable | Screenshot |
| LF-07 | Use Android Back gesture/button | Closes the topmost panel first; does not unexpectedly exit or lose selections | Screen recording |
| LF-08 | Slow network and offline transition | Loading, empty, retry, and offline states are understandable; no stale success state | Screen recording |
| LF-09 | Privacy blur enabled | Protected content remains blurred in the UI and is not briefly exposed during load/transition | Before/after screenshots |
| LF-10 | Navigate away and return | Blur and consent state follow the documented persistence rules; no accidental reset | Screen recording |
| LF-11 | Camera permission denied, granted, then revoked (where camera is used) | Feature fails closed when denied/revoked; no camera capture before explicit grant | Permission screenshots |
| LF-12 | Repeated use for five minutes | No crash, runaway memory growth, frozen scroll, or severe frame drops | Device observation + logs |
| LF-13 | Accessibility | Text readable at system font scaling; controls have labels and visible focus/pressed states | Screenshot |
| LF-14 | Data/privacy inspection | No image or camera payload is sent before consent; requests use HTTPS and contain no access token in URL | Network capture with secrets redacted |

## Automated coverage

CI runs Chromium layout checks at 320×640, 360×800, 393×873, 412×915, and 844×390 against the Marketplace and Wardrobe demo pages. This catches horizontal overflow only. It does not validate touch response, the physical camera pipeline, Android permissions, GPU behavior, memory pressure, or blur timing.

## Sign-off

- [ ] All LF-01…LF-14 passed on a physical Android handset.
- [ ] Failed cases have issue links and reproducible steps.
- [ ] Screenshots/video and redacted network evidence are attached.
- [ ] Reviewer confirms blur never flashes protected content.
- [ ] Release owner accepts remaining limitations.

**Do not mark physical Android QA complete from CI emulation alone.**
