"""Inline imaging checklist, driven by chart selections and sidebar exposure."""
from pathlib import Path
import streamlit as st
import configuration
from planning import Plan, load_rules, evaluate_checklist, save_accepted


GROUPS = (
    ('Observation start time', ('Start altitude','Start horizon','Start night')),
    ('Observation end time', ('End altitude','End horizon','End night')),
    ('Observation window', ('Observation duration','Exposure count','Start timing','Obscured duration','Limited observation duration')),
)
PENDING = (
    'Object is above the minimum altitude', 'Object is above the local horizon',
    'Astronomical night is occurring',
)


def render_planner(target, settings, start, exposure, profile, chart_selection, chart_first, chart_last, moon_data=None, cloud_data=None):
    try:
        rules=load_rules()
    except (OSError,ValueError,TypeError) as exc:
        st.error(f'Check planning_rules in config.toml: {exc}')
        return
    if not rules['enabled']:
        st.info('Imaging-session planning is disabled in config.toml.')
        return
    with st.expander('Observation Feedback'):
        st.write(f'Exposure: {exposure:g} seconds · {settings.timezone}')
        plan=report=None
        error=None
        try:
            from interactive_chart import selected_interval
            begin,end=selected_interval(chart_selection,chart_first,chart_last)
            plan=Plan(target.common_name,begin.astimezone(start.tzinfo),end.astimezone(start.tzinfo),exposure)
            report=evaluate_checklist(plan,target,settings,rules,profile,moon_data=moon_data)
        except (ValueError,OSError) as exc:
            error=str(exc)
        if error:
            st.error(error)
        by_name={c.name:c for c in report.checks} if report else {}
        for index,(heading,names) in enumerate(GROUPS):
            instant=plan.start if plan and index==0 else plan.end if plan and index==1 else None
            title=heading+(f' — {instant:%d %b %H:%M}' if instant else '')
            st.markdown(f'<h3 style="color:#4c9be8;font-size:clamp(16px,3.5vw,25px);font-weight:500;margin:16px 0 10px">{title}</h3>',unsafe_allow_html=True)
            for position,name in enumerate(names):
                check=by_name.get(name)
                if check:
                    st.markdown(f'{"✅" if check.status=="Suitable" else "❌"} {check.message}')
                else:
                    label=PENDING[position] if index<2 else ('Total observation time is sufficient','Number of exposures is sufficient','Observation starts at a convenient time','The object is obscured for hh:mm (x %) of the total observation time','The object is either below the minimum specified altitude or obscured by the local horizon for hh:mm (x %) of the total observation time')[position]
                    st.markdown(f'— {label} (select start and stop times)')
        st.markdown('<h3 style="color:#4c9be8;font-size:clamp(16px,3.5vw,25px);font-weight:500;margin:16px 0 10px">Moon illumination</h3>',unsafe_allow_html=True)
        feedback=report.moon_feedback if report else None
        if feedback:
            from datetime import datetime
            if not feedback['enabled']:
                st.write('Moonlight interference assessment is disabled')
            elif not feedback['intervals']:
                st.write('No significant moonlight interference expected during this observation')
            else:
                for interval in feedback['intervals']:
                    begin=datetime.fromtimestamp(interval['start']/1000,plan.start.tzinfo)
                    end=datetime.fromtimestamp(interval['end']/1000,plan.start.tzinfo)
                    st.write(f'Interference within your selected observation starts at {begin:%H:%M}')
                    st.write(f'Interference within your selected observation ends at {end:%H:%M}')
                st.write(f"Possible interference covers {feedback['percent']:.0f} % ({feedback['duration']}) of the total observation time")
            if not feedback['intervals'] and feedback['enabled']:
                st.write('Possible interference covers 0 % (00:00) of the total observation time')
            st.write(f"Moon phase at observation start: {feedback['phase']} — {feedback['illumination']:.0f}% illuminated")
        else:
            st.write('Select start and stop times to assess moonlight interference')
        st.markdown('<h3 style="color:#4c9be8;font-size:clamp(16px,3.5vw,25px);font-weight:500;margin:16px 0 10px">Cloud cover</h3>',unsafe_allow_html=True)
        if report and cloud_data is not None:
            from cloud_forecast import summarise_cloud_window
            from datetime import datetime
            cloud=summarise_cloud_window(cloud_data,plan.start,plan.end)
            report.cloud_feedback=cloud
            known=cloud['average'] is not None
            partial=cloud['missing_seconds']>.5
            def cloud_row(label,value,good):
                symbol='—' if value is None or partial else '✅' if good else '❌'
                st.write(f'{symbol} {label}: {value:.0f}%' if value is not None else f'— {label}: unavailable')
            cloud_row('Average forecast cloud cover',cloud['average'],known and cloud['average']<=cloud['limit'])
            cloud_row('Highest forecast cloud cover',cloud['highest'],known and cloud['highest']<=cloud['limit'])
            if known:
                mark='—' if partial else '✅' if cloud['exceeded_percent']==0 else '❌'
                st.write(f"{mark} Cloud cover exceeds your preferred limit ({cloud['limit']:g}%) for: {cloud['exceeded_percent']:.0f}% ({cloud['exceeded_duration']}) of the observation")
            else:
                st.write('— Time above your preferred cloud-cover limit: unavailable')
            retrieved=cloud['retrieved_at']
            timestamp=datetime.fromisoformat(retrieved).astimezone(plan.start.tzinfo).strftime('%d %b, %H:%M') if retrieved else 'unavailable'
            st.write(f'Forecast retrieved: {timestamp} · Open-Meteo')
            if partial:
                st.write(f"Forecast unavailable for {cloud['missing_duration']} of the observation")
                if known:st.write('Average and highest cloud cover use only the available forecast period.')
            if cloud['error']:st.write(cloud['error'])
        else:
            for label in ('Average forecast cloud cover','Highest forecast cloud cover','Time above your preferred cloud-cover limit','Forecast retrieved'):
                st.write(f'— {label}: select start and stop times')
        if report:
            needs_ack=any(c.status=='Challenging' for c in report.checks)
            # Key acknowledgements to the actual plan, so editing invalidates consent.
            ack_key=f'plan_ack:{target.object_id}:{plan.start.isoformat()}:{plan.end.isoformat()}:{exposure}:{rules}'
            acknowledged=st.checkbox('I have reviewed the warnings',key=ack_key) if needs_ack else False
            if st.button('Accept plan',disabled=not report.can_accept(rules,acknowledged)):
                try:
                    path=save_accepted(plan,report,rules,configuration.CONFIG_PATH.parent/'plans',acknowledged)
                except (OSError,ValueError) as exc:
                    st.error(f'Plan could not be saved: {exc}')
                else:
                    st.session_state['accepted_plan_path']=str(path)
                    st.success('Accepted plan saved. Execution is not armed.')
        accepted=st.session_state.get('accepted_plan_path')
        if accepted and Path(accepted).exists():
            st.download_button('Download accepted plan',Path(accepted).read_bytes(),file_name=Path(accepted).name,mime='application/json')

def simple_report_messages(report):
    """Show issues only, without duplicated aggregate checks or technical labels."""
    names={c.name for c in report.checks if c.status != 'Suitable'}
    hidden=set()
    if names & {'Start darkness','End darkness'}:
        hidden.add('Astronomical darkness')
    if names & {'Start obstruction','End obstruction','Obscured duration'}:
        hidden.add('Local horizon')
    return [(c.status,c.message) for c in report.checks if c.status != 'Suitable' and c.name not in hidden]
