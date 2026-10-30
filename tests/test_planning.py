from copy import deepcopy
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import json
import pytest
from planning import DEFAULTS, Plan, assess, load_rules, save_accepted, evaluate
from configuration import Settings
from targets import Target


def plan(**changes):
    values=dict(target='M31',start=datetime(2026,10,29,20,tzinfo=timezone.utc),end=datetime(2026,10,30,2,tzinfo=timezone.utc),exposure_seconds=180,filter_confirmed=True)
    return Plan(**(values|changes))


def report(rules=None, **changes):
    data=dict(altitudes=[50,55],horizons=[0,0],sun_altitudes=[-20,-25],moon_altitudes=[-5,-10],moon_separations=[20,20],moon_illumination=[90,90],filter_recommended=False,target_major_arcmin=30,fov=(2,1))
    return assess(plan(),rules or deepcopy(DEFAULTS),**(data|changes))


def test_good_plan_and_overheads(tmp_path):
    r=report()
    assert r.status=='Unknown' # weather is never assumed clear
    assert r.exposures < 120
    assert r.integration_minutes==r.exposures*3
    assert not r.can_accept(DEFAULTS)
    assert r.can_accept(DEFAULTS,True)
    path=save_accepted(plan(),r,DEFAULTS,tmp_path,True)
    payload=json.loads(path.read_text())
    assert payload['execution_status']=='not_armed'
    assert payload['plan']['end'].startswith('2026-10-30')
    assert payload['rules']==DEFAULTS


@pytest.mark.parametrize('changes,name,status',[
    ({'sun_altitudes':[-11,-20]},'Astronomical darkness','Unsuitable'),
    ({'sun_altitudes':[-12,-18]},'Astronomical darkness','Challenging'),
    ({'altitudes':[29,50]},'Target altitude','Unsuitable'),
    ({'altitudes':[30,50]},'Target altitude','Challenging'),
    ({'horizons':[47,0]},'Local horizon','Unsuitable'),
    ({'crossing':True},'Meridian crossing','Challenging'),
    ({'moon_altitudes':[10,20]},'Moon interference','Unsuitable'),
    ({'filter_recommended':True},'Filter suitability','Challenging'),
    ({'target_major_arcmin':None},'Framing','Unknown'),
    ({'target_major_arcmin':100},'Framing','Unsuitable'),
])
def test_rule_boundaries(changes,name,status):
    r=report(**changes)
    assert next(c.status for c in r.checks if c.name==name)==status
    if status=='Unsuitable':
        assert not r.can_accept(DEFAULTS,True)


def test_overrides_and_disabled_checks():
    rules=deepcopy(DEFAULTS)
    rules['allow_unknown_advisory_override']=False
    assert not report(rules).can_accept(rules,True)
    rules['weather']['enabled']=False
    assert report(rules).status=='Suitable'
    rules['darkness']['enabled']=False
    assert all(c.name!='Astronomical darkness' for c in report(rules,sun_altitudes=[20,20]).checks)
    rules['enabled']=False
    with pytest.raises(ValueError):
        save_accepted(plan(),report(rules),rules,'unused',True)


@pytest.mark.parametrize('changes',[
    {'exposure_seconds':0},{'exposure_seconds':float('nan')},
    {'start':datetime(2026,10,29,20)},
    {'end':datetime(2026,10,29,19,tzinfo=timezone.utc)},
    {'start':datetime(2026,3,29,1,30,tzinfo=ZoneInfo('Europe/London'))},
])
def test_invalid_plans(changes):
    with pytest.raises(ValueError):plan(**changes)


def test_elapsed_time_across_dst():
    zone=ZoneInfo('Europe/London')
    p=plan(start=datetime(2026,10,25,0,tzinfo=zone),end=datetime(2026,10,25,3,tzinfo=zone))
    assert p.seconds==4*3600


def test_configuration_defaults_validation_and_preservation(tmp_path):
    from configuration import save_settings_changes
    path=tmp_path/'config.toml'
    path.write_text('[planning_rules.visibility]\npreferred_min_altitude=55\n')
    assert load_rules(path)['visibility']['preferred_min_altitude']==55
    save_settings_changes(path,exposure_seconds=120)
    assert load_rules(path)['visibility']['preferred_min_altitude']==55
    for text in ['[planning_rules]\nenabled=1','[planning_rules.visibility]\nsample_interval_minutes=0','[planning_rules.exposure]\nmin_seconds=700','[planning_rules]\ntypo=true']:
        path.write_text(text)
        with pytest.raises(ValueError):load_rules(path)


def test_real_offline_astronomy():
    settings=Settings(latitude_deg=52,longitude_deg=-3)
    target=Target('M31','M31',10.6847,41.269)
    r=evaluate(plan(),target,settings,deepcopy(DEFAULTS))
    assert len(r.checks)>=10
    assert all(c.status in ('Suitable','Challenging','Unsuitable','Unknown') for c in r.checks)
    assert r.exposures>0


def test_weather_thresholds_and_staleness():
    now=datetime(2026,10,29,18,tzinfo=timezone.utc)
    weather=dict(cloud_percent=60,wind_mph=10,gust_mph=10,humidity_percent=70,temperature_celsius=10,dewpoint_celsius=0,rain=False,updated_at=now)
    r=report(weather=weather,now=now)
    assert next(c.status for c in r.checks if c.name=='Cloud cover')=='Unsuitable'
    r=report(weather=weather,now=now+timedelta(hours=4))
    assert next(c.status for c in r.checks if c.name=='Weather forecast')=='Unknown'


def test_missing_sky_samples_fail_closed():
    with pytest.raises(ValueError):report(altitudes=[float('nan'),50])



def test_simple_darkness_and_obstruction_messages():
    r=report(altitudes=[40,60],horizons=[50,50],sun_altitudes=[-15,-14])
    messages={c.name:c.message for c in r.checks}
    assert messages['Start darkness']=='Start time is before astronomical sunset'
    assert messages['End darkness']=='End time is after astronomical sunrise'
    assert messages['Start obstruction']=='Object is obscured at start time'
    assert 'End obstruction' not in messages
    assert messages['Obscured duration']=='Object is obscured for 03:54 (65%) of the total observation time'


def test_visibility_duration_interpolates_crossings_and_uses_longest_run():
    from planning import visibility_durations
    obscured,longest=visibility_durations(7200,[-1,1,-1],[-1,1,-1],[0,3600,7200])
    assert obscured==3600
    assert longest==3600
    # Uneven final sampling interval must not be treated as a full step.
    obscured,longest=visibility_durations(150,[1,1,-1],[1,1,-1],[0,120,150])
    assert obscured==15
    assert longest==135
    assert visibility_durations(60,[-1,-1],[-1,-1])==(60,0)
    assert visibility_durations(60,[1,1],[1,1])==(0,60)


def test_short_visible_window_message_and_simple_issue_list():
    from planning_ui import simple_report_messages
    r=report(altitudes=[40,60],horizons=[50,50],sun_altitudes=[-15,-14])
    issues=simple_report_messages(r)
    assert not any('sampled' in text or 'clearance' in text for _,text in issues)
    assert not any(text=='Observation includes time outside astronomical darkness' for _,text in issues)
    assert not any(text=='Object is obscured during the observation' for _,text in issues)
    r=report(altitudes=[40,60],horizons=[55,55])
    assert any(c.message=='Visible window is only 0.6 hours' for c in r.checks)
    from planning import Report, Check
    assert simple_report_messages(Report([Check('Good','Suitable','Everything fine')],10,30))==[]



@pytest.mark.parametrize('hour,message',[(20,'Observation starts at a convenient time'),(23,'Observation does not begin until late'),(0,'Observation begins in the early hours'),(5,'Observation begins in the early hours'),(6,'Observation starts at a convenient time')])
def test_fixed_checklist_order_and_timing(hour,message):
    from planning import checklist_report
    start=datetime(2026,10,29,hour,tzinfo=timezone.utc)
    p=plan(start=start,end=start+timedelta(hours=3))
    r=checklist_report(p,DEFAULTS,40,[40,50],[10,10],[-18,-20],30)
    assert [c.name for c in r.checks]==['Start altitude','Start horizon','Start night','End altitude','End horizon','End night','Observation duration','Exposure count','Start timing','Obscured duration','Limited observation duration']
    assert next(c.message for c in r.checks if c.name=='Start timing')==message
    assert all(c.status=='Suitable' for c in r.checks if c.name!='Start timing')


def test_checklist_endpoint_failures_and_short_window():
    from planning import checklist_report
    p=plan(end=datetime(2026,10,29,20,30,tzinfo=timezone.utc))
    r=checklist_report(p,DEFAULTS,40,[39,30],[40,30],[-17,-18],4)
    assert [c.status for c in r.checks[:6]]==['Unsuitable','Unsuitable','Unsuitable','Unsuitable','Unsuitable','Suitable']
    assert 'may be too short' in r.checks[6].message
    assert r.checks[7].message=='Number of exposures is small (4)'
    assert not r.can_accept(DEFAULTS,True)


def test_timing_configuration_validation(tmp_path):
    path=tmp_path/'config.toml'
    path.write_text('[planning_rules.timing]\nlate_start_hour=22\nearly_hours_end=5\n')
    assert load_rules(path)['timing']['late_start_hour']==22
    path.write_text('[planning_rules.timing]\nlate_start_hour=24\n')
    with pytest.raises(ValueError):load_rules(path)



@pytest.mark.parametrize('alt,horizon,times,expected,status',[
    ([50,50],[0,0],[0,3600],'00:00 (0 %)','Suitable'),
    ([10,10],[20,20],[0,3600],'01:00 (100 %)','Unsuitable'),
    ([10,30],[20,20],[0,3600],'00:30 (50 %)','Unsuitable'),
    ([30,30,10],[20,20,20],[0,3000,3600],'00:05 (8 %)','Unsuitable'),
])
def test_feedback_obscured_duration(alt,horizon,times,expected,status):
    from planning import checklist_report
    p=plan(end=datetime(2026,10,29,21,tzinfo=timezone.utc))
    report=checklist_report(p,DEFAULTS,40,alt,horizon,[-20]*len(alt),20,sample_seconds=times)
    check=next(c for c in report.checks if c.name=='Obscured duration')
    assert check.name=='Obscured duration'
    assert check.status==status
    assert check.message==f'The object is obscured for {expected} of the total observation time'



@pytest.mark.parametrize('alt,horizon,minimum,expected',[
    ([50,50],[0,0],40,0),
    ([30,30],[0,0],40,3600),
    ([50,50],[60,60],40,3600),
    ([30,50],[40,40],40,1800),
    ([40,40],[0,0],40,0),
    # Separate restrictions at either end leave a clear interval in the middle.
    ([30,50],[0,60],35,1800),
])
def test_combined_altitude_and_horizon_duration(alt,horizon,minimum,expected):
    from planning import limited_observation_seconds, checklist_report
    seconds=limited_observation_seconds(3600,alt,horizon,minimum,[0,3600])
    assert seconds==pytest.approx(expected)
    p=plan(end=datetime(2026,10,29,21,tzinfo=timezone.utc))
    report=checklist_report(p,DEFAULTS,minimum,alt,horizon,[-20,-20],20)
    check=report.checks[-1]
    assert check.name=='Limited observation duration'
    minutes=round(expected/60)
    assert check.message==f'The object is either below the minimum specified altitude or obscured by the local horizon for {minutes//60:02d}:{minutes%60:02d} ({expected/36:.0f} %) of the total observation time'
    assert check.status==('Suitable' if expected==0 else 'Unsuitable')


def test_checklist_exposure_count_matches_chart_without_overheads():
    from planning import evaluate_checklist
    # 37 exposures of 300 seconds; setup/download/flip settings must not reduce it.
    start=datetime(2026,10,30,20,tzinfo=timezone.utc)
    p=plan(start=start,end=start+timedelta(seconds=37*300+299),exposure_seconds=300)
    settings=Settings(latitude_deg=52,longitude_deg=-3)
    r=evaluate_checklist(p,Target('M31','M31',10.6847,41.269),settings,deepcopy(DEFAULTS))
    assert r.exposures==37
    assert next(c.message for c in r.checks if c.name=='Exposure count')=='Number of exposures is sufficient (37)'
