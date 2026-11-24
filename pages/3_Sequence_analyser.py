"""Streamlit NINA sequence analyser page."""
import streamlit as st
from sequence_analyser import render_page

st.set_page_config(page_title='Sequence analyser', layout='wide')
render_page()
