"""mw_astro entry point. Run with: streamlit run app.py."""
import streamlit as st

st.set_page_config(page_title="Planner", layout="wide")
page = st.navigation([
    st.Page("planner.py", title="Planner", default=True),
    st.Page("pages/4_Annotate_Image.py", title="Image annotator", url_path="Annotate_Image"),
    st.Page("pages/2_FITS_browser.py", title="FITS browser", url_path="FITS_browser"),
    st.Page("pages/3_Sequence_analyser.py", title="Sequence analyser", url_path="Sequence_analyser"),
])
page.run()
