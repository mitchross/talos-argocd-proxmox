---
name: radar-local-alerts
description: "Use when changing radar-ng alerts. Preserve shared logic."
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [radar-ng, expo, notifications]
    related_skills: [homelab-app-development, expo-router]
---

# radar-ng local notifications

## When to Use

Use for local weather-alert policy, notification delivery, permissions, flood control or notification-tap navigation in radar-ng.

## Rules

- Read the checkout's `AGENTS.md` and locate its existing schedulers before editing. Ship user-facing changes in `web/` and `frontend/` together.
- Keep pure alert policy under `web/src/shared/` and re-export it from `frontend/src/lib/`, following `warningTags.ts`; do not copy mapping tables between clients.
- Read the point `/api/alerts` path, not just `/api/alerts/map`, when looking for CAP metadata. The point API preserves full NWS features while the map intentionally slims properties. Preserve `parameters`, `references`, IDs and geometry in client adapters.
- Deduplicate NWS revisions by both reference identifiers and VTEC event identity. Ignore VTEC action changes, but retain office, phenomenon, significance, event number and year. Record suppressed revisions and overflow before awaiting delivery so concurrent checks cannot flood retries.
- Check `parameters.thunderstormDamageThreat` for destructive Severe Thunderstorm Warnings. Emergencies may appear in the headline while the event remains a Warning.
- Create Android notification channels before requesting permission for a first-use test alert. Expo's system permission and native-module failures must produce a visible failure, not a false sent confirmation.
- Use the existing rain-alert notification handler and background wake rather than adding a second owner. Background wakes are OS-controlled (15 minutes at best), not reliable emergency push delivery; explain that limitation in settings and handoff.
- For browsers, use a service worker registration on mobile and wait for it to become active before immediate test delivery. Handle notification taps both in an existing window (postMessage) and a newly opened window (validated bounds in URL).
- For Expo, handle both live response listeners and the last response after navigation is ready. Clear consumed responses, remove listeners on cleanup, and fit polygon bounds using the existing radar focus mechanism.
- Test the pure planner, actual adapter delivery boundary, warm/cold tap paths and permission rejection. Report lack of physical-device verification and the required native rebuild. System sounds do not guarantee distinct tones or bypass Do Not Disturb; describe fallbacks plainly.
