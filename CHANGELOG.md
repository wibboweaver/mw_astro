# Changelog

## Imaging session planner — 2026-10-30

- Select an observation interval with two chart clicks; preview duration and exposure-only image count while choosing the stop time.
- Show ordered inline Observation Feedback for start/end altitude, local horizon, astronomical darkness, session duration, exposure count, late starts and obscured time.
- Use the same exposure-only count in the chart and feedback panel.
- Estimate broadband moonlight interference using Moon altitude, illumination and target separation. Show affected periods across the chart as a white, 50%-opaque, 8-pixel strip with a visibility checkbox.
- Show Moon phase and illumination at observation start, affected times clipped to the selected window, and overlapping duration/percentage. Wording explicitly identifies the selected observation window.
- Provide show/hide controls for the object trajectory, local horizon, minimum altitude and moonlight interference.
- Save and download accepted plans locally. Acceptance does not arm equipment or communicate with NINA.
- Add configurable active planning thresholds and remove obsolete entries from config.toml.
- Retry DSS2 colour images through the official CDS mirror, refresh cached requests on retry, and show an unavailable message rather than substitute imagery.

Validation: 211 tests passed; 1 live integration test deselected.
