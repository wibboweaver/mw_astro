"""Fix empty progress-cell labels in the installed Streamlit frontend.

Run with the app's Python after reinstalling Streamlit. Numeric progress bars
are untouched; missing progress cells use the dataframe's placeholder text.
"""
from pathlib import Path
import streamlit
import shutil

BEFORE='[`checkbox`,`line_chart`,`bar_chart`,`progress`].includes(i.kind)?r():g_(n,l)'
AFTER='[`checkbox`,`line_chart`,`bar_chart`].includes(i.kind)?r():g_(n,l)'


def patch_renderer(source):
    if source.count(BEFORE)==1:
        source=source.replace(BEFORE,AFTER,1)
    elif AFTER not in source:
        raise RuntimeError('Unsupported Streamlit renderer; no changes made.')
    start=source.index('function Zh(')
    end=source.index('Zh.isEditableType',start)
    progress=source[start:end]
    before='getCell(e){if(O(e))return zu();'
    after='getCell(e){if(O(e))return zu(!0);'
    if progress.count(before)==1:
        progress=progress.replace(before,after,1)
    elif after not in progress:
        raise RuntimeError('Unsupported progress-cell renderer; no changes made.')
    return source[:start]+progress+source[end:]


def main():
    frontend=Path(streamlit.__file__).parent/'static'/'static'/'js'
    candidates=list(frontend.glob('DataFrame.*.js'))
    matching=[path for path in candidates if BEFORE in path.read_text() or AFTER in path.read_text()]
    if len(matching)!=1:
        raise RuntimeError('Cannot identify a unique Streamlit renderer; no changes made.')
    path=matching[0]
    original=path.read_text()
    updated=patch_renderer(original)
    if updated!=original:
        path.write_text(updated)
    # Streamlit assets have immutable hashed URLs. Give the patched bundle a
    # separate directory so existing browsers do not reuse unpatched bytes.
    versioned=frontend.with_name('js-rating-labels-v1')
    shutil.copytree(frontend,versioned,dirs_exist_ok=True)
    index=frontend.parent.parent/'index.html'
    content=index.read_text()
    content=content.replace('./static/js/','./static/js-rating-labels-v1/')
    index.write_text(content)
    print('Missing progress-cell labels enabled with fresh asset URLs; numeric bars unchanged.')


if __name__=='__main__':
    main()
