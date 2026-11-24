"""Describe FITS cards and render tables within expandable logical sections."""
from html import escape
import re


# Descriptions annotate the header; they never replace values read from a file.
GROUPS = {}


def register(group, source, entries):
    for keywords, meaning in entries:
        for keyword in keywords.split():
            GROUPS[keyword] = (group, meaning, source)


register('Target', 'Selected target / sequence (inferred from keyword)', [
    ('OBJECT', 'Intended target name or label; does not verify the image contents.'),
    ('OBJCTRA', 'Intended target right ascension, usually hours, minutes and seconds; not a measured image position.'),
    ('OBJCTDEC', 'Intended target declination, usually signed degrees, arcminutes and arcseconds; not a measured image position.'),
    ('OBJCTROT', 'Planned image rotation in degrees; distinct from the actual rotator angle.'),
])
register('Exposure and timing', 'Capture settings / sequence (inferred from keyword)', [
    ('IMAGETYP', 'Exposure type, for example LIGHT, DARK, FLAT or BIAS.'),
    ('EXPTIME EXPOSURE', 'Exposure duration in seconds.'),
])
register('Exposure and timing', 'Acquisition software / clock (inferred from keyword)', [
    ('DATE-OBS DATE-UTC', 'Observation start in UTC as recorded by the acquisition software.'),
    ('DATE-LOC', 'Observation start in local time; the recorded string may omit a UTC offset.'),
    ('DATE-AVG', 'Exposure midpoint in UTC.'),
    ('DATE-END', 'Observation end time; consult TIMESYS and the header comment for the time scale.'),
    ('MJD-OBS', 'Observation start as a Modified Julian Date, in days.'),
    ('MJD-AVG', 'Exposure midpoint as a Modified Julian Date, in days.'),
    ('JD', 'Julian Date, in days; consult the header comment for the reference instant.'),
    ('TIMESYS', 'Time scale used for header timestamps.'),
])
register('Camera', 'Camera driver / camera settings (inferred from keyword)', [
    ('INSTRUME', 'Imaging instrument or camera name.'),
    ('CAMERAID', 'Camera identifier supplied by its driver.'),
    ('GAIN', 'Camera gain setting; not necessarily electrons per ADU.'),
    ('OFFSET', 'Camera baseline offset setting.'),
    ('EGAIN', 'Conversion gain in electrons per analogue-to-digital unit (ADU).'),
    ('USBLIMIT', 'Camera-specific USB traffic setting.'),
    ('READOUTM', 'Sensor readout mode.'),
    ('XBINNING YBINNING', 'Binning factor along the indicated image axis.'),
    ('XPIXSZ YPIXSZ', 'Pixel size along the indicated axis in micrometres.'),
    ('CCD-TEMP', 'Actual sensor temperature in degrees Celsius.'),
    ('SET-TEMP', 'Requested sensor cooling temperature in degrees Celsius.'),
    ('BAYERPAT', 'Colour sensor Bayer mosaic pattern.'),
    ('XBAYROFF YBAYROFF XBAYEROFF YBAYEROFF', 'Bayer mosaic alignment offset along the indicated axis.'),
])
register('Optics', 'User entered / equipment configuration (inferred from keyword)', [
    ('FOCALLEN', 'Configured effective focal length in millimetres, including any reducer or Barlow.'),
    ('FOCRATIO', 'Configured focal ratio (f-number).'),
])
register('Observing site and observer', 'User entered / site configuration (inferred from keyword)', [
    ('OBSERVER', 'Name of the person acquiring the images.'),
    ('OBSERVAT', 'Observatory name.'),
    ('SITENAME', 'Observing site name.'),
    ('SITELAT', 'Observing latitude in degrees.'),
    ('SITELONG', 'Observing longitude in degrees.'),
])
register('Observing site and observer', 'Site configuration or mount driver; version dependent (inferred from keyword)', [
    ('SITEELEV', 'Observing site elevation above sea level in metres.'),
])
register('Mount and telescope', 'Equipment configuration / mount driver (inferred from keyword)', [
    ('TELESCOP', 'Telescope name; may fall back to the mount driver name.'),
    ('RA', 'Mount-reported right ascension; distinct from the intended target and a plate-solved position. Consult the header comment for units.'),
    ('DEC', 'Mount-reported declination; distinct from the intended target and a plate-solved position. Consult the header comment for units.'),
    ('PIERSIDE', 'Side of pier reported by the mount.'),
])
register('Filters', 'Filter-wheel configuration / selection (inferred from keyword)', [
    ('FWHEEL', 'Filter wheel name.'),
    ('FILTER', 'Selected filter name.'),
])
register('Focus', 'Focuser driver / probe (inferred from keyword)', [
    ('FOCNAME', 'Focuser name.'),
    ('FOCPOS FOCUSPOS', 'Focuser position in steps.'),
    ('FOCUSSZ', 'Reported focuser step size.'),
    ('FOCTEMP FOCUSTEM', 'Focuser probe temperature in degrees Celsius.'),
])
register('Rotation', 'Rotator driver (inferred from keyword)', [
    ('ROTNAME', 'Rotator name.'),
    ('ROTATOR ROTATANG', 'Actual reported rotator angle in degrees.'),
    ('ROTSTPSZ', 'Reported rotator step size.'),
])
register('Weather and sky', 'Connected weather / sky data source (inferred from keyword)', [
    ('AMBTEMP', 'Ambient temperature in degrees Celsius.'),
    ('HUMIDITY', 'Relative humidity in percent.'),
    ('DEWPOINT', 'Dew point in degrees Celsius.'),
    ('PRESSURE', 'Air pressure in hPa.'),
    ('CLOUDCVR', 'Cloud cover in percent.'),
    ('WINDDIR', 'Wind direction in degrees: 0 north, 90 east, 180 south, 270 west.'),
    ('WINDSPD WINDGUST', 'Wind speed or gust in kilometres per hour.'),
    ('SKYTEMP', 'Sky temperature in degrees Celsius.'),
    ('SKYBRGHT', 'Sky brightness in lux.'),
    ('MPSAS', 'Sky quality in magnitudes per square arcsecond.'),
    ('STARFWHM', 'Reported stellar full width at half maximum; consult the header comment for units.'),
])
register('Image format', 'Saved image / FITS writer (inferred from keyword)', [
    ('SIMPLE', 'Whether the primary HDU conforms to the FITS standard.'),
    ('BITPIX', 'Stored pixel data type: positive values denote integer bit depth; negative values denote floating point.'),
    ('NAXIS', 'Number of data axes.'),
    ('BZERO', 'Offset in physical pixel value = BZERO + BSCALE × stored value.'),
    ('BSCALE', 'Scale factor applied to stored pixel values.'),
    ('EXTEND', 'Whether extensions may follow the primary HDU.'),
    ('ROWORDER', 'Stored image row orientation.'),
    ('XTENSION', 'FITS extension type.'),
    ('EXTNAME EXTVER', 'Extension name or version.'),
    ('PCOUNT GCOUNT', 'FITS structural parameter or group count.'),
    ('CHECKSUM DATASUM', 'Checksum used to check FITS data integrity.'),
])
register('Software and provenance', 'File creator / processing software (inferred from keyword)', [
    ('SWCREATE', 'Application, version and architecture that created the file.'),
    ('CREATOR', 'Software that created the file.'),
    ('ORIGIN', 'Organisation responsible for creating the file.'),
    ('DATE', 'File creation timestamp recorded in the header; distinct from exposure time and filesystem dates.'),
    ('COMMENT HISTORY', 'Original header commentary or processing history.'),
])

GROUP_ORDER = ['Target', 'Exposure and timing', 'Camera', 'Optics',
               'Observing site and observer', 'Mount and telescope', 'Filters',
               'Focus', 'Rotation', 'Weather and sky', 'Astrometry / WCS',
               'Image format', 'Software and provenance', 'Other headers']


def describe_keyword(keyword):
    """Return an explanation, not an assertion about a particular file's origin."""
    key = keyword.upper()
    if key in GROUPS:
        return GROUPS[key]
    if re.fullmatch(r'Z?NAXIS\d+', key):
        return ('Image format', 'Length of the indicated data axis in pixels.',
                'Saved image / FITS writer (inferred from keyword)')
    if key in {'EQUINOX', 'RADESYS', 'RADECSYS', 'WCSAXES', 'LONPOLE', 'LATPOLE', 'WCSNAME'} or re.fullmatch(
            r'(CTYPE|CRVAL|CRPIX|CDELT|CUNIT|CROTA)\d+[A-Z]?|(CD|PC|PV|PS)\d+_\d+[A-Z]?|'
            r'(A|B|AP|BP)_(ORDER|\d+_\d+)', key):
        meaning = ('Reference equinox of the celestial coordinate system.' if key == 'EQUINOX' else
                   'Coordinate-system / WCS parameter; a single keyword does not establish a complete plate solution.')
        return ('Astrometry / WCS', meaning,
                'Coordinate configuration / astrometric software (inferred from keyword)')
    return ('Other headers', 'Unrecognised or custom header field; see the original comment.',
            'Unknown — not specified by this header')


def group_cards(cards):
    """Preserve card order, repeated keywords, blank cards and original values."""
    groups = {}
    for card in cards:
        group, meaning, source = describe_keyword(card['Keyword'])
        groups.setdefault(group, []).append({**card, 'Meaning': meaning, 'Data source': source})
    return [(group, groups[group]) for group in GROUP_ORDER if group in groups]


def value_html(value):
    if isinstance(value, bool):
        kind, text = 'boolean', str(value)
    elif isinstance(value, (int, float, complex)):
        kind, text = 'number', str(value)
    elif isinstance(value, str):
        kind, text = 'string', '"' + value + '"'
    else:
        kind, text = 'other', str(value)
    return f'<span class="fits-{kind}">{escape(text)}</span>'


def branch(label, children, opened=False):
    return f'<details{" open" if opened else ""}><summary>{label}</summary><div class="fits-children">{children}</div></details>'


def metadata_table_html(rows):
    headings = ''.join(f'<th scope="col">{name}</th>' for name in ('Definition', 'Setting', 'Value', 'Source'))
    body = []
    for definition, setting, value, source, comment in rows:
        # Original comments remain available on hover and in Original header cards.
        title = f' title="{escape(comment, quote=True)}"' if comment else ''
        body.append(f'<tr><td>{escape(definition)}</td>'
                    f'<td class="fits-key"{title}>{escape(setting)}</td>'
                    f'<td>{value_html(value)}</td><td>{escape(source)}</td></tr>')
    return '<div class="fits-table-scroll"><table><thead><tr>' + headings + '</tr></thead><tbody>' + ''.join(body) + '</tbody></table></div>'


def metadata_tree_html(filename, headers, details):
    """Use native disclosure controls: no scripts, remote assets or unsafe values."""
    file_definitions = {'Name': 'File name', 'Path': 'Absolute file location',
                        'Size (bytes)': 'File size in bytes', 'Created': 'Filesystem creation time',
                        'Modified': 'Filesystem modification time'}
    file_rows = metadata_table_html((file_definitions.get(key, key), key, value, 'Filesystem', '')
                                    for key, value in details.items())
    file_rows += '<div class="fits-note">Filesystem dates are separate from exposure timestamps; offsets are shown where available.</div>'
    children = branch('File details', file_rows)
    multiple = len(headers) > 1
    for header in headers:
        groups = []
        for name, cards in group_cards(header['cards']):
            rows = []
            for card in cards:
                keyword = card['Keyword'] or '(blank card)'
                definition = card['Meaning'].split(';', 1)[0].rstrip('.')
                source = card['Data source'].removesuffix(' (inferred from keyword)')
                rows.append((definition, keyword, card['Value'], source, card['Comment']))
            groups.append(branch(f'{escape(name)} <span class="fits-note">({len(cards)} fields)</span>', metadata_table_html(rows)))
        content = ''.join(groups)
        children += branch(escape(header['label']), content, True) if multiple else content
    tree = branch(escape(filename), children, True)
    return '''<style>
    .fits-tree {font-family:inherit;font-size:0.92rem;line-height:1.6;overflow-wrap:anywhere;}
    .fits-tree summary {cursor:pointer;white-space:pre-wrap;padding:3px 0;}
    .fits-tree summary::marker {color:#30c999;}
    .fits-tree summary:focus-visible {outline:2px solid #30c999;outline-offset:2px;}
    .fits-tree .fits-children {margin-left:0.65rem;padding-left:1.1rem;border-left:1px solid #73828c55;}
    .fits-tree .fits-children>div {white-space:pre-wrap;}
    .fits-tree .fits-table-scroll {overflow-x:auto;white-space:normal !important;margin:0.5rem 0 1rem;}
    .fits-tree table {border-collapse:collapse;width:100%;table-layout:fixed;}
    .fits-tree th,.fits-tree td {text-align:left;vertical-align:top;padding:0.5rem 0.7rem;border:1px solid #73828c55;white-space:pre-wrap;overflow-wrap:anywhere;}
    .fits-tree th {font-weight:600;background:#73828c15;}
    .fits-tree th:nth-child(1) {width:34%;}
    .fits-tree th:nth-child(2) {width:16%;}
    .fits-tree th:nth-child(3) {width:25%;}
    .fits-tree th:nth-child(4) {width:25%;}
    .fits-tree td:nth-child(2),.fits-tree td:nth-child(3) {font-family:ui-monospace,SFMono-Regular,Consolas,monospace;}
    @media(max-width:700px) {.fits-tree table {min-width:650px;}}
    .fits-tree .fits-key {color:light-dark(#00617a,#62d9f5);}
    .fits-tree .fits-number {color:light-dark(#865100,#ffbd36);}
    .fits-tree .fits-string {color:light-dark(#21643a,#b8f3c8);}
    .fits-tree .fits-boolean {color:light-dark(#7040a0,#d0a3ff);}
    .fits-tree .fits-note {opacity:0.72;}
    </style><div class="fits-tree">''' + tree + '</div>'
