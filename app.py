"""SIMBAD lookup and altitude planning. Run with: streamlit run app.py."""
from datetime import date as calendar_date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from pathlib import Path
import hashlib
import json

from targets import Target, parse_targets, resolve_targets
from visibility import calculate_tracks, filter_tracks, discover_tracks, MODES
from catalogue import load_catalogue
from target_table import target_table
import framing
if getattr(framing, "_loaded_source_stamp", None) != (Path(framing.__file__).stat().st_mtime_ns, Path(framing.__file__).with_name("framing.js").stat().st_mtime_ns):
    import importlib
    importlib.reload(framing)
from framing import field_of_view, fit_preview_field, framing_data, render_framing
from astronomical_night import night_for_chart, night_text
from object_sizes import object_size_label
from filter_recommendations import recommend_db2
from reference_images import fetch_preview, preview_fov, PreviewError

import importlib
import interactive_chart
from streamlit.components.v1 import html
import streamlit as st

import configuration
if getattr(configuration, "_loaded_source_stamp", None) != Path(configuration.__file__).stat().st_mtime_ns:
    importlib.reload(configuration)

from configuration import (load_settings, save_settings_changes, save_uploaded_catalogue,
                           TARGET_SOURCES, CATALOGUE_SCOPES, IMAGE_FIELDS)
from objects import resolve_object
from horizon import available_horizons, load_horizon, horizon_altitudes

@st.cache_resource(max_entries=1, show_spinner=False)
def chart_renderer(source_version):
    # Keep the loaded Python renderer in sync with edits during a running session.
    return importlib.reload(interactive_chart).chart_html


@st.cache_data(show_spinner=False)
def cached_coordinates(targets):
    return resolve_targets(targets, resolve_object)


@st.cache_data(show_spinner=False, max_entries=12)
def cached_tracks(targets, latitude, longitude, height, start, duration, step):
    return calculate_tracks(targets, latitude, longitude, height, start, duration, step)


@st.cache_data(show_spinner=False)
def cached_catalogue(named_only):
    return load_catalogue(named_only)


@st.cache_data(show_spinner=False, max_entries=4)
def cached_discovery(targets, latitude, longitude, height, start, duration, step, minimum, profile, mode):
    return discover_tracks(targets, latitude, longitude, height, start, duration, step, minimum, profile, mode)


@st.cache_data(show_spinner=False, max_entries=100)
def cached_lookup(name):
    result = resolve_object(name)
    return Target(name, str(result["name"]), float(result["ra_deg"]), float(result["dec_deg"]))


@st.cache_data(show_spinner=False, ttl=604800, max_entries=100)
def cached_preview(ra_deg, dec_deg, fov_deg):
    return fetch_preview(ra_deg, dec_deg, fov_deg)


@st.cache_data(show_spinner=False, max_entries=32)
def cached_night(evening_date, zone_name, chart_start, chart_end, latitude, longitude, height):
    return night_for_chart(evening_date, zone_name, chart_start, chart_end, latitude, longitude, height)


@st.cache_data(show_spinner=False, max_entries=12)
def cached_target_table(targets, start, longitude, timezone):
    return target_table(targets, start, longitude, timezone)


def persist_sidebar(field, key):
    value = st.session_state[key]
    if field in ("camera_width_px", "camera_height_px"):
        value = int(value)
    changes = ({"start_hour": value.hour, "start_minute": value.minute}
               if field == "start_time" else
               {field: value.isoformat() if field == "evening_date" else (value or "") if field == "horizon_file" else value})
    try:
        save_settings_changes(**changes)
        st.session_state.pop("settings_save_error", None)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        st.session_state["settings_save_error"] = f"Settings could not be saved: {exc}"


def persist_framing(field, component_field):
    value = st.session_state.get("camera_framing", {}).get(component_field)
    if value is None:
        return
    try:
        save_settings_changes(**{field: float(value)})
        st.session_state.pop("settings_save_error", None)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        st.session_state["settings_save_error"] = f"Settings could not be saved: {exc}"


def persist_upload():
    upload = st.session_state.get("sidebar_upload")
    if upload is not None:
        try:
            save_uploaded_catalogue(upload.getvalue())
            st.session_state.pop("settings_save_error", None)
        except (OSError, ValueError, UnicodeError) as exc:
            st.session_state["settings_save_error"] = f"Catalogue could not be saved: {exc}"


st.set_page_config(layout="wide")
st.title("Astronomical targets")
try:
    settings = load_settings()
except (OSError, ValueError, TypeError, KeyError) as exc:
    st.error(f"Check config.toml: {exc}")
    st.stop()

zone = ZoneInfo(settings.timezone)
height = settings.height_m
horizon_profile = None
with st.sidebar:
    plan_tab, site_tab, targets_tab, frame_tab = st.tabs(["Plan", "Site", "Targets", "Frame"])
    with plan_tab:
        date = st.date_input("Evening date",
            calendar_date.fromisoformat(settings.evening_date) if settings.evening_date else datetime.now(zone).date(),
            key="sidebar_date", on_change=persist_sidebar, args=("evening_date", "sidebar_date"))
        start_time = st.slider("Start time (local)", min_value=time(0, 0), max_value=time(23, 59),
            value=time(settings.start_hour, settings.start_minute), step=timedelta(minutes=1), format="HH:mm",
            key="sidebar_start_time", on_change=persist_sidebar, args=("start_time", "sidebar_start_time"))
        exposure_steps = sorted(set([0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 15.0, 20.0, 30.0, 45.0,
            60.0, 90.0, 120.0, 180.0, 240.0, 300.0, 360.0, 480.0, 600.0, 900.0,
            1200.0, 1800.0, 3600.0, float(settings.exposure_seconds)]))
        exposure = st.select_slider("Exposure (seconds)", options=exposure_steps,
            value=float(settings.exposure_seconds), format_func=lambda value: f"{value:g}",
            key="sidebar_exposure", on_change=persist_sidebar, args=("exposure_seconds", "sidebar_exposure"))
        minimum_altitude = st.slider("Minimum altitude (°)", 0.0, 90.0,
            value=float(settings.minimum_altitude_deg), step=0.1, format="%.1f°",
            key="sidebar_minimum", on_change=persist_sidebar, args=("minimum_altitude_deg", "sidebar_minimum"))
        visibility_mode = st.selectbox("Target visibility", MODES, index=MODES.index(settings.visibility_mode),
            key="sidebar_visibility", on_change=persist_sidebar, args=("visibility_mode", "sidebar_visibility"))
        st.caption("Visibility is sampled at the configured interval. During window requires both limits at the same time.")
        st.caption(f"Local timezone: {settings.timezone}; duration: {settings.duration_hours:g} hours.")
    with site_tab:
        latitude = st.number_input("Latitude (° north)", -90.0, 90.0,
            value=None if settings.latitude_deg is None else float(settings.latitude_deg), format="%.6f",
            key="sidebar_latitude", on_change=persist_sidebar, args=("latitude_deg", "sidebar_latitude"))
        longitude = st.number_input("Longitude (° east)", -180.0, 180.0,
            value=None if settings.longitude_deg is None else float(settings.longitude_deg), format="%.6f",
            key="sidebar_longitude", on_change=persist_sidebar, args=("longitude_deg", "sidebar_longitude"))
        horizon_options = [None, *[path.name for path in available_horizons()]]
        saved_horizon = settings.horizon_file or None
        if saved_horizon not in horizon_options:
            st.warning(f"Saved horizon {saved_horizon} is missing. Choose a new horizon.")
            saved_horizon = None
        horizon_name = st.selectbox("Custom horizon", horizon_options,
            index=horizon_options.index(saved_horizon),
            format_func=lambda name: "None" if name is None else Path(name).stem,
            key="sidebar_horizon", on_change=persist_sidebar, args=("horizon_file", "sidebar_horizon"))
        horizon_file = next((path for path in available_horizons() if path.name == horizon_name), None)
    with targets_tab:
        target_source = st.selectbox("Target source", TARGET_SOURCES, index=TARGET_SOURCES.index(settings.target_source),
            key="sidebar_source", on_change=persist_sidebar, args=("target_source", "sidebar_source"))
        uploaded = None
        scope = settings.catalogue_scope
        if target_source == "Automatic catalogue":
            scope = st.selectbox("Catalogue scope", CATALOGUE_SCOPES, index=CATALOGUE_SCOPES.index(settings.catalogue_scope),
                key="sidebar_scope", on_change=persist_sidebar, args=("catalogue_scope", "sidebar_scope"))
            st.caption("OpenNGC • Best 100 by visibility, displayed A–Z.")
        else:
            uploaded = st.file_uploader("Target catalogue (CSV, up to 100)", type=["csv"],
                key="sidebar_upload", on_change=persist_upload)
            if st.button("Refresh coordinates"):
                cached_coordinates.clear()
    with frame_tab:
        show_preview = st.checkbox("DSS2 reference image", value=settings.show_preview,
            key="sidebar_preview", on_change=persist_sidebar, args=("show_preview", "sidebar_preview"))
        image_field = settings.image_field
        if show_preview:
            image_field = st.selectbox("Image field of view", IMAGE_FIELDS, index=IMAGE_FIELDS.index(settings.image_field),
                key="sidebar_image_field", on_change=persist_sidebar, args=("image_field", "sidebar_image_field"))
        st.subheader("Telescope and camera")
        focal_length = st.number_input("Effective focal length (mm)", 20.0, 20000.0,
            value=float(settings.focal_length_mm), step=5.0,
            key="sidebar_focal_length", on_change=persist_sidebar, args=("focal_length_mm", "sidebar_focal_length"))
        sensor_width = st.number_input("Sensor width (mm)", 0.1, 100.0,
            value=float(settings.sensor_width_mm), step=0.1,
            key="sidebar_sensor_width", on_change=persist_sidebar, args=("sensor_width_mm", "sidebar_sensor_width"))
        sensor_height = st.number_input("Sensor height (mm)", 0.1, 100.0,
            value=float(settings.sensor_height_mm), step=0.1,
            key="sidebar_sensor_height", on_change=persist_sidebar, args=("sensor_height_mm", "sidebar_sensor_height"))
        camera_width = st.number_input("Camera width (pixels)", 1, 100000,
            value=settings.camera_width_px, step=1,
            key="sidebar_camera_width", on_change=persist_sidebar, args=("camera_width_px", "sidebar_camera_width"))
        camera_height = st.number_input("Camera height (pixels)", 1, 100000,
            value=settings.camera_height_px, step=1,
            key="sidebar_camera_height", on_change=persist_sidebar, args=("camera_height_px", "sidebar_camera_height"))
        fov_width, fov_height = field_of_view(focal_length, sensor_width, sensor_height)
        st.metric("Camera field of view", f"{fov_width:.2f}° × {fov_height:.2f}°")
        st.caption(f"{camera_width} × {camera_height} pixels")
        st.caption("Defaults: Sharpstar Z4, 550 mm; ASI2600 sensor, 23.5 × 15.7 mm. Use the effective focal length including any reducer. Drag the reference image to position the object; rotate the frame below it.")
    if not settings.evening_date:
        try:
            save_settings_changes(evening_date=date.isoformat())
        except (OSError, ValueError) as exc:
            st.session_state["settings_save_error"] = f"Settings could not be saved: {exc}"
    if "settings_save_error" in st.session_state:
        st.error(st.session_state["settings_save_error"])
    if horizon_file is not None:
        try:
            horizon_profile = load_horizon(horizon_file)
        except (OSError, ValueError) as exc:
            st.error(f"Cannot load {horizon_file.name}: {exc}")
            st.stop()

selection_mode = st.radio("Find a target", ["Visible targets", "Object name / ID"], horizontal=True)
if latitude is None or longitude is None:
    with st.sidebar:
        st.warning("Enter latitude and longitude to display targets.")
    st.stop()
start = datetime.combine(date, start_time, tzinfo=zone)
if selection_mode == "Object name / ID":
    with st.form("manual_lookup"):
        object_name = st.text_input("Object name or catalogue ID", placeholder="M31 or Iris Nebula")
        lookup = st.form_submit_button("Look up")
    if lookup:
        name = object_name.strip()
        st.session_state.pop("manual_target", None)
        if not name:
            st.warning("Enter an object name or catalogue ID.")
        else:
            try:
                with st.spinner("Querying SIMBAD…"):
                    st.session_state["manual_target"] = cached_lookup(name)
            except ValueError as exc:
                st.error(str(exc))
            except Exception:
                st.error("SIMBAD lookup failed. Check your connection and try again.")
    target = st.session_state.get("manual_target")
    if target is None:
        st.stop()
    selected = target.common_name
    tracks = cached_tracks((target,), latitude, longitude, height, start, settings.duration_hours, settings.step_minutes)
    if not filter_tracks(tracks, minimum_altitude, horizon_profile, visibility_mode):
        with st.sidebar:
            st.warning("This object does not meet the current visibility limits.")
else:
    try:
        if target_source == "Automatic catalogue":
            catalogue = cached_catalogue(scope == "Named and Messier objects")
        else:
            catalogue_text = uploaded.getvalue().decode("utf-8-sig") if uploaded else (Path(__file__).parent / settings.catalogue_file).read_text(encoding="utf-8-sig")
            catalogue = parse_targets(catalogue_text)
    except (OSError, ValueError, UnicodeError) as exc:
        st.error(f"Cannot load target catalogue: {exc}")
        st.stop()

    if not catalogue:
        st.warning("No target catalogue is supplied yet. Add up to 100 verified common names and SIMBAD IDs to targets.csv, or upload a CSV in the sidebar. See TARGETS.md for the format.")
        st.stop()

    with st.spinner("Loading target coordinates…"):
        targets, failures = (catalogue, ()) if target_source == "Automatic catalogue" else cached_coordinates(catalogue)
    if failures:
        with st.sidebar:
            st.warning(f"{len(failures)} target(s) could not be resolved and are excluded.")
            with st.expander("Coordinate errors"):
                for failure in failures:
                    st.text(failure)
    with st.spinner("Checking target visibility…"):
        if target_source == "Automatic catalogue":
            tracks = cached_discovery(targets, latitude, longitude, height, start, settings.duration_hours, settings.step_minutes,
                                      minimum_altitude, horizon_profile, visibility_mode)
            eligible = sorted(tracks, key=str.casefold)
        else:
            tracks = cached_tracks(targets, latitude, longitude, height, start, settings.duration_hours, settings.step_minutes)
            eligible = sorted(filter_tracks(tracks, minimum_altitude, horizon_profile, visibility_mode), key=str.casefold)
    with st.sidebar:
        st.caption(f"{len(eligible)} qualifying targets shown from {len(catalogue):,} catalogue entries.")
    if not eligible:
        st.warning("No targets meet the visibility limits.")
        st.stop()

    by_name = {item.common_name: item for item in targets}
    visible_targets = tuple(by_name[name] for name in eligible)
    remembered = st.session_state.get("selected_target")
    default_row = eligible.index(remembered) if remembered in eligible else 0
    # Reset row indices whenever identities/order change, retaining the target by name.
    identities = [(item.common_name, item.object_id, item.ra_deg, item.dec_deg) for item in visible_targets]
    table_key = "target_table:" + hashlib.sha256(json.dumps(identities).encode()).hexdigest()[:16]
    st.subheader("Visible targets")
    st.markdown("Select a row to view its chart and image.")
    selection = st.dataframe(cached_target_table(visible_targets, start, longitude, settings.timezone),
        key=table_key, hide_index=True, width="stretch", height=250,
        on_select="rerun", selection_mode="single-row",
        selection_default={"selection": {"rows": [default_row]}})
    st.markdown(f"Transit: next upper meridian crossing from the selected start time ({settings.timezone}; HH:MM). "
                "Sizes and classifications: OpenNGC. Distance is unavailable in the bundled catalogue.")
    rows = selection.selection.rows
    if not rows or not 0 <= rows[0] < len(visible_targets):
        st.stop()
    target = visible_targets[rows[0]]
    selected = target.common_name
    st.session_state["selected_target"] = selected
frame = tracks[selected].copy()
night_periods = cached_night(date, settings.timezone, frame["Time"].iloc[0].to_pydatetime(),
                             frame["Time"].iloc[-1].to_pydatetime(), latitude, longitude, height)
night_description = night_text(night_periods, date, settings.timezone)
st.subheader(selected)
if horizon_profile is not None:
    frame["Horizon (°)"] = horizon_altitudes(horizon_profile, frame["Azimuth (°)"].to_numpy())
if show_preview:
    chart_column, image_column = st.columns([2, 1], gap="large")
else:
    chart_column, image_column = st.container(), None
with chart_column:
    renderer = chart_renderer(Path(interactive_chart.__file__).stat().st_mtime_ns)
    html(renderer(frame, minimum_altitude, settings.timezone, object_size_label(target.object_id),
                  exposure_seconds=exposure, target_key=f"{target.ra_deg}:{target.dec_deg}", night_periods=night_periods), height=635)
    filter_recommended, filter_reason = recommend_db2(target.object_id)
    st.checkbox("ZWO DB2 dual-band filter recommended", value=filter_recommended, disabled=True,
                help=filter_reason, key=f"filter_recommendation:{target.object_id}")
if image_column is not None:
    requested_fov = preview_fov(target.object_id) if image_field == "Fit target" else float(image_field.rstrip("°"))
    fov = fit_preview_field(requested_fov, focal_length, sensor_width, sensor_height)
    with image_column:
        try:
            with st.spinner("Loading DSS2 image…"):
                image_bytes = cached_preview(target.ra_deg, target.dec_deg, fov)
        except PreviewError as exc:
            st.warning(str(exc))
            st.button("Retry image", key="retry_image")
        else:
            data = framing_data(image_bytes, focal_length, sensor_width, sensor_height, fov,
                                settings.frame_rotation_deg, int(camera_width), int(camera_height),
                                view_key=f"{target.ra_deg}:{target.dec_deg}")
            render_framing(data,
                on_rotation_change=lambda: persist_framing("frame_rotation_deg", "rotation"))
            if (data["width"] ** 2 + data["height"] ** 2) ** 0.5 > 600:
                st.warning("The camera frame exceeds the image service’s 10° limit; part of the frame is outside this view.")
            st.markdown("[DSS2: STScI/NASA · colour by CDS](https://archive.stsci.edu/dss/copyright.html) · [HiPS2FITS](https://alasky.cds.unistra.fr/hips-image-services/hips2fits)")
        st.markdown(night_description)

