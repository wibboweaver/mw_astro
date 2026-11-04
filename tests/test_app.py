from datetime import time
from pathlib import Path
from unittest.mock import patch
import pandas as pd
import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest
from configuration import Settings
from targets import Target

APP = str(Path(__file__).resolve().parents[1] / 'app.py')
FIXTURES = (Target('Fixture low', 'TEST1', 10, 40), Target('Fixture high', 'TEST2', 20, 50))


@pytest.fixture(autouse=True)
def clear_caches(tmp_path, monkeypatch):
    import configuration
    test_config = tmp_path / "config.toml"
    test_config.write_text(Path(configuration.__file__).with_name("config.toml").read_text())
    monkeypatch.setattr(configuration, "CONFIG_PATH", test_config)
    st.cache_data.clear()
    from io import BytesIO
    from PIL import Image
    image = BytesIO()
    Image.new("RGB", (600, 600)).save(image, format="JPEG")
    with patch("catalogue.load_catalogue", return_value=()), patch("reference_images.fetch_preview", return_value=image.getvalue()), patch("cloud_forecast.fetch_cloud_forecast", return_value=dict(segments=[],retrieved_at=None,error="Cloud forecast unavailable")):
        yield
    st.cache_data.clear()


def fake_tracks(targets, latitude, longitude, height, start, duration, step):
    return {target.common_name: pd.DataFrame({'Time': [pd.Timestamp(start), pd.Timestamp(start)+pd.Timedelta(hours=duration)],
        'Altitude (°)': [alt, alt], 'Azimuth (°)': [150, 150]}) for target, alt in zip(targets, [50, 70])}


def start_custom():
    app = AppTest.from_file(APP, default_timeout=20).run()
    next(s for s in app.sidebar.selectbox if s.label == 'Target source').select('Custom CSV').run()
    return app


def chart_frames(app):
    import json
    from types import SimpleNamespace
    return [SimpleNamespace(proto=SimpleNamespace(srcdoc=json.loads(item.proto.json)['html']))
            for item in app.get('bidi_component') if 'observation_chart' in item.proto.component_name]


def target_names(app):
    return list(app.dataframe[0].value['Common name'])


def select_target(app, name):
    # AppTest has no dataframe click helper; submit the same protobuf state as a row click.
    import json
    states = app._tree.get_widget_states()
    table_id = app.dataframe[0].proto.id
    retained = [state for state in states.widgets if state.id != table_id]
    del states.widgets[:]
    states.widgets.extend(retained)
    state = states.widgets.add(id=table_id)
    state.string_value = json.dumps({'selection': {'rows': [] if name is None else [target_names(app).index(name)], 'columns': []}})
    return app._run(states)


def test_table_filters_retains_selection_and_reuses_tracks():
    with patch('targets.parse_targets', return_value=FIXTURES), patch('configuration.load_settings', return_value=Settings(latitude_deg=52, longitude_deg=-3)), patch('visibility.calculate_tracks', side_effect=fake_tracks) as calculate, patch('objects.resolve_object') as resolver:
        app = start_custom()
        assert not app.exception
        assert target_names(app) == ['Fixture high', 'Fixture low']
        select_target(app, 'Fixture high')
        assert calculate.call_count == 1
        app.sidebar.slider(key='sidebar_minimum').set_value(60.0).run()
        assert target_names(app) == ['Fixture high']
        assert app.session_state['selected_target'] == 'Fixture high'
        assert calculate.call_count == 1
        app.sidebar.slider(key='sidebar_start_time').set_value(time(20, 30)).run()
        assert calculate.call_count == 2
        assert calculate.call_args.args[4].hour == 20
        assert calculate.call_args.args[4].minute == 30
        resolver.assert_not_called()
        content = chart_frames(app)[0].proto.srcdoc
        assert 'pointermove' in content and 'id="alt"' in content
        assert not app.text_input
        assert not app.time_input
        assert not any(n.label == "Session exposure (seconds)" for n in app.number_input)


def test_selected_target_removed_by_custom_horizon(tmp_path):
    profile = tmp_path/'Garden.txt'
    profile.write_text('60 0\n60 180')
    with patch('targets.parse_targets', return_value=FIXTURES), patch('configuration.load_settings', return_value=Settings(latitude_deg=52, longitude_deg=-3)), patch('visibility.calculate_tracks', side_effect=fake_tracks) as calculate, patch('horizon.available_horizons', return_value=[profile]):
        app = start_custom()
        select_target(app, 'Fixture low')
        assert app.session_state['selected_target'] == 'Fixture low'
        app.sidebar.selectbox(key='sidebar_horizon').select(profile.name).run()
        assert not app.exception
        assert target_names(app) == ['Fixture high']
        assert app.session_state['selected_target'] == 'Fixture high'
        assert calculate.call_count == 1
        assert '"horizon": [60.0, 60.0]' in chart_frames(app)[0].proto.srcdoc
        app.sidebar.slider(key='sidebar_minimum').set_value(80.0).run()
        assert any('No targets meet' in item.value for item in app.warning)
        assert not app.dataframe
        assert not chart_frames(app)


def test_empty_catalogue_explains_required_source():
    with patch('targets.parse_targets', return_value=()):
        app = start_custom()
        assert not app.exception
        assert 'No target catalogue' in app.warning[0].value
        assert not chart_frames(app)


def test_automatic_catalogue_needs_no_list_and_selection_is_cached():
    with patch('catalogue.load_catalogue', return_value=FIXTURES), patch('configuration.load_settings', return_value=Settings(latitude_deg=52, longitude_deg=-3)), patch('visibility.calculate_tracks', side_effect=fake_tracks) as calculate, patch('objects.resolve_object') as resolver:
        app = AppTest.from_file(APP, default_timeout=20).run()
        assert not app.exception
        assert target_names(app) == ['Fixture high', 'Fixture low']
        select_target(app, 'Fixture low')
        assert calculate.call_count == 1
        assert len(chart_frames(app)) == 1
        resolver.assert_not_called()
        assert not app.file_uploader


def esa_payload(app):
    import json
    return next(json.loads(item.proto.json) for item in app.get('bidi_component')
                if 'esa_dss2_preview' in item.proto.component_name)


def test_esa_preview_uses_tiles_without_requesting_cutouts():
    with patch('catalogue.load_catalogue', return_value=FIXTURES), patch('configuration.load_settings', return_value=Settings(latitude_deg=52, longitude_deg=-3)), patch('visibility.calculate_tracks', side_effect=fake_tracks), patch('reference_images.fetch_preview') as fetch:
        app = AppTest.from_file(APP, default_timeout=20).run()
        assert not app.exception
        original = esa_payload(app)
        assert original['survey'] == 'https://skies.esac.esa.int/DSSColor'
        assert 'image' not in original
        app.sidebar.slider(key='sidebar_start_time').set_value(time(20,30)).run()
        assert esa_payload(app)['view_key'] == original['view_key']
        select_target(app, 'Fixture low')
        assert esa_payload(app)['view_key'] != original['view_key']
        select_target(app, 'Fixture high')
        assert esa_payload(app)['view_key'] == original['view_key']
        fetch.assert_not_called()
        assert len(chart_frames(app)) == 1








def test_sidebar_changes_persist_across_new_sessions(tmp_path, monkeypatch):
    import configuration
    path = tmp_path/'saved.toml'
    path.write_text('[observatory]\nlatitude_deg=52.0\nlongitude_deg=-3.0\nheight_m=123.0\n')
    monkeypatch.setattr(configuration, 'CONFIG_PATH', path)
    profile = tmp_path/'Garden.txt'
    profile.write_text('10 0\n10 180\n')
    with patch('horizon.available_horizons', return_value=[profile]):
        app = AppTest.from_file(APP, default_timeout=20).run()
        assert not any('sea level' in n.label.lower() for n in app.sidebar.number_input)
        app.sidebar.number_input(key='sidebar_latitude').set_value(53.0).run()
        app.sidebar.number_input(key='sidebar_longitude').set_value(-2.0).run()
        app.sidebar.selectbox(key='sidebar_horizon').select('Garden.txt').run()
        app.sidebar.date_input(key='sidebar_date').set_value(__import__('datetime').date(2026,11,2)).run()
        app.sidebar.slider(key='sidebar_start_time').set_value(time(21,40)).run()
        app.sidebar.slider(key='sidebar_exposure').set_value(240.0).run()
        app.sidebar.slider(key='sidebar_minimum').set_value(45.0).run()
        app.sidebar.selectbox(key='sidebar_visibility').select('At start').run()
        app.sidebar.selectbox(key='sidebar_scope').select('All deep-sky objects').run()
        app.sidebar.selectbox(key='sidebar_image_field').select('2°').run()
        app.sidebar.checkbox(key='sidebar_preview').uncheck().run()
        saved = configuration.load_settings()
        assert saved.height_m == 123
        assert saved.exposure_seconds == 240
        assert saved.latitude_deg == 53 and saved.longitude_deg == -2
        assert saved.horizon_file == 'Garden.txt' and saved.start_minute == 40
        assert saved.evening_date == '2026-11-02' and saved.minimum_altitude_deg == 45
        assert not saved.show_preview and saved.image_field == '2°'
        fresh = AppTest.from_file(APP, default_timeout=20).run()
        assert not fresh.exception
        assert fresh.sidebar.number_input(key='sidebar_latitude').value == 53
        assert fresh.sidebar.slider(key='sidebar_start_time').value == time(21,40)
        assert fresh.sidebar.slider(key='sidebar_exposure').value == 240
        assert fresh.sidebar.date_input(key='sidebar_date').value.isoformat() == '2026-11-02'
        assert fresh.sidebar.selectbox(key='sidebar_horizon').value == 'Garden.txt'
        assert not fresh.sidebar.checkbox(key='sidebar_preview').value
        fresh.sidebar.checkbox(key='sidebar_preview').check().run()
        assert fresh.sidebar.selectbox(key='sidebar_image_field').value == '2°'
        fresh.sidebar.selectbox(key='sidebar_source').select('Custom CSV').run()
        reopened = AppTest.from_file(APP, default_timeout=20).run()
        assert reopened.sidebar.selectbox(key='sidebar_source').value == 'Custom CSV'


def test_save_failure_is_visible_and_chart_still_works():
    with patch('catalogue.load_catalogue', return_value=FIXTURES), patch('configuration.load_settings', return_value=Settings(latitude_deg=52, longitude_deg=-3, evening_date='2026-10-22')), patch('visibility.calculate_tracks', side_effect=fake_tracks), patch('configuration.save_settings_changes', side_effect=PermissionError('read only')):
        app = AppTest.from_file(APP, default_timeout=20).run()
        app.sidebar.slider(key='sidebar_minimum').set_value(45.0).run()
        assert not app.exception
        assert len(chart_frames(app)) == 1
        assert any('could not be saved' in e.value for e in app.sidebar.error)


def test_exposure_control_and_filter_recommendation():
    with patch('catalogue.load_catalogue',return_value=FIXTURES), patch('configuration.load_settings',return_value=Settings(latitude_deg=52,longitude_deg=-3,evening_date='2026-10-22')), patch('visibility.calculate_tracks',side_effect=fake_tracks), patch('filter_recommendations.recommend_dualband',return_value=(True,'Emission nebula')):
        app=AppTest.from_file(APP,default_timeout=20).run()
        assert not app.exception
        assert app.sidebar.slider(key='sidebar_exposure').value == 180
        assert not any('filter recommended' in box.label for box in app.checkbox)
        assert set(app.dataframe[0].value['Filter?'])=={'yes'}
        app.sidebar.slider(key='sidebar_exposure').set_value(240.0).run()
        assert not app.exception
        assert '"exposure_seconds": 240.0' in chart_frames(app)[0].proto.srcdoc
        with patch('filter_recommendations.recommend_dualband',return_value=(False,'Broadband target')):
            select_target(app, 'Fixture low')
            st.cache_data.clear()
            app.run()
            assert set(app.dataframe[0].value['Filter?'])=={'no'}


def test_night_times_remain_without_reference_links_and_survive_image_failure():
    from reference_images import PreviewError
    with patch('catalogue.load_catalogue',return_value=FIXTURES),patch('configuration.load_settings',return_value=Settings(latitude_deg=52,longitude_deg=-3,evening_date='2026-10-22')),patch('visibility.calculate_tracks',side_effect=fake_tracks):
        app=AppTest.from_file(APP,default_timeout=20).run()
        assert not app.exception
        markdown=[item.value for item in app.main.markdown]
        assert not any('ESA sky survey' in text for text in markdown)
        assert not app.sidebar.caption
        assert any(c.value=='Chart shows object altitude over time' for c in app.main.caption)
        times=next(i for i,text in enumerate(markdown) if 'Astronomical night (Europe/London)' in text)
        assert 'Start:' in markdown[times] and 'End:' in markdown[times]
        assert '"astronomical_night": [[' in chart_frames(app)[0].proto.srcdoc
        st.cache_data.clear()
        with patch('reference_images.fetch_preview',side_effect=PreviewError('Unavailable')):
            app.run()
            assert any('Astronomical night' in item.value for item in app.main.markdown)
            assert len(chart_frames(app))==1


def test_visible_target_table_selects_and_filters():
    with patch('catalogue.load_catalogue', return_value=FIXTURES), patch('configuration.load_settings', return_value=Settings(latitude_deg=52, longitude_deg=-3)), patch('visibility.calculate_tracks', side_effect=fake_tracks):
        app = AppTest.from_file(APP, default_timeout=20).run()
        assert not app.exception
        table = app.dataframe[0].value
        assert list(table['Common name']) == ['Fixture high', 'Fixture low']
        assert not any(box.label == 'Target (common name)' for box in app.selectbox)
        assert app.dataframe[0].proto.selection_mode
        assert app.main.subheader[0].value == 'Visible targets'
        assert list(table.columns) == ['Catalogue ID', 'Common name', 'Night rating', 'Rating notes', 'Transit time', 'Frame coverage', 'Object pixels', 'Window', 'Filter?', 'Size', 'Classification', 'Distance', 'RA (J2000)', 'Dec (J2000)']
        select_target(app, 'Fixture low')
        pd.testing.assert_frame_equal(table, app.dataframe[0].value)
        app.sidebar.slider(key='sidebar_minimum').set_value(60.0).run()
        assert list(app.dataframe[0].value['Catalogue ID']) == ['TEST2']


def test_sidebar_tabs_equipment_persistence_and_image_cache():
    import configuration
    with patch('catalogue.load_catalogue',return_value=FIXTURES), patch('visibility.calculate_tracks',side_effect=fake_tracks), patch('reference_images.fetch_preview',return_value=b'fixture') as fetch:
        app=AppTest.from_file(APP,default_timeout=20).run()
        assert not app.exception
        assert [tab.label for tab in app.sidebar.tabs] == ['Plan','Site','Targets','Frame']
        assert app.sidebar.number_input(key='sidebar_focal_length').value == 550
        app.sidebar.number_input(key='sidebar_focal_length').set_value(1100.0).run()
        app.sidebar.number_input(key='sidebar_sensor_width').set_value(22.0).run()
        app.sidebar.number_input(key='sidebar_sensor_height').set_value(14.0).run()
        assert not app.exception
        saved=configuration.load_settings()
        assert saved.focal_length_mm==1100 and saved.sensor_width_mm==22 and saved.sensor_height_mm==14
        fresh=AppTest.from_file(APP,default_timeout=20).run()
        assert fresh.sidebar.number_input(key='sidebar_focal_length').value==1100
        assert fresh.sidebar.number_input(key='sidebar_sensor_width').value==22
        assert fresh.sidebar.number_input(key='sidebar_sensor_height').value==14
        app.sidebar.number_input(key='sidebar_camera_width').set_value(6000).run()
        app.sidebar.number_input(key='sidebar_camera_height').set_value(4000).run()
        saved=configuration.load_settings()
        assert saved.camera_width_px == 6000 and saved.camera_height_px == 4000
        fresh=AppTest.from_file(APP,default_timeout=20).run()
        assert fresh.sidebar.number_input(key='sidebar_camera_width').value == 6000
        assert fresh.sidebar.number_input(key='sidebar_camera_height').value == 4000
        count=fetch.call_count
        configuration.save_settings_changes(frame_rotation_deg=135)
        app.run()
        assert not app.exception and fetch.call_count==count
        assert configuration.load_settings().frame_rotation_deg==135


def test_clearing_row_hides_chart_and_reselecting_updates_details():
    with patch('catalogue.load_catalogue', return_value=FIXTURES), patch('configuration.load_settings', return_value=Settings(latitude_deg=52, longitude_deg=-3)), patch('visibility.calculate_tracks', side_effect=fake_tracks):
        app=AppTest.from_file(APP, default_timeout=20).run()
        assert app.main.subheader[-1].value == 'Fixture high'
        select_target(app, None)
        assert not app.exception and not chart_frames(app)
        assert len(app.dataframe)==1
        select_target(app, 'Fixture low')
        assert not app.exception
        assert app.main.subheader[-1].value=='Fixture low'
        assert app.session_state['selected_target']=='Fixture low'
        assert '10:40' in chart_frames(app)[0].proto.srcdoc


def test_markdown_report_panel_generates_and_invalidates():
    from planning import Report,Check
    from datetime import datetime,timezone
    begin=datetime(2026,10,29,20,tzinfo=timezone.utc)
    end=datetime(2026,10,30,1,tzinfo=timezone.utc)
    with patch('catalogue.load_catalogue',return_value=FIXTURES), patch('configuration.load_settings',return_value=Settings(latitude_deg=52,longitude_deg=-3)), patch('visibility.calculate_tracks',side_effect=fake_tracks), patch('planning_ui.evaluate_checklist',return_value=Report([Check('Start night','Unsuitable','Outside astronomical darkness')],40,120)), patch('interactive_chart.selected_interval',return_value=(begin,end)):
        app=AppTest.from_file(APP,default_timeout=20).run()
        assert not app.exception
        assert not any(e.label=='Observation Feedback' for e in app.expander)
        assert any(e.label=='Imaging report' for e in app.expander)
        assert not any(b.label=='Accept plan' for b in app.button)
        next(b for b in app.button if b.label=='Generate report').click().run()
        assert not app.exception
        content=app.session_state['imaging_report_markdown']
        assert '**GO' not in content and '**NO GO' not in content
        assert content.count('## Observation Criteria')==1
        assert 'Sequence:' not in content
        app.run()
        assert app.session_state['imaging_report_markdown']==content
        app.sidebar.slider(key='sidebar_exposure').set_value(240).run()
        assert 'imaging_report_markdown' not in app.session_state


@pytest.mark.parametrize('points,message', [([], 'Missing start and stop'), ([0], 'Missing stop')])
def test_planner_reports_missing_chart_times(points,message):
    with patch('catalogue.load_catalogue',return_value=FIXTURES), patch('configuration.load_settings',return_value=Settings(latitude_deg=52,longitude_deg=-3)), patch('visibility.calculate_tracks',side_effect=fake_tracks), patch('interactive_chart.render_chart') as chart, patch('planning_ui.evaluate_checklist') as evaluate:
        def selection(content,key):
            import json
            payload=json.loads(content.split('const data=')[1].split(';')[0])
            return {'interval':[payload['times'][0] for _ in points]}
        chart.side_effect=selection
        app=AppTest.from_file(APP,default_timeout=20).run()
        assert not app.exception
        assert any(message in e.value for e in app.info)
        evaluate.assert_not_called()


def test_planner_uses_chart_interval_and_current_sidebar_exposure():
    from planning import Report, Check
    import json
    captured={}
    def selection(content,key):
        payload=json.loads(content.split('const data=')[1].split(';')[0])
        captured['times']=payload['times']
        return {'interval':list(reversed(payload['times']))}
    with patch('catalogue.load_catalogue',return_value=FIXTURES), patch('configuration.load_settings',return_value=Settings(latitude_deg=52,longitude_deg=-3)), patch('visibility.calculate_tracks',side_effect=fake_tracks), patch('interactive_chart.render_chart',side_effect=selection), patch('planning_ui.evaluate_checklist',return_value=Report([Check('Weather','Unknown','Check forecast')],20,80)) as evaluate:
        app=AppTest.from_file(APP,default_timeout=20).run()
        app.sidebar.slider(key='sidebar_exposure').set_value(240.0).run()
        assert not app.exception
        next(b for b in app.button if b.label=='Generate report').click().run()
        assert not app.exception
        plan=evaluate.call_args.args[0]
        assert plan.exposure_seconds==240
        assert [int(plan.start.timestamp()*1000),int(plan.end.timestamp()*1000)]==captured['times']
        assert not app.time_input
        assert not any(n.label=='Session exposure (seconds)' for n in app.number_input)


def test_target_image_is_pinned_across_equipment_and_chart_changes():
    with patch('catalogue.load_catalogue',return_value=FIXTURES), patch('configuration.load_settings',return_value=Settings(latitude_deg=52,longitude_deg=-3)), patch('visibility.calculate_tracks',side_effect=fake_tracks):
        app=AppTest.from_file(APP,default_timeout=20).run()
        original=esa_payload(app)
        app.sidebar.number_input(key='sidebar_focal_length').set_value(1100.).run()
        app.sidebar.selectbox(key='sidebar_image_field').select('5°').run()
        app.sidebar.slider(key='sidebar_start_time').set_value(time(20,30)).run()
        st.cache_data.clear()
        app.run()
        current=esa_payload(app)
        assert not app.exception
        assert current['image_field']==original['image_field']
        assert current['view_key']==original['view_key']
        assert current['width']!=original['width']
        select_target(app,'Fixture low')
        assert esa_payload(app)['view_key']!=original['view_key']


def test_frame_fit_updates_with_equipment_and_window_aligns_left():
    import json
    with patch('catalogue.load_catalogue',return_value=FIXTURES), patch('configuration.load_settings',return_value=Settings(latitude_deg=52,longitude_deg=-3)), patch('visibility.calculate_tracks',side_effect=fake_tracks), patch('object_sizes.catalogue_sizes',return_value={'TEST1':(60.,30.),'TEST2':(120.,60.)}):
        app=AppTest.from_file(APP,default_timeout=20).run()
        before=app.dataframe[0].value['Frame coverage'].tolist()
        assert all(value != '—' for value in before)
        columns=json.loads(app.dataframe[0].proto.columns)
        assert columns['Window']['alignment']=='left'
        app.sidebar.number_input(key='sidebar_focal_length').set_value(1100.).run()
        assert not app.exception
        assert app.dataframe[0].value['Frame coverage'].tolist()!=before
        assert app.session_state['selected_target']=='Fixture high'


@pytest.mark.parametrize('hours',[4.0,24.0])
def test_chart_duration_slider_updates_tracks_and_persists(hours):
    import configuration
    with patch('catalogue.load_catalogue',return_value=FIXTURES), patch('visibility.calculate_tracks',side_effect=fake_tracks) as calculate:
        app=AppTest.from_file(APP,default_timeout=20).run()
        assert not app.exception
        sliders=list(app.sidebar.slider)
        labels=[slider.label for slider in sliders]
        assert labels.index(app.sidebar.slider(key='sidebar_duration').label)==labels.index('Minimum altitude (°)')+1
        assert app.sidebar.slider(key='sidebar_exposure').proto.step==10
        assert app.sidebar.slider(key='sidebar_minimum').proto.step==1
        duration=app.sidebar.slider(key='sidebar_duration')
        assert duration.proto.min==4 and duration.proto.max==24
        duration.set_value(hours).run()
        assert not app.exception
        assert calculate.call_args.args[5]==hours
        assert configuration.load_settings().duration_hours==hours
        fresh=AppTest.from_file(APP,default_timeout=20).run()
        assert not fresh.exception
        assert fresh.sidebar.slider(key='sidebar_duration').value==hours


def test_legacy_slider_values_round_to_new_steps():
    with patch('configuration.load_settings',return_value=Settings(latitude_deg=52,longitude_deg=-3,exposure_seconds=123,minimum_altitude_deg=49.8,duration_hours=30)):
        app=AppTest.from_file(APP,default_timeout=20).run()
        assert not app.exception
        assert app.sidebar.slider(key='sidebar_exposure').value==120
        assert app.sidebar.slider(key='sidebar_minimum').value==50
        assert app.sidebar.slider(key='sidebar_duration').value==24


def test_main_page_uses_catalogue_directly_and_new_title():
    with patch('catalogue.load_catalogue',return_value=FIXTURES), patch('configuration.load_settings',return_value=Settings(latitude_deg=52,longitude_deg=-3)), patch('visibility.calculate_tracks',side_effect=fake_tracks), patch('objects.resolve_object') as resolver:
        app=AppTest.from_file(APP,default_timeout=20).run()
        assert not app.exception
        assert app.title[0].value=='Astrophotography Planning'
        assert not app.radio and not app.text_input and not app.form
        assert target_names(app)==['Fixture high','Fixture low']
        select_target(app,'Fixture low')
        assert not app.exception
        assert app.session_state['selected_target']=='Fixture low'
        assert len(chart_frames(app))==1
        resolver.assert_not_called()


def test_discovery_uses_configured_limit_and_sampling():
    with patch('catalogue.load_catalogue',return_value=FIXTURES), patch('configuration.load_settings',return_value=Settings(latitude_deg=52,longitude_deg=-3,max_objects=1,step_minutes=5)), patch('visibility.calculate_tracks',side_effect=fake_tracks) as calculate:
        app=AppTest.from_file(APP,default_timeout=20).run()
        assert not app.exception
        assert len(target_names(app))==1
        assert target_names(app)==['Fixture high']
        assert calculate.call_args.args[6]==5


def test_night_rating_order_and_selection_survive_score_changes():
    scores={'Fixture high':40,'Fixture low':90}
    def ratings(targets,*args):
        return {t.common_name:dict(score=scores[t.common_name],rain=None,cloud=None,reason='Test rating',start=None,end=None) for t in targets}
    with patch('catalogue.load_catalogue',return_value=FIXTURES), patch('configuration.load_settings',return_value=Settings(latitude_deg=52,longitude_deg=-3)), patch('visibility.calculate_tracks',side_effect=fake_tracks), patch('night_rating.all_ratings',side_effect=ratings):
        app=AppTest.from_file(APP,default_timeout=20).run()
        assert not app.exception
        assert target_names(app)==['Fixture low','Fixture high']
        select_target(app,'Fixture high')
        assert app.session_state['selected_target']=='Fixture high'
        scores.update({'Fixture high':95,'Fixture low':None})
        st.cache_data.clear()
        app.run()
        assert not app.exception
        assert target_names(app)==['Fixture high','Fixture low']
        assert app.session_state['selected_target']=='Fixture high'
        assert app.main.subheader[-1].value=='Fixture high'
        scores.update({'Fixture high':0,'Fixture low':None})
        st.cache_data.clear()
        app.run()
        assert not app.exception
        assert target_names(app)==['Fixture low','Fixture high']



def test_target_table_excludes_weather_and_preserves_missing_ratings():
    def ratings(targets,*args):
        return {t.common_name:dict(score=None,cloud=None,rain=None,reason='Catalogue dimensions unavailable',start=None,end=None) for t in targets}
    with patch('catalogue.load_catalogue',return_value=FIXTURES), patch('configuration.load_settings',return_value=Settings(latitude_deg=52,longitude_deg=-3)), patch('visibility.calculate_tracks',side_effect=fake_tracks), patch('night_rating.all_ratings',side_effect=ratings):
        app=AppTest.from_file(APP,default_timeout=20).run()
        assert not app.exception
        table=app.dataframe[0]
        assert 'Cloud cover' not in table.value.columns
        assert 'Rain risk' not in table.value.columns
        assert table.proto.placeholder=='Missing data'
        assert table.value['Night rating'].isna().all()
        assert any('Missing data — Catalogue dimensions unavailable' in c.value for c in app.caption)


def test_mixed_rating_values_preserve_native_progress_bars():
    def ratings(targets,*args):
        return {t.common_name:dict(score=80 if t.common_name=='Fixture low' else None,cloud=None,rain=None,reason='Test',start=None,end=None) for t in targets}
    with patch('catalogue.load_catalogue',return_value=FIXTURES), patch('configuration.load_settings',return_value=Settings(latitude_deg=52,longitude_deg=-3)), patch('visibility.calculate_tracks',side_effect=fake_tracks), patch('night_rating.all_ratings',side_effect=ratings):
        app=AppTest.from_file(APP,default_timeout=20).run()
        assert not app.exception
        assert app.dataframe[0].value['Night rating'].iloc[0]==80
        assert pd.isna(app.dataframe[0].value['Night rating'].iloc[1])
        import json
        assert json.loads(app.dataframe[0].proto.columns)['Night rating']['type_config']['type']=='progress'
