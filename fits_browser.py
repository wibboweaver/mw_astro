"""Read filesystem details and FITS headers without loading image arrays."""
from datetime import datetime
from pathlib import Path
import subprocess

from astropy.io import fits

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
                            'cards': [{'Keyword': card.keyword, 'Value': str(card.value),
                                       'Comment': card.comment} for card in hdu.header.cards]})
    return headers



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
        st.session_state.pop('fits_selected', None)
        if kind == 'file':
            st.session_state['fits_selected'] = path
        st.session_state.pop('fits_picker_error', None)
    except OSError as exc:
        st.session_state['fits_picker_error'] = f'Cannot open picker: {exc}'


def render_page():
    import streamlit as st
    st.title('FITS browser')
    st.caption('Browse a folder on the computer running Streamlit. Times include the local UTC offset.')
    folder_button, file_button, refresh_button = st.columns(3)
    folder_button.button('Browse folder…', on_click=browse_path, args=('folder',))
    file_button.button('Browse file…', on_click=browse_path, args=('file',))
    refresh_button.button('Refresh folder')
    if st.session_state.get('fits_picker_error'):
        st.error(st.session_state['fits_picker_error'])
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
    if st.session_state.get('fits_selected') not in paths:
        st.session_state.pop('fits_selected', None)
    selected = st.selectbox('FITS image', paths, format_func=lambda path: path.name, key='fits_selected')
    try:
        details = file_details(selected)
        st.subheader('File details')
        st.table([{'Detail': key, 'Value': str(value)} for key, value in details.items()])
        st.subheader('FITS metadata')
        headers = read_headers(selected)
        for header in headers:
            with st.expander(header['label'], expanded=True):
                st.dataframe(header['cards'], hide_index=True, width='stretch')
    except (OSError, ValueError, TypeError, EOFError) as exc:
        st.error(f'Cannot read FITS file: {exc}')
