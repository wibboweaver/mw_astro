from datetime import datetime,timedelta,timezone
import pytest
from configuration import Settings
from targets import Target
from planning import Plan,Report,Check
from planning_report import markdown_report

@pytest.mark.parametrize('status,decision',[('Suitable','GO'),('Challenging','GO'),('Unsuitable','NO GO'),('Unknown','NO GO')])
def test_decision_setup_and_markdown(status,decision):
    start=datetime(2026,11,3,23,tzinfo=timezone.utc)
    plan=Plan('M31',start,start+timedelta(hours=2),300)
    target=Target('Andromeda','M31',10.6847,41.269)
    result=markdown_report(plan,target,Settings(latitude_deg=52,longitude_deg=-3),Report([Check('Test',status,'Test result')],24,120))
    assert '**GO' not in result and '**NO GO' not in result
    assert 'deal breaker' not in result.lower()
    assert 'Pass/Fail' not in result
    assert '04 November 2026, 01:00' in result
    assert '| Exposure | 300 seconds |' in result
    assert result.count('## Observation Criteria')==1
    assert 'Sequence:' not in result
    assert '| Filter selection |' not in result
    assert '| Capture overheads |' not in result
    assert '| Filter recommendation |' in result
    assert 'unavailable' in result
    assert result.count('| Criterion | Status | Potential Impact | Notes |')==2
    assert '### Favourable criteria' in result
    assert '### Criteria to review on site' in result
    assert 'Forecast source' not in result and 'Decision scope' not in result
    passed,consider=result.split('### Favourable criteria')[1].split('### Criteria to review on site')
    assert ('| Test |' in passed)==(status=='Suitable')
    assert ('| Test |' in consider)==(status!='Suitable')


@pytest.mark.parametrize('status',['Suitable','Challenging','Unsuitable','Unknown'])
def test_frame_information_and_independent_potential_impact(status):
    start=datetime(2026,11,3,23,tzinfo=timezone.utc)
    plan=Plan('M31',start,start+timedelta(hours=2),300)
    target=Target('Andromeda','M31',10.6847,41.269)
    result=markdown_report(plan,target,Settings(latitude_deg=52,longitude_deg=-3,frame_rotation_deg=72),Report([Check('Start night',status,'Darkness check')],24,120),frame_centre=(15,40))
    assert '## Capture Information (NINA)' in result
    assert '| Frame centre (J2000) | RA 01:00:00.0 · Dec +40:00:00 |' in result
    assert '| Frame angle | 72° |' in result
    assert result.index('| Catalogue centre')<result.index('| Frame centre')<result.index('| Frame angle')
    assert 'Temperature / gain' not in result and 'Framing and rotation' not in result
    row=next(line for line in result.splitlines() if line.startswith('| Start night |'))
    assert row.split('|')[3].strip()=='High'
    for row in result.splitlines():
        if row.startswith('| ') and len(row.split('|'))==6 and 'Criterion' not in row and not row.startswith('| None '):
            assert row.split('|')[3].strip() in ('High','Medium','Low')


@pytest.mark.parametrize('identifier,label',[('M31','No filter'),('M57','Dualband Filter'),('CUSTOM','Unknown — object classification is inconclusive')])
def test_filter_label_distinguishes_broadband_and_unknown(identifier,label):
    start=datetime(2026,11,3,23,tzinfo=timezone.utc)
    result=markdown_report(Plan('Target',start,start+timedelta(hours=2),300),Target('Target',identifier,10,40),Settings(latitude_deg=52,longitude_deg=-3),Report([],24,120))
    assert '| Filter recommendation | '+label+' |' in result


def test_report_frame_fit_rejects_small_objects_without_hiding_target(monkeypatch):
    import object_sizes
    monkeypatch.setattr(object_sizes,'catalogue_sizes',lambda:{'CUSTOM':(1,0.5)})
    start=datetime(2026,11,3,23,tzinfo=timezone.utc)
    result=markdown_report(Plan('Tiny',start,start+timedelta(hours=2),300),Target('Tiny','CUSTOM',10,40),Settings(latitude_deg=52,longitude_deg=-3),Report([],24,120))
    assert '| Frame fit | Review on site | Medium |' in result
    assert '| Object pixels |' not in result
    assert '| Frame coverage |' not in result
    assert result.count('| Frame fit |')==1
    assert 'The selected object covers ' in result and 'of the frame which is approximately ' in result
    assert result.index('| Frame fit |')>result.index('### Criteria to review on site')


@pytest.mark.parametrize('status,oversized,expected',[('Pass',False,'Pass'),('Fail',False,'Fail'),('Pass',True,'Fail'),('Unknown',None,'Unknown')])
def test_single_frame_fit_criterion_and_simple_notes(monkeypatch,status,oversized,expected):
    monkeypatch.setattr('planning_report.frame_metrics',lambda *args:dict(coverage='1.4% × 1.2%',pixels='87 × 50',status=status,oversized=oversized))
    start=datetime(2026,11,3,23,tzinfo=timezone.utc)
    result=markdown_report(Plan('Target',start,start+timedelta(hours=2),300),Target('Target','CUSTOM',10,40),Settings(latitude_deg=52,longitude_deg=-3),Report([Check('Frame fit','Suitable','Duplicate')],24,120))
    nina,criteria=result.split('## Observation Criteria')
    assert 'Frame fit' not in nina and 'Frame coverage' not in nina and 'Object pixels' not in nina
    assert result.count('| Frame fit |')==1
    assert '| Frame containment |' not in result
    passed,failed=criteria.split('### Criteria to review on site')
    assert ('| Frame fit |' in passed)==(expected=='Pass')
    assert ('| Frame fit |' in failed)==(expected!='Pass')
    display={'Pass':'Favourable','Fail':'Review on site','Unknown':'Not assessed'}[expected]
    assert f'| Frame fit | {display} | Medium | The selected object covers 1.4% x 1.2% of the frame which is approximately 87 x 50 pixels.' in result



def test_twilight_report_uses_advisory_status_and_full_window_totals():
    from planning import checklist_report,DEFAULTS
    start=datetime(2026,11,3,23,tzinfo=timezone.utc)
    plan=Plan('M31',start,start+timedelta(hours=1),300)
    assessment=checklist_report(plan,DEFAULTS,40,[50,50],[0,0],[-20,-15],12)
    result=markdown_report(plan,Target('M31','M31',10,40),Settings(latitude_deg=52,longitude_deg=-3),assessment)
    assert '| End night | Review on site |' in result
    assert 'Astronomical twilight is occurring' in result
    assert 'Astronomical night: 00:24; astronomical twilight: 00:36; brighter conditions: 00:00' in result
    assert '| Status |' in result and '| Pass |' not in result and '| Fail |' not in result
    assert 'deal breaker' not in result.lower()
    assert 'assess a trial exposure' in result



def test_report_contains_same_circular_rating_and_its_window():
    from night_rating import rating_gauge
    start=datetime(2026,11,4,18,tzinfo=timezone.utc)
    plan=Plan('M31',start,start+timedelta(hours=2),300)
    rating=dict(score=87,reason='Clear window',start=start.timestamp(),end=(start+timedelta(hours=3)).timestamp())
    result=markdown_report(plan,Target('M31','M31',10,40),Settings(latitude_deg=52,longitude_deg=-3),Report([],24,120),night_rating=rating)
    assert rating_gauge(87,'Clear window') in result
    assert result.index('NIGHT_RATING_START')<result.index('## Capture Information (NINA)')
    assert 'may differ from the selected capture interval' in result
    rating.update(score=None,reason='Catalogue dimensions unavailable')
    result=markdown_report(plan,Target('M31','M31',10,40),Settings(latitude_deg=52,longitude_deg=-3),Report([],24,120),night_rating=rating)
    assert 'Night rating: Missing data' in result and 'Missing data — Catalogue dimensions unavailable' in result
    assert 'NIGHT_RATING_START' in result
