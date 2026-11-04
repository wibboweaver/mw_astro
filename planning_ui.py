"""Generate and download the Markdown imaging plan for the current chart selection."""
import hashlib
import re
from pathlib import Path
import streamlit as st
from planning import Plan, load_rules, evaluate_checklist
from planning_report import markdown_report


def render_planner(target, settings, start, exposure, profile, chart_selection, chart_first, chart_last, moon_data=None, cloud_data=None, night_rating=None):
    with st.expander('Imaging report', expanded=True):
        try:
            rules=load_rules()
            if not rules['enabled']:
                st.info('Imaging-session planning is disabled in config.toml.')
                return
            from interactive_chart import selected_interval
            begin,end=selected_interval(chart_selection,chart_first,chart_last)
            plan=Plan(target.common_name,begin.astimezone(start.tzinfo),end.astimezone(start.tzinfo),exposure)
        except (ValueError,OSError,TypeError) as exc:
            st.info(str(exc))
            actions=st.container(horizontal=True)
            actions.button('Generate report',disabled=True)
            actions.download_button('Save report',data='',file_name='imaging-plan.md',disabled=True)
            return
        centre=st.session_state.get('esa_camera_framing',{}).get('centre')
        frame_centre=None
        if centre and centre.get('view_key')==f'{target.ra_deg}:{target.dec_deg}':
            import math
            ra,dec=centre.get('ra'),centre.get('dec')
            if all(isinstance(v,(int,float)) and math.isfinite(v) for v in (ra,dec)) and 0<=ra<360 and -90<=dec<=90:
                frame_centre=(ra,dec)
        # Reports are snapshots: never offer an old plan after any input changes.
        signature=hashlib.sha256(repr((target,settings,plan,rules,profile,moon_data,cloud_data,frame_centre,night_rating,Path(__file__).with_name('planning_report.py').stat().st_mtime_ns)).encode()).hexdigest()
        if st.session_state.get('imaging_report_signature')!=signature:
            st.session_state.pop('imaging_report_markdown',None)
        actions=st.container(horizontal=True)
        if actions.button('Generate report'):
            try:
                assessment=evaluate_checklist(plan,target,settings,rules,profile,moon_data=moon_data)
                content=markdown_report(plan,target,settings,assessment,cloud_data,frame_centre=frame_centre,night_rating=night_rating)
            except (ValueError,OSError,TypeError,KeyError) as exc:
                st.error(f'Report could not be generated: {exc}')
            else:
                st.session_state['imaging_report_markdown']=content
                st.session_state['imaging_report_signature']=signature
        content=st.session_state.get('imaging_report_markdown','')
        filename=re.sub(r'[^A-Za-z0-9_-]+','-',target.object_id).strip('-') or 'target'
        actions.download_button('Save report',data=content,file_name=f'{filename}-{plan.start:%Y-%m-%d}.md',mime='text/markdown',disabled=not content)
        if content:
            with st.container(key='imaging_report_content'):
                # Keep tables at full width; the 16% status column fits Favourable,
                # with Notes taking the remaining width after the fixed columns.
                st.html('<style>.st-key-imaging_report_content table{width:100%;table-layout:fixed}.st-key-imaging_report_content th,.st-key-imaging_report_content td{overflow-wrap:anywhere}.st-key-imaging_report_content table:has(th:nth-child(4)) th:nth-child(1){width:22%}.st-key-imaging_report_content table:has(th:nth-child(4)) th:nth-child(2){width:16%}.st-key-imaging_report_content table:has(th:nth-child(4)) th:nth-child(3){width:14%}.st-key-imaging_report_content table:not(:has(th:nth-child(4))) th:first-child{width:36%}</style>')
                graphic=re.search(r'<!-- NIGHT_RATING_START -->(.*?)<!-- NIGHT_RATING_END -->',content,re.S)
                if graphic:
                    st.markdown(content[:graphic.start()])
                    st.html(graphic.group(1))
                    st.markdown(content[graphic.end():])
                else:
                    st.markdown(content)
        else:
            st.caption('Generate a report for the selected chart interval. Save report downloads the Markdown file.')

_loaded_source_stamp=Path(__file__).stat().st_mtime_ns
