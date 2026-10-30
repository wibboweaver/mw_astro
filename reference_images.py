"""DSS2 colour reference cutouts from the documented CDS HiPS2FITS service."""
from functools import lru_cache
from io import BytesIO
from pathlib import Path
import csv
import math
import logging
from urllib.parse import urlencode
from urllib.request import urlopen

from PIL import Image
from catalogue import DATA_DIR

ENDPOINT = 'https://alasky.cds.unistra.fr/hips-image-services/hips2fits'
MIRROR_ENDPOINT = 'https://alaskybis.cds.unistra.fr/hips-image-services/hips2fits'
SURVEY = 'CDS/P/DSS2/color'
MAX_BYTES = 8 * 1024 * 1024


class PreviewError(Exception):
    """The survey service did not return a usable reference image."""


@lru_cache(maxsize=1)
def catalogue_dimensions():
    sizes = {}
    for name in ('NGC.csv', 'addendum.csv'):
        with (DATA_DIR / name).open(encoding='utf-8-sig', newline='') as handle:
            for row in csv.DictReader(handle, delimiter=';'):
                try:
                    size = float(row['MajAx'])
                except (ValueError, TypeError):
                    continue
                if math.isfinite(size) and size > 0:
                    sizes[row['Name']] = size
    return sizes


def preview_fov(object_id):
    """Fit the published major axis plus 50% padding; unknown size uses 1°."""
    arcmin = catalogue_dimensions().get(object_id)
    return max(0.25, min(10.0, arcmin * 1.5 / 60)) if arcmin else 1.0


def preview_url(ra_deg, dec_deg, fov_deg):
    if not all(math.isfinite(v) for v in (ra_deg, dec_deg, fov_deg)):
        raise ValueError('Image coordinates and field of view must be finite.')
    if not 0 <= ra_deg < 360 or not -90 <= dec_deg <= 90 or not 0.1 <= fov_deg <= 10:
        raise ValueError('Invalid image coordinates or field of view.')
    return ENDPOINT + '?' + urlencode({
        'hips': SURVEY, 'ra': ra_deg, 'dec': dec_deg, 'fov': fov_deg,
        'width': 600, 'height': 600, 'projection': 'TAN', 'coordsys': 'icrs',
        'rotation_angle': 0, 'format': 'jpg',
    })



def _jpeg(content):
    if len(content)>MAX_BYTES:
        raise ValueError('Image response is too large.')
    with Image.open(BytesIO(content)) as image:
        if image.format!='JPEG' or image.size!=(600,600):
            raise ValueError('Unexpected image format or size.')
        image.verify()
    return content


def _download(url, timeout=12, limit=MAX_BYTES):
    with urlopen(url,timeout=timeout) as response:
        content=response.read(limit+1)
    if len(content)>limit:
        raise ValueError('Response is too large.')
    return content


def fetch_preview(ra_deg,dec_deg,fov_deg):
    url=preview_url(ra_deg,dec_deg,fov_deg)
    last_error=None
    for endpoint in (ENDPOINT,MIRROR_ENDPOINT):
        try:
            return _jpeg(_download(endpoint+'?'+url.split('?',1)[1],timeout=6))
        except (OSError,ValueError) as exc:
            last_error=exc
            logging.getLogger(__name__).warning('DSS2 provider %s failed: %s',endpoint,exc)
    raise PreviewError('DSS2 colour preview is currently unavailable. Please retry later.') from last_error


_loaded_source_stamp = Path(__file__).stat().st_mtime_ns
