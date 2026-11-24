# Changelog

## 2026-11-24

- Show a named image-preview tab for each of two selected objects, with
  independent framing centres and deferred loading of the hidden preview.
- Simplify chart controls and add taller Clear objects / Clear timelines buttons.
  Show paired duration (HH:MM), image count and object size readouts; the second
  object's bracketed duration and count use timelines 2–3.
- Add Clear objects beside the chart's precipitation checkbox. Allow a third
  timeline with two selected targets, keeping calculations on the first two;
  deselecting any target clears all timelines and the previous report.
- Browse FITS folders recursively, with a configurable child-folder depth guard
  (fits_browser.max_folder_depth, default 3) and relative paths for duplicate names.
- Add a sortable FITS folder metadata table while preserving the separate
  single-file categorised view, and remove the Original header cards section.
- Allow a second selected planning target as a comparison trajectory.
- Reject malformed configuration sections and handle whitespace-only sequence
  messages without crashing the analyser.

## 2026-11-21

- Migrate active configuration to JSON, separate mandatory rules from relative
  preferences, and favour earlier dark starts for non-automated sessions.

- Replace Moon-first interval selection with configurable relative weights for
  integration, altitude, transit, Moon, cloud, precipitation and start time.

- Store the supplied rig inventory and add Choose intervals with automatic
  report generation and Suggested Session Parameters.

- Remove the sequence review checklist to keep the analyser focused on capture
  summaries, timing and sequence structure.

- Add compact capture and review summaries, session finish projections, and
  consistent Name: [Enabled] Time: HH:MM headings to the sequence analyser.

- Simplify the sequence tree into Conditions, Items and Triggers sections with
  real entry counts, readable settings and complete multiline messages.

- Include configured camera cooling and warming durations (minutes) in sequence
  projections, marked as approximate allowances rather than guaranteed minima.

- Add collapsible sequence groups and persistent disable choices for groups,
  instructions and triggers. Exclude disabled branches from all projections.

- Show Unknown when sequence JSON does not establish enabled status, rather
  than incorrectly reporting Yes; label these timings as assuming enabled.

- Add a Sequence analyser page for NINA advanced-sequencer JSON files, with
  instruction/trigger names, enabled state, loop-aware timing and short notes.

- Show startup data-check progress and remove the manual Earth-rotation panel.

- Check Earth-rotation data once at startup, reuse newer cached data across
  restarts, and refresh stale predictions automatically with an offline fallback.

## 2026-11-18

- Shorten capture guidance to four target-specific answers: capture, combine,
  emissions and synthetic S II. Keep sources separate and omit unnecessary
  synthetic-SHO instructions for broadband and Horsehead images.


- Prevent expired IERS predictions from crashing offline planning calculations.
  Use a shared, scoped Earth-rotation data context; warn when data are stale or
  the selected dates exceed coverage. Add an explicit refresh control and carry
  accuracy notices into exported plans.


- Replace the yes/no filter column with a capture approach: Broadband, Dual-band,
  Both, or Needs assessment.
- Add selected-target capture guidance and include it in imaging-plan exports.
- Distinguish source-backed line presence from missing line-flux ratios; explain
  DB2 limits, HOO and explicitly synthetic SHO, and additional S II capture.


| Date | Version | Changes |
|---|---|---|
| 2026-11-04 | alpha | Enlarged rating-circle digits in the app and reports and used a bundled scalable font for consistent rendering across platforms. |
| 2026-11-04 | alpha | Corrected Moon phase labels around principal events and widened report Status columns while retaining overall table width. |
| 2026-11-04 | alpha | Added configurable Night ratings based on continuous astronomical-night visibility, Moon interference and uncropped frame coverage; cloud cover and rain risk are independent of the score. |
| 2026-11-04 | alpha | Sorted targets by descending Night rating, followed by targets with missing assessment data and then zero-rated targets; retained target selection when ordering changes. |
| 2026-11-04 | alpha | Added configurable frame-coverage preferences, scoring curve and undersized-object score cap; included estimated object coverage and pixel dimensions in the target table and report. |
| 2026-11-04 | alpha | Replaced Observation Feedback with a generated Markdown imaging report, adjacent Generate report and Save report buttons, Capture Information (NINA), and advisory criteria tables with Status, Potential Impact and Notes. |
| 2026-11-04 | alpha | Added catalogue and actual frame-centre RA/Dec, frame angle, and a circular Night rating graphic to reports; replaced inline SVG rating graphics with embedded PNGs for reliable rendering. |
| 2026-11-04 | alpha | Distinguished astronomical twilight from night in chart shading, hover text and report assessments; combined Moon phase, separation, illumination and impact information into one panel. |
| 2026-11-04 | alpha | Removed Cloud cover and Rain risk columns and their table-specific display code from the target list; retained weather information in the chart and report. |
| 2026-11-04 | alpha | Preserved native Night rating progress bars and added Missing data labels for uncalculable ratings through a local Streamlit renderer fix; versioned the corrected frontend asset URLs to prevent stale browser caches. The reapplication script is scripts/fix_progress_placeholder.py. |
| 2026-11-04 | alpha | Added a Filter? target-table column and standardised filter wording to Dualband Filter; removed the filter-recommendation checkbox. |
| 2026-11-04 | alpha | Renamed the main page Astrophotography Planning, removed object-name lookup controls, added total chart coverage from 4 to 24 hours, and made exposure and minimum-altitude sliders advance in 10-second and 1-degree increments. |
| 2026-11-04 | alpha | Added configuration parameters for the target-list limit and visibility sampling interval; formatted observation durations and angular sizes with compact units. |
| 2026-11-03 | alpha | Consolidated Frame fit into one Pass/Fail observation criterion with coverage and approximate object pixel dimensions in its notes. |
| 2026-11-01 | alpha | Simplified chart titles, sidebar notes and image-panel text; added an altitude-over-time description below the object name. |
| 2026-11-01 | alpha | Added enlarged image previews and 75%, 50% and 33% crop previews, with remaining resolution and megapixels. |
| 2026-11-01 | alpha | Switched image previews to ESA DSS2 colour tiles; retained camera framing, rotation and image positioning. |
| 2026-11-01 | alpha | Added rotating camera-frame labels for field of view, resolution and arcseconds per pixel. |
| 2026-11-01 | alpha | Added Frame fit and usable observation Window columns; left-aligned Window values. |
| 2026-11-01 | alpha | Improved chart layers, horizon shading, Moon information and collapsible legend; added cloud-cover percentages to forecast blocks. |
| 2026-11-01 | alpha | Changed the start-time slider to 10-minute increments. |
| 2026-10-30 | alpha | Added hourly cloud forecasts and cloud-cover feedback for the selected observation window. |
| 2026-10-30 | alpha | Added chart-selected observation times, live duration and exposure counts, inline Observation Feedback, Moon interference estimates and configurable planning rules. |
| 2026-10-30 | alpha | Added local plan saving and downloading; fixed start and stop markers disappearing after chart updates. |
| 2026-10-29 | alpha | Established the initial working application. |
