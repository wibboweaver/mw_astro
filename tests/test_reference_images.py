from io import BytesIO
from urllib.error import URLError
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch

import pytest
from PIL import Image
from reference_images import preview_url, preview_fov, fetch_preview, PreviewError, SURVEY


def test_query_is_coordinate_based_with_exact_colour_survey():
    query = parse_qs(urlparse(preview_url(315.4, 68.16, 0.5)).query)
    assert query['hips'] == [SURVEY]
    assert query['ra'] == ['315.4'] and query['dec'] == ['68.16']
    assert query['fov'] == ['0.5']
    assert query['format'] == ['jpg']
    assert query['width'] == query['height'] == ['600']
    assert 'object' not in query


@pytest.mark.parametrize('args', [(360, 0, 1), (0, 91, 1), (0, 0, 0), (float('nan'), 0, 1)])
def test_invalid_query(args):
    with pytest.raises(ValueError):
        preview_url(*args)


def test_automatic_fov_uses_published_size_with_limits():
    with patch('reference_images.catalogue_dimensions', return_value={'SMALL': 1, 'LARGE': 600, 'NORMAL': 40}):
        assert preview_fov('SMALL') == 0.25
        assert preview_fov('LARGE') == 10
        assert preview_fov('NORMAL') == 1
        assert preview_fov('UNKNOWN') == 1


def test_valid_jpeg_response():
    output = BytesIO()
    Image.new('RGB', (600, 600)).save(output, format='JPEG')
    with patch('reference_images.urlopen', return_value=BytesIO(output.getvalue())) as request:
        assert fetch_preview(10, 40, 1) == output.getvalue()
        assert request.call_args.kwargs['timeout'] == 12


@pytest.mark.parametrize('body', [b'<html>upstream error</html>', b'{"error": "no image"}'])
def test_non_image_responses_are_friendly_errors(body):
    with patch('reference_images.urlopen', return_value=BytesIO(body)):
        with pytest.raises(PreviewError, match='unavailable'):
            fetch_preview(10, 40, 1)


def test_network_failure_is_friendly_error():
    with patch('reference_images.urlopen', side_effect=URLError('offline')):
        with pytest.raises(PreviewError):
            fetch_preview(10, 40, 1)
