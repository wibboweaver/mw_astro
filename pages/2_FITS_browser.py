"""Streamlit FITS browser page."""
import streamlit as st
from fits_browser import render_page

st.set_page_config(page_title='FITS browser', layout='wide')
render_page()
