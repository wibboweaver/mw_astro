"""Run the current sibling Astro Annotate project, including its config and canvas."""
from pathlib import Path
import importlib.util
import sys

import streamlit as st

source = Path(__file__).resolve().parents[2] / "astro-annotate" / "app.py"
if not source.is_file():
    st.error(f"Astro Annotate source was not found at {source}.")
    st.stop()

# Reset image state left by the older embedded implementation once per session.
if st.session_state.get("_annotation_source") != "live-project-v1":
    st.session_state.pop("image_id", None)
    st.session_state["_annotation_source"] = "live-project-v1"

# Execute the live source each rerun; keep its own config/cache/component paths.
spec = importlib.util.spec_from_file_location("mw_astro_annotation", source)
annotation = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = annotation
spec.loader.exec_module(annotation)
annotation.main()
st.set_page_config(page_title="Image annotator")
