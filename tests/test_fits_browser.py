from astropy.io import fits
import pyarrow as pa
from streamlit.testing.v1 import AppTest
import fits_browser

from fits_browser import file_metadata_row, list_fits, metadata_frame


def test_folder_rows_preserve_extensions_repeated_cards_and_missing_values(tmp_path):
    primary = fits.PrimaryHDU()
    primary.header['OBJECT'] = 'M31'
    primary.header['EXPTIME'] = 120.0
    primary.header.add_history('first')
    primary.header.add_history('second')
    extension = fits.ImageHDU(name='SCI')
    extension.header['OBJECT'] = 'extension object'
    first = tmp_path / 'a.fits'
    fits.HDUList([primary, extension]).writeto(first)
    second = tmp_path / 'b.fit.gz'
    fits.PrimaryHDU().writeto(second)
    (tmp_path / 'ignored.txt').write_text('not FITS')

    paths = list_fits(tmp_path)
    assert paths == [first, second]
    frame = metadata_frame([file_metadata_row(path) for path in paths])
    assert list(frame['Name']) == ['a.fits', 'b.fit.gz']
    assert frame.loc[0, 'OBJECT'] == 'M31'
    assert frame.loc[0, 'HDU 1: OBJECT'] == 'extension object'
    assert frame.loc[0, 'HISTORY'] == 'first'
    assert frame.loc[0, 'HISTORY [2]'] == 'second'
    assert frame.loc[0, 'EXPTIME'] == 120.0
    assert frame['EXPTIME'].isna()[1]
    assert frame['EXPTIME'].dtype.kind == 'f'
    pa.Table.from_pandas(frame)


def test_mixed_header_types_are_arrow_compatible_and_bad_files_remain_visible(tmp_path):
    paths = []
    for name, value in [('a.fits', 120.0), ('b.fits', 'unknown')]:
        hdu = fits.PrimaryHDU()
        hdu.header['EXPTIME'] = value
        path = tmp_path / name
        hdu.writeto(path)
        paths.append(path)
    broken = tmp_path / 'broken.fits'
    broken.write_text('not a FITS file')
    paths.append(broken)
    frame = metadata_frame([file_metadata_row(path) for path in paths])
    assert list(frame['EXPTIME'][:2]) == ['120.0', 'unknown']
    assert frame['EXPTIME'].isna()[2]
    assert frame.loc[2, 'Name'] == 'broken.fits'
    assert frame.loc[2, 'Read error']
    pa.Table.from_pandas(frame)


def test_browser_shows_folder_table_and_selected_details_without_original_cards(tmp_path):
    for name in ('a.fits', 'b.fits'):
        hdu = fits.PrimaryHDU()
        hdu.header['OBJECT'] = name
        hdu.writeto(tmp_path / name)
    app = AppTest.from_string('from fits_browser import render_page\nrender_page()')
    app.session_state['fits_folder'] = str(tmp_path)
    app.run()
    assert not app.exception
    assert len(app.dataframe) == 1
    assert list(app.dataframe[0].value['Name']) == ['a.fits', 'b.fits']
    assert list(app.dataframe[0].value['OBJECT']) == ['a.fits', 'b.fits']
    assert not app.expander
    assert 'FITS metadata' in [item.value for item in app.subheader]
    app.selectbox[0].select(tmp_path / 'b.fits').run()
    assert not app.exception
    assert app.selectbox[0].value == tmp_path / 'b.fits'
    hdu = fits.PrimaryHDU()
    hdu.header['OBJECT'] = 'changed'
    hdu.writeto(tmp_path / 'b.fits', overwrite=True)
    app.button[2].click().run()
    assert not app.exception
    assert app.dataframe[0].value.loc[1, 'OBJECT'] == 'changed'


def test_browse_file_reads_only_selected_file_and_switches_back_to_folder(tmp_path, monkeypatch):
    first, second = tmp_path / 'a.fits', tmp_path / 'b.fits'
    for path in (first, second):
        hdu = fits.PrimaryHDU()
        hdu.header['OBJECT'] = path.name
        hdu.writeto(path)
    monkeypatch.setattr(fits_browser, 'choose_path', lambda kind: str(second if kind == 'file' else tmp_path))
    reads = []
    original_reader = fits_browser.read_headers

    def read_headers(path):
        reads.append(path)
        return original_reader(path)

    monkeypatch.setattr(fits_browser, 'read_headers', read_headers)
    app = AppTest.from_string('from fits_browser import render_page\nrender_page()').run()
    app.button[1].click().run()
    assert not app.exception
    assert reads == [second]
    assert not app.dataframe
    assert not app.selectbox
    assert not app.expander
    assert app.text_input[0].label == 'FITS file'
    assert app.text_input[0].value == str(second)
    assert [item.value for item in app.subheader] == ['FITS metadata']

    # Refresh and cancelling a picker preserve the single-file view.
    app.button[2].click().run()
    assert not app.exception
    assert not app.dataframe
    assert all(path == second for path in reads)
    monkeypatch.setattr(fits_browser, 'choose_path', lambda kind: '')
    app.button[0].click().run()
    assert not app.exception
    assert not app.dataframe
    assert app.session_state['fits_browse_mode'] == 'file'

    monkeypatch.setattr(fits_browser, 'choose_path', lambda kind: str(second if kind == 'file' else tmp_path))
    app.button[0].click().run()
    assert not app.exception
    assert app.text_input[0].label == 'Folder containing FITS images'
    assert list(app.dataframe[0].value['Name']) == ['a.fits', 'b.fits']

    # Returning from the folder table must hide every other file again.
    reads.clear()
    app.button[1].click().run()
    assert not app.exception
    assert reads == [second]
    assert not app.dataframe
    assert not app.selectbox
    assert app.text_input[0].value == str(second)
