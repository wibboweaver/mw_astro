# Automatic target discovery

The default source is a bundled, attributed OpenNGC snapshot (Mattia Verga and
contributors, CC BY-SA 4.0). No account, API key or user-provided list is needed.
Source revision and attribution: data/openngc/SOURCE.json and ATTRIBUTION.md.

The default pool includes deep-sky objects with published common names or
Messier numbers. Select **All deep-sky objects** to search the full supported
NGC/IC catalogue and addendum. Stars, duplicates and nonexistent entries are
excluded. Common names are retained verbatim; identifiers disambiguate them.
Objects without a common name use a Messier number or catalogue identifier.

The app computes tracks for the selected site/date/start/window and applies
minimum altitude AND the interpolated custom horizon at the same sample.
During window: at least one clear sample. At start: first sample clear.
Throughout window: every sample clear. Touching an obstruction is excluded.
No custom profile means a flat 0-degree horizon. These are sampled tests and
do not guarantee uninterrupted clearance between samples.

All candidates are tested before limiting the list to 100. Results are ranked
by most qualifying samples, then peak altitude, then name. This is visibility
ranking only, not a measure of photographic brightness or field-of-view fit.
Search results are cached; selecting an object requires no network query or
track recalculation. The chart, horizon overlay and live readouts are retained.

**Custom CSV** remains optional for a personal list of up to 100 objects.
Columns: common_name,object_id,ra_deg,dec_deg. Coordinates may be omitted
together; SIMBAD resolves and caches them. Custom CSV names must be unique.
Local targets.csv or a sidebar upload is used only in Custom CSV mode.

## Reference images

The selected target's coordinates request a 600×600 DSS2 colour JPEG from
CDS HiPS2FITS. Images are cached in memory for seven days (up to 100 cutouts).
No observing-site coordinates are sent. The local catalogue stores no images.
Fit target uses OpenNGC's major axis plus 50% padding, limited to 0.25–10°;
unknown size defaults to 1°. Override the field or hide the image in the sidebar.
This is a survey reference, not a simulation of your camera's field of view.
An unavailable image does not remove the chart or interrupt target filtering.

Image credits: Digitized Sky Survey – STScI/NASA; coloured and HiPS-generated
by CDS. This application uses hips2fits, a service provided by CDS.
Service: https://alasky.cds.unistra.fr/hips-image-services/hips2fits
DSS copyright: https://archive.stsci.edu/dss/copyright.html

## Manual lookup

Use **Object name / ID** above the target selector to enter any SIMBAD name or
catalogue ID. Successful lookups are cached; changing the date, site or horizon
reuses the resolved coordinates. The target stays selected across reruns.
Manual lookup also works with an empty custom list or no eligible automatic
results. It displays the requested object even when it fails the visibility
limits, with a sidebar warning; the minimum-altitude/horizon lines remain.
Switch back to **Visible targets** for the filtered, A–Z dropdown. Ranking still
chooses the best 100 automatic results before they are alphabetized for display.

## Angular size

The Object size box shows OpenNGC's major × minor dimensions, with degrees,
arcminutes or arcseconds chosen by the major axis. If only the major axis is
published, only that value is shown. Unknown sizes are marked Unavailable;
image field of view is never substituted for object size. Common NGC/IC ID
spacing and leading zeros, plus Messier aliases, are normalized for manual
lookups. Time below the chart is HH:MM in the configured local timezone.

## Saved sidebar settings

Sidebar changes are written immediately to config.toml. New sessions restore
latitude/longitude, horizon filename, evening date, start hour AND minute,
minimum altitude, visibility mode, catalogue source/scope, preview toggle and
image field of view. Elevation remains available as observatory.height_m in
the config and is used in calculations, but has no sidebar control.

A valid uploaded CSV is kept locally in catalogues/last_upload.csv so Custom CSV
also works after reopening. Removing the uploader widget does not lose the
saved file. Original targets.csv is untouched. Each update merges only changed
settings, preserves unrelated config entries, and replaces the config atomically.
Write failures are shown in the sidebar. The selected evening date is retained
literally; advance it when planning a different night. A missing horizon file
shows a warning and does not overwrite its saved filename.

## Observation intervals and exposures

Click twice inside the plot to place two persistent purple vertical lines. The
order of clicks does not matter. Duration is actual elapsed time, even across
midnight or a daylight-saving transition. A third click starts a new interval;
Clear interval removes both lines. Hover values still update independently.

Exposure (seconds), directly below Start time in the sidebar, is saved to the
config. Default: 180 seconds (editable planning value). The image estimate is
floor(selected duration / exposure) and counts only complete exposures, with
no download, dithering, autofocus or other overhead. It does not clip the
chosen interval to the horizon; select the usable part of the track.

Selected lines are retained in browser session storage for the same target
and chart time range, so adjusting exposure immediately updates the count.
Changing target or the chart's date/time range starts a separate interval.

The read-only checkbox under the chart recommends the ZWO DB2 2-inch Dual-Band
Filter for OpenNGC emission-line types EmN, HII, PN and SNR. It is clear for
broadband objects and ambiguous/unknown classifications. Hover its help icon
for the reason. This is a conservative type-based recommendation, not a claim
that the filter is installed. Generic Neb or Cl+N types are insufficient for
an automatic recommendation; reflection and emission components can differ.
Manufacturer guidance: https://www.zwoastro.com/product/duo-band-filters/

## Astronomical night

A pale blue-grey rectangle shades times when the geometric solar centre is
below -18°. Computation uses the observing site and selected date, in Astropy,
without atmospheric refraction or network downloads. Solar crossings are
bracketed at two-minute intervals and refined to within one second.

The times below the reference-image links describe the selected evening's
noon-to-noon night in the configured local timezone. Shading is clipped to the
chart range; a longer chart can include several dark intervals. The custom
terrain horizon and the target minimum altitude do not change twilight times.
Summer dates without astronomical darkness and continuous polar darkness
are reported explicitly instead of inventing start/end times. This shading
does not change the existing target filters, chosen interval or image count.
Definition: https://aa.usno.navy.mil/faq/RST_defs

## Sidebar sliders

Start time uses a local-time slider from 00:00 to 23:59 in one-minute steps.
Exposure uses a slider of common exposure durations, from 0.1 to 3600 seconds;
any existing custom configured duration is retained as an additional option.
Minimum altitude uses a 0–90° slider in 0.1° steps. These controls retain the
existing automatic config saving, twilight calculation and image-count updates.

The table below the chart lists the same qualifying targets as the dropdown, in A–Z order. It includes catalogue ID, published common name (or dropdown label), next upper meridian transit after the sidebar start time (local HH:MM), angular size, classification, distance, and J2000 RA/Dec. Transit uses apparent coordinates and sidereal time, independently of the chart sampling interval. The bundled OpenNGC files have no distance column: distances remain Unavailable, without inferring them from redshift. Unknown custom targets retain their names and coordinates with unavailable catalogue metadata. Table calculations are cached so selecting a different target does not recalculate the entire list.

Sidebar controls are grouped into Plan, Site, Targets and Frame tabs. Frame accepts effective focal length, physical sensor width/height in millimetres, and camera width/height in pixels. Defaults are 550 mm, 23.5 × 15.7 mm, and 6248 × 4176 pixels for the Z4/ASI2600. Pixel dimensions describe the full sensor readout; they do not alter angular coverage. Physical field is 2 atan(sensor dimension / (2 focal length)). The rectangle uses the DSS2 TAN projection at its target centre. Dragging translates the image beneath the fixed frame immediately, with no network calls. The displayed survey is a finite cutout: moving it far enough exposes its edges; a larger Image field of view requests more sky. The image offset is remembered for each target and cutout size within the browser session, including across rotation changes. Centre image resets that offset. There are no direction labels or zoom controls. Rotation redraws locally during input and saves on release. Equipment and rotation persist in config.toml; obsolete frame_zoom entries are ignored. Sensor dimensions and rotation do not replace the selected target coordinates with new pointing coordinates. Initial field fits the padded diagonal at all rotations, up to the existing 10° service limit.

The visible-target table is now the selector, above the charts; the dropdown is removed. Select one row to update the altitude plot, DSS2 image, framing and filter recommendation. The table supports column sorting, search and CSV export. Row identities remain tied to original data positions even after client-side sorting. Changes to the eligible list reset stale indices and retain the chosen target by name if still visible, otherwise select the first A–Z target. Manual lookup preserves the table choice. Clearing the selected row hides the chart until another is selected. Streamlit 1.66 or later is required for the initial highlighted row.
