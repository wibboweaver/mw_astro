"""Astrophotography planning. Run with: streamlit run app.py."""
from datetime import date as calendar_date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from pathlib import Path
import hashlib
import json
import importlib
import cloud_forecast, night_rating
for source_module in (cloud_forecast,night_rating):
    if getattr(source_module,'_loaded_source_stamp',None)!=Path(source_module.__file__).stat().st_mtime_ns:
        importlib.reload(source_module)

from targets import parse_targets, resolve_targets
from visibility import calculate_tracks, filter_tracks, discover_tracks, MODES
from catalogue import load_catalogue
import importlib
import object_sizes
if getattr(object_sizes, '_loaded_source_stamp', None) != Path(object_sizes.__file__).stat().st_mtime_ns:
    importlib.reload(object_sizes)
import target_table as target_table_module
if getattr(target_table_module, '_loaded_source_stamp', None) != Path(target_table_module.__file__).stat().st_mtime_ns:
    importlib.reload(target_table_module)
from target_table import target_table, observing_window_hours
import framing
if getattr(framing, "_loaded_source_stamp", None) != (Path(framing.__file__).stat().st_mtime_ns, Path(framing.__file__).with_name("framing.js").stat().st_mtime_ns):
    import importlib
    importlib.reload(framing)
from framing import field_of_view, fit_preview_field
from astronomical_night import night_for_chart, night_text, twilight_for_chart
from object_sizes import object_size_label
import reference_images
if getattr(reference_images, '_loaded_source_stamp', None) != Path(reference_images.__file__).stat().st_mtime_ns:
    import importlib
    importlib.reload(reference_images)
from reference_images import preview_fov

import importlib
import interactive_chart
if getattr(interactive_chart, '_loaded_source_stamp', None) != (Path(interactive_chart.__file__).stat().st_mtime_ns, Path(interactive_chart.__file__).with_name('chart_bridge.js').stat().st_mtime_ns):
    importlib.reload(interactive_chart)
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
def cached_discovery(targets, latitude, longitude, height, start, duration, step, minimum, profile, mode, limit):
    return discover_tracks(targets, latitude, longitude, height, start, duration, step, minimum, profile, mode, limit=limit)


@st.cache_data(show_spinner=False, max_entries=32)
def cached_night(evening_date, zone_name, chart_start, chart_end, latitude, longitude, height):
    return night_for_chart(evening_date, zone_name, chart_start, chart_end, latitude, longitude, height)


@st.cache_data(show_spinner=False, max_entries=12)
def cached_target_table(targets, start, longitude, timezone, windows=None, camera_field=None, camera_pixels=None, ratings=None):
    # Target table contains object ratings and geometry; weather stays on the chart and report.
    return target_table(targets, start, longitude, timezone, windows, camera_field, camera_pixels, ratings)


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


def persist_esa_rotation():
    value=st.session_state.get('esa_camera_framing',{}).get('rotation')
    if value is not None:
        try:
            save_settings_changes(frame_rotation_deg=float(value))
            st.session_state.pop('settings_save_error',None)
        except (OSError,ValueError) as exc:
            st.session_state['settings_save_error']=f'Settings could not be saved: {exc}'


def persist_upload():
    upload = st.session_state.get("sidebar_upload")
    if upload is not None:
        try:
            save_uploaded_catalogue(upload.getvalue())
            st.session_state.pop("settings_save_error", None)
        except (OSError, ValueError, UnicodeError) as exc:
            st.session_state["settings_save_error"] = f"Catalogue could not be saved: {exc}"


st.set_page_config(layout="wide")
st.title("Astrophotography Planning")
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
        # Round legacy saved times to the nearest available ten-minute slot.
        start_minutes = min(23*60+50, ((settings.start_hour*60+settings.start_minute+5)//10)*10)
        start_time = st.slider("Start time (local)", min_value=time(0, 0), max_value=time(23, 50),
            value=time(start_minutes//60, start_minutes%60), step=timedelta(minutes=10), format="HH:mm",
            key="sidebar_start_time", on_change=persist_sidebar, args=("start_time", "sidebar_start_time"))
        exposure_value = max(10, int((settings.exposure_seconds+5)//10)*10)
        exposure = st.slider("Exposure (seconds)", min_value=10, max_value=max(3600, exposure_value),
            value=exposure_value, step=10,
            key="sidebar_exposure", on_change=persist_sidebar, args=("exposure_seconds", "sidebar_exposure"))
        minimum_altitude = st.slider("Minimum altitude (°)", 0.0, 90.0,
            value=float(int(settings.minimum_altitude_deg+0.5)), step=1.0, format="%.0f°",
            key="sidebar_minimum", on_change=persist_sidebar, args=("minimum_altitude_deg", "sidebar_minimum"))
        duration_hours = st.slider("Total chart coverage (hours)", 4.0, 24.0,
            value=float(max(4, min(24, int(settings.duration_hours+0.5)))), step=1.0, format="%.0f",
            key="sidebar_duration", on_change=persist_sidebar, args=("duration_hours", "sidebar_duration"))
        visibility_mode = st.selectbox("Target visibility", MODES, index=MODES.index(settings.visibility_mode),
            key="sidebar_visibility", on_change=persist_sidebar, args=("visibility_mode", "sidebar_visibility"))
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

if latitude is None or longitude is None:
    with st.sidebar:
        st.warning("Enter latitude and longitude to display targets.")
    st.stop()
start = datetime.combine(date, start_time, tzinfo=zone)
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
        tracks = cached_discovery(targets, latitude, longitude, height, start, duration_hours, settings.step_minutes,
                                  minimum_altitude, horizon_profile, visibility_mode, settings.max_objects)
        eligible = sorted(tracks, key=str.casefold)
    else:
        tracks = cached_tracks(targets, latitude, longitude, height, start, duration_hours, settings.step_minutes)
        eligible = sorted(filter_tracks(tracks, minimum_altitude, horizon_profile, visibility_mode), key=str.casefold)
if not eligible:
    st.warning("No targets meet the visibility limits.")
    st.stop()

by_name = {item.common_name: item for item in targets}
visible_targets = tuple(by_name[name] for name in eligible)
st.subheader("Visible targets")
st.markdown(f"Select an object for planning ({len(visible_targets)} total objects listed)")
table_frame=tracks[eligible[0]]
table_nights=cached_night(date,settings.timezone,table_frame['Time'].iloc[0].to_pydatetime(),table_frame['Time'].iloc[-1].to_pydatetime(),latitude,longitude,height)
windows={item.common_name:observing_window_hours(tracks[item.common_name],minimum_altitude,horizon_profile,table_nights) for item in visible_targets}
from cloud_forecast import load_cloud_settings, forecast_for_chart, fetch_cloud_forecast
@st.cache_data(show_spinner=False,ttl=1800,max_entries=16)
def cached_cloud_forecast(first,last,latitude,longitude,cloud_settings):
    return forecast_for_chart(first,last,latitude,longitude,cloud_settings,fetcher=fetch_cloud_forecast)
try:
    cloud_settings=load_cloud_settings(configuration.CONFIG_PATH)
    cloud_data=cached_cloud_forecast(table_frame['Time'].iloc[0].to_pydatetime(),table_frame['Time'].iloc[-1].to_pydatetime(),latitude,longitude,cloud_settings)
except (OSError,ValueError,TypeError) as exc:
    st.error(f'Check cloud_forecast in config.toml: {exc}')
    st.stop()
from night_rating import load_rating_settings, all_ratings, rating_sort_key
@st.cache_data(show_spinner=False,max_entries=12)
def cached_night_ratings(targets,tracks,nights,profile,minimum,cloud,settings,moon_rules,rules):
    # Weather-independent score: visibility, Moon interference and frame fit.
    return all_ratings(targets,tracks,nights,profile,minimum,cloud,settings,moon_rules,rules)
try:
    from planning import load_rules
    rating_rules=load_rating_settings(configuration.CONFIG_PATH)
    ratings=cached_night_ratings(visible_targets,{t.common_name:tracks[t.common_name] for t in visible_targets},table_nights,horizon_profile,minimum_altitude,cloud_data,settings,load_rules()['moon'],rating_rules)
except (ValueError,OSError,TypeError) as exc:
    st.error(f'Check night rating settings: {exc}')
    st.stop()
# Keep the displayed rows and their target identities in the same rating order.
visible_targets=tuple(sorted(visible_targets,key=lambda item:rating_sort_key(ratings[item.common_name],item.common_name)))
remembered = st.session_state.get("selected_target")
names=[item.common_name for item in visible_targets]
default_row = names.index(remembered) if remembered in names else 0
# Reset row indices whenever identities/order change, retaining the target by name.
identities = [(item.common_name, item.object_id, item.ra_deg, item.dec_deg) for item in visible_targets]
table_key = "target_table:" + hashlib.sha256(json.dumps(identities).encode()).hexdigest()[:16]
usable_count=sum(value['start'] is not None for value in ratings.values())
st.caption(f'{usable_count} listed targets have an observable astronomical-night window above the minimum altitude and local horizon. '
    'Target visibility filters the full chart period, which can also include daylight and twilight. '
    'Rated targets appear first, followed by targets awaiting assessment, then targets with no usable dark window.')
display_table=cached_target_table(visible_targets, start, longitude, settings.timezone, windows, (fov_width, fov_height), (camera_width, camera_height), ratings).copy()
selection = st.dataframe(display_table,
    column_config={'Distance':None,
        'Night rating':st.column_config.ProgressColumn('Night rating',width=112,min_value=0,max_value=100,format='%d',color='auto',help='Preference score, not success probability. Best continuous dark window; Configurable weights: visibility 30, Moon 15, frame 25 by default. Independent of cloud cover and rain risk. Full frame credit at preferred coverage; undersized targets have a configurable score cap. Missing values display Missing data; select the target to see the explanation.'),
        'Rating notes':None,
        'Filter?':st.column_config.TextColumn('Filter?',help='Dualband Filter recommendation: yes for emission-line targets; no means not recommended or classification unknown.'),
        'Object pixels':st.column_config.TextColumn('Object pixels',help='Estimated major × minor pixel footprint on the full uncropped sensor, with long axes aligned; not resolved detail.'),
        'Frame coverage':st.column_config.TextColumn('Frame coverage',help='Approximate object major × minor dimensions as percentages of the camera long × short field, with long sides aligned. Above 100% extends beyond that edge. Independent of camera rotation; catalogue sizes are approximate. — means an unknown dimension.'),
        'Window':st.column_config.TextColumn('Window',alignment='left',help='Duration as hours° minutes′. Total time in the chart range above the minimum altitude and local horizon during astronomical night. Estimated from sampled trajectories.')},
    key=table_key, hide_index=True, width="stretch", height=250, placeholder="Missing data",
    on_select="rerun", selection_mode="single-row",
    selection_default={"selection": {"rows": [default_row]}})
rows = selection.selection.rows
if not rows or not 0 <= rows[0] < len(visible_targets):
    st.stop()
target = visible_targets[rows[0]]
selected = target.common_name
st.session_state["selected_target"] = selected
rating=ratings[selected]
if rating['score'] is None:
    st.caption('Night rating — based on the object’s observable window within the chart period: Missing data — '+rating['reason'])
else:
    from night_rating import rating_gauge
    st.html(rating_gauge(rating['score'],rating['reason']))
st.caption('Selecting a different start and stop time can change the assessment. The report uses your chosen interval to assess cloud cover, rain risk and observing conditions.')
if rating['start'] is not None:
    st.caption('Rated window: '+datetime.fromtimestamp(rating['start'],zone).strftime('%d %b %H:%M')+'–'+datetime.fromtimestamp(rating['end'],zone).strftime('%d %b %H:%M')+' · Rain risk is separate from the score.')

frame = tracks[selected].copy()
from planning import load_rules
from moon_interference import calculate_moonlight
@st.cache_data(show_spinner=False, max_entries=12)
def cached_moonlight(first,last,latitude,longitude,height,ra,dec,step,rules,source_version=None):
    return calculate_moonlight(first,last,latitude,longitude,height,ra,dec,step,rules)
try:
    planning_rules=load_rules()
    moon_data=cached_moonlight(frame['Time'].iloc[0].to_pydatetime(),frame['Time'].iloc[-1].to_pydatetime(),latitude,longitude,height,target.ra_deg,target.dec_deg,planning_rules['visibility']['sample_interval_minutes'],planning_rules['moon'],Path(__file__).with_name('moon_interference.py').stat().st_mtime_ns)
except (OSError,ValueError,TypeError) as exc:
    st.error(f'Check planning_rules in config.toml: {exc}')
    st.stop()
night_periods = cached_night(date, settings.timezone, frame["Time"].iloc[0].to_pydatetime(),
                             frame["Time"].iloc[-1].to_pydatetime(), latitude, longitude, height)
@st.cache_data(show_spinner=False, max_entries=32)
def cached_twilight(first,last,latitude,longitude,height):
    return twilight_for_chart(first,last,latitude,longitude,height)
twilight_periods=cached_twilight(frame['Time'].iloc[0].to_pydatetime(),frame['Time'].iloc[-1].to_pydatetime(),latitude,longitude,height)
night_description = night_text(night_periods, date, settings.timezone)
st.subheader(selected)
st.caption("Chart shows object altitude over time")
import planning_ui, planning_report
for report_module in (planning_report,planning_ui):
    if getattr(report_module,'_loaded_source_stamp',None)!=Path(report_module.__file__).stat().st_mtime_ns:
        importlib.reload(report_module)
from planning_ui import render_planner
if horizon_profile is not None:
    frame["Horizon (°)"] = horizon_altitudes(horizon_profile, frame["Azimuth (°)"].to_numpy())
if show_preview:
    chart_column, image_column = st.columns([2, 1], gap="large")
else:
    chart_column, image_column = st.container(), None
with chart_column:
    renderer = chart_renderer(Path(interactive_chart.__file__).stat().st_mtime_ns)
    chart_content = renderer(frame, minimum_altitude, settings.timezone, object_size_label(target.object_id),
                  exposure_seconds=exposure, target_key=f"{target.ra_deg}:{target.dec_deg}", night_periods=night_periods, twilight_periods=twilight_periods, moon_intervals=moon_data["intervals"], cloud_forecast=cloud_data, moon_distance={"times":moon_data["times"],"separation":moon_data["separation"],"altitudes":moon_data["altitudes"],"illumination":moon_data["illumination"],"phase_angles":moon_data["phase_angles"],"enabled":moon_data["enabled"]})
    interval_key = "observation:" + hashlib.sha256(f"{target.ra_deg}:{target.dec_deg}:{frame['Time'].iloc[0]}:{frame['Time'].iloc[-1]}".encode()).hexdigest()[:16]
    chart_selection = interactive_chart.render_chart(chart_content, interval_key)
    render_planner(target, settings, start, exposure, horizon_profile, chart_selection, frame["Time"].iloc[0], frame["Time"].iloc[-1], moon_data=moon_data, cloud_data=cloud_data,night_rating=rating)

if image_column is not None:
    requested_fov = preview_fov(target.object_id) if image_field == "Fit target" else float(image_field.rstrip("°"))
    fov = fit_preview_field(requested_fov, focal_length, sensor_width, sensor_height)
    with image_column:
        import esa_preview
        if esa_preview._loaded_source_stamp != (Path(esa_preview.__file__).stat().st_mtime_ns,Path(esa_preview.__file__).with_suffix('.js').stat().st_mtime_ns):
            importlib.reload(esa_preview)
        preview_key=(target.object_id,target.ra_deg,target.dec_deg)
        fields=st.session_state.setdefault('esa_preview_fields',{})
        fov=fields.setdefault(preview_key,fov)
        data=esa_preview.esa_preview_data(target.ra_deg,target.dec_deg,focal_length,sensor_width,sensor_height,fov,
            settings.frame_rotation_deg,int(camera_width),int(camera_height),view_key=f'{target.ra_deg}:{target.dec_deg}')
        esa_preview.render_esa_preview(data,on_rotation_change=lambda:persist_esa_rotation())
        st.markdown(night_description)
        with st.expander('Chart legend', expanded=False):
            legend_items = (
                ('border-top:3px solid #4c9be8', 'Object trajectory'),
                ('background:rgba(255,0,0,0.6);border-top:2px solid #c44e52', 'Below local horizon'),
                ('border-top:3px dotted #e69520', 'Minimum altitude'),
                ('border-top:3px solid #bc80ee', 'Observation start / stop'),
                ('background:rgba(255,255,0,0.9)', 'Possible Moon interference'),
                ('background:rgba(150,159,197,0.16);border:1px solid #969fc5', 'Astronomical night'),
                ('background:rgba(245,158,11,0.18);border:1px solid #f59e0b', 'Astronomical twilight (Sun −12° to −18°)'),
                ('background:linear-gradient(to right,#22c55e,#fbbf24,#ef4444)', 'Cloud / Precip.: green = low %, amber = intermediate, red = high %; Precip. = probability'),
                ('background:repeating-linear-gradient(135deg,transparent 0 4px,#888 4px 5px)', 'Weather forecast unavailable'),
            )
            st.html(''.join(f'<div style="display:flex;align-items:center;gap:10px;margin:7px 0;font-size:14px"><span aria-hidden="true" style="display:inline-block;flex:0 0 28px;height:10px;{style}"></span><span>{label}</span></div>' for style,label in legend_items))

