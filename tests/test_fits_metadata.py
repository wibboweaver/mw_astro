"""FITS grouping must not lose cards or interpret their contents as markup."""
from astropy.io import fits

from fits_browser import read_headers
from fits_metadata import group_cards, metadata_tree_html


def card(keyword, value, comment=''):
    return {'Keyword': keyword, 'Value': value, 'Comment': comment}


def test_groups_preserve_unknown_repeated_blank_and_typed_cards():
    cards = [card('OBJECT', 'M31'), card('EXPTIME', 2.0), card('SIMPLE', True),
             card('CUSTOM', 'user data'), card('HISTORY', 'first'),
             card('HISTORY', 'second'), card('', 'blank commentary')]
    groups = dict(group_cards(cards))
    assert groups['Target'][0]['Value'] == 'M31'
    assert groups['Exposure and timing'][0]['Value'] == 2.0
    assert groups['Image format'][0]['Value'] is True
    assert [row['Value'] for row in groups['Software and provenance']] == ['first', 'second']
    assert [row['Keyword'] for row in groups['Other headers']] == ['CUSTOM', '']
    assert sum(len(rows) for rows in groups.values()) == len(cards)
    assert 'Unknown' in groups['Other headers'][0]['Data source']


def test_wcs_and_target_pointing_are_distinct():
    groups = dict(group_cards([card('OBJCTRA', '00 00 00'), card('RA', 12.0),
                              card('CRVAL1', 10.0), card('CD1_1', 0.1),
                              card('A_2_0', 0.001), card('EQUINOX', 2000)]))
    assert 'not a measured image position' in groups['Target'][0]['Meaning']
    assert 'Mount-reported' in groups['Mount and telescope'][0]['Meaning']
    assert len(groups['Astrometry / WCS']) == 4


def test_tree_escapes_all_file_content_and_keeps_timestamps():
    timestamp = '2026-11-21T14:52:41.8340590'
    html = metadata_tree_html('<img src=x>', [
        {'label': '<HDU>', 'cards': [card('OBJECT', '<script>alert(1)</script>', '<b>comment</b>'),
                                   card('DATE-OBS', timestamp)]},
        {'label': '<extension>', 'cards': [card('FILTER', 'Ha')]},
    ], {'Path': '<unsafe>'})
    assert '<script>' not in html and '<img src=x>' not in html
    assert '&lt;script&gt;' in html and '&lt;b&gt;comment&lt;/b&gt;' in html
    assert '&lt;extension&gt;' in html and '&lt;unsafe&gt;' in html
    assert timestamp in html
    assert 'Selected target / sequence' in html
    assert '<th scope="col">Definition</th><th scope="col">Setting</th><th scope="col">Value</th><th scope="col">Source</th>' in html
    assert '<td class="fits-key">DATE-OBS</td>' in html
    # File, file details, two HDUs and three groups; no per-field branches.
    assert html.count('<details') == 7
    assert '<details open>' in html


def test_reader_keeps_extensions_duplicate_cards_and_values(tmp_path):
    primary = fits.PrimaryHDU()
    primary.header['OBJECT'] = 'Test M31'
    primary.header['DATE-OBS'] = '2026-11-21T14:52:41.8340590'
    primary.header['EXPTIME'] = 2.0
    primary.header.add_history('first')
    primary.header.add_history('second')
    extension = fits.ImageHDU(name='SCI')
    extension.header['CUSTOM'] = 'extension metadata'
    path = tmp_path / 'test.fits'
    fits.HDUList([primary, extension]).writeto(path)
    headers = read_headers(path)
    assert len(headers) == 2
    assert [row['Value'] for row in headers[0]['cards'] if row['Keyword'] == 'HISTORY'] == ['first', 'second']
    assert next(row['Value'] for row in headers[0]['cards'] if row['Keyword'] == 'EXPTIME') == 2.0
    assert next(row['Value'] for row in headers[0]['cards'] if row['Keyword'] == 'SIMPLE') is True
    assert headers[1]['cards'][-1]['Value'] == 'extension metadata'
