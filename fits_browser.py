"""Read filesystem details and FITS headers without loading image arrays."""
from datetime import datetime
from pathlib import Path
import subprocess

from astropy.io import fits
import pandas as pd
from fits_metadata import metadata_tree_html

FITS_SUFFIXES = ('.fits', '.fit', '.fts', '.fits.gz', '.fit.gz', '.fts.gz', '.fits.fz', '.fit.fz', '.fts.fz')


def list_fits(folder):
    directory = Path(folder).expanduser()
    if not directory.is_dir():
        raise ValueError('Enter the path to an existing folder.')
    return sorted((path for path in directory.iterdir()
                   if path.is_file() and path.name.lower().endswith(FITS_SUFFIXES)),
                  key=lambda path: (path.name.casefold(), path.name))


def file_details(path):
    path = Path(path)
    stat = path.stat()
    birth = getattr(stat, 'st_birthtime', None)
    def timestamp(value):
        return datetime.fromtimestamp(value).astimezone().isoformat(sep=' ', timespec='seconds')
    return {'Name': path.name, 'Path': str(path.resolve()), 'Size (bytes)': stat.st_size,
            'Created': timestamp(birth) if birth is not None else 'Unavailable on this filesystem',
            'Modified': timestamp(stat.st_mtime)}


def read_headers(path):
    headers = []
    with fits.open(path, mode='readonly', memmap=True) as hdus:
        for index, hdu in enumerate(hdus):
            headers.append({'label': f'{index}: {hdu.name} ({type(hdu).__name__})',
                            'cards': [{'Keyword': card.keyword, 'Value': card.value,
                                       'Comment': card.comment} for card in hdu.header.cards]})
    return headers


def file_metadata_row(path, signature=None):
    """Read one table row; signature lets Streamlit invalidate cached file reads.

    Extension keywords and repeated cards get distinct columns. Header values
    retain their types where possible, so numeric columns can be sorted.
    """
    row = {'Name': Path(path).name}
    try:
        row.update(file_details(path))
        for index, header in enumerate(read_headers(path)):
            counts = {}
            for card in header['cards']:
                keyword = card['Keyword'] or '(blank)'
                counts[keyword] = counts.get(keyword, 0) + 1
                column = keyword if index == 0 else f'HDU {index}: {keyword}'
                if counts[keyword] > 1:
                    column += f' [{counts[keyword]}]'
                # Keep FITS keywords distinct from filesystem column names.
                if column in row:
                    column = f'FITS: {column}'
                value = card['Value']
                row[column] = value if isinstance(value, (str, bool, int, float)) else str(value)
    except (OSError, ValueError, TypeError, EOFError) as exc:
        row['Read error'] = str(exc)
    return row


def metadata_frame(rows):
    """Allow heterogeneous FITS values without Arrow serialization failures."""
    frame = pd.DataFrame(rows)
    for column in frame.columns:
        values = frame[column].dropna()
        if frame[column].dtype == object and not all(isinstance(value, str) for value in values):
            frame[column] = frame[column].map(lambda value: None if pd.isna(value) else str(value))
    return frame



def choose_path(kind):
    """Open a native macOS picker; cancellation leaves the selection unchanged."""
    prompt = ('choose folder with prompt "Choose a folder containing FITS images"'
              if kind == 'folder' else
              'choose file with prompt "Choose a FITS image"')
    script = ('try\nreturn POSIX path of (' + prompt + ')\n'
              'on error number -128\nreturn ""\nend try')
    result = subprocess.run(['osascript', '-e', script], capture_output=True, text=True)
    if result.returncode:
        raise OSError(result.stderr.strip() or 'The file picker could not be opened.')
    return result.stdout.rstrip('\n')


def browse_path(kind):
    import streamlit as st
    try:
        chosen = choose_path(kind)
        if not chosen:
            return
        path = Path(chosen)
        if kind == 'file' and not path.name.lower().endswith(FITS_SUFFIXES):
            st.session_state['fits_picker_error'] = 'Please choose a FITS file (.fits, .fit, .fts, .gz or .fz).'
            return
        st.session_state['fits_folder'] = str(path if kind == 'folder' else path.parent)
        st.session_state['fits_browse_mode'] = kind
        st.session_state.pop('fits_selected', None)
        if kind == 'file':
            st.session_state['fits_file'] = str(path)
        st.session_state.pop('fits_picker_error', None)
    except OSError as exc:
        st.session_state['fits_picker_error'] = f'Cannot open picker: {exc}'


def render_file_metadata(selected):
    import streamlit as st
    try:
        details = file_details(selected)
        st.subheader('FITS metadata')
        headers = read_headers(selected)
        st.caption('Only fields present in this file are shown. Data sources are inferred from keyword conventions, '
                   'not verified provenance. Header timestamps are displayed exactly as stored.')
        st.html(metadata_tree_html(selected.name, headers, details))
    except (OSError, ValueError, TypeError, EOFError) as exc:
        st.error(f'Cannot read FITS file: {exc}')


def render_page():
    import streamlit as st
    st.title('FITS browser')
    st.caption('Browse a file for categorised metadata, or a folder to compare all its FITS files.')
    cached_row = st.cache_data(show_spinner=False)(file_metadata_row)
    folder_button, file_button, refresh_button = st.columns(3)
    folder_button.button('Browse folder…', on_click=browse_path, args=('folder',))
    file_button.button('Browse file…', on_click=browse_path, args=('file',))
    file_mode = st.session_state.get('fits_browse_mode') == 'file'
    if refresh_button.button('Refresh file' if file_mode else 'Refresh folder'):
        cached_row.clear()
    if st.session_state.get('fits_picker_error'):
        st.error(st.session_state['fits_picker_error'])
    if file_mode:
        filename = st.text_input('FITS file', key='fits_file')
        if not filename.strip():
            st.info('Choose a FITS file using Browse file above.')
            return
        selected = Path(filename.strip()).expanduser()
        if not selected.name.lower().endswith(FITS_SUFFIXES):
            st.error('Please choose a FITS file (.fits, .fit, .fts, .gz or .fz).')
            return
        render_file_metadata(selected)
        return
    folder = st.text_input('Folder containing FITS images', key='fits_folder', placeholder='/path/to/images')
    if not folder.strip():
        st.info('Choose a folder or FITS file using the Browse buttons above.')
        return
    try:
        paths = list_fits(folder.strip())
    except (OSError, ValueError) as exc:
        st.error(f'Cannot read folder: {exc}')
        return
    if not paths:
        st.info('No FITS files found in this folder. Subfolders are not included.')
        return
    st.caption(f'{len(paths)} FITS file(s) found. Supports .fits, .fit, .fts, .gz and .fz variants.')
    st.subheader('Folder metadata')
    with st.spinner('Reading FITS metadata…'):
        rows = []
        for path in paths:
            try:
                stat = path.stat()
                signature = (stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size)
                rows.append(cached_row(str(path.resolve()), signature))
            except OSError as exc:
                rows.append({'Name': path.name, 'Read error': str(exc)})
        frame = metadata_frame(rows)
    st.caption('One row per file. Click a column heading to sort; scroll horizontally for more metadata. '
               'Missing fields are blank. Extension headers use an HDU prefix; repeated cards have numbered columns.')
    st.dataframe(frame, hide_index=True, width='stretch')
    if st.session_state.get('fits_selected') not in paths:
        st.session_state.pop('fits_selected', None)
    selected = st.selectbox('FITS image', paths, format_func=lambda path: path.name, key='fits_selected')
    render_file_metadata(selected)
