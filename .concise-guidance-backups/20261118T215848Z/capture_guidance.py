"""Evidence-backed capture advice; unknown line strengths remain unknown.

SHO describes a colour mapping, not an object class or an elemental abundance.
No image-derived or invented emission percentages are used here.
"""
from dataclasses import dataclass
from object_sizes import normalise_id
import filter_recommendations as filters

DB2_SOURCE = ('ZWO DB2 transmission bands', 'https://www.zwoastro.com/product/duo-band-filters/')
RATIO_NOTE = (
    'S II : Hα : O III proportions: not available in this catalogue. '
    'Line ratios vary across a nebula; a useful number needs a published spectrum or '
    'calibrated line-flux measurement with a stated region and extinction correction. '
    'They are neither elemental abundances nor RGB palette weights. '
    'Do not infer them from a stretched colour image or use them directly as exposure-time ratios.'
)
SYNTHETIC_NOTE = (
    'Your ZWO DB2 passes Hα (656.3 nm) and O III (500.7 nm), not an isolated S II channel '
    '(671.6 / 673.1 nm). It cannot measure S II or recover its spatial structure. '
    'The extracted Hα/O III images are practical channel estimates: continuum and other '
    'lines within the passbands can contribute.'
)
SYNTHETIC_STEPS = (
    'For a synthetic SHO-style result, extract Hα and O III in your astro processor, '
    'then create an artistic substitute such as S* = Hα, or S* = 0.8 × Hα + 0.2 × O III. '
    'These example weights are creative choices, not measured sulphur proportions. '
    'Map R = S*, G = Hα, B = O III; balance colour and stretch to taste. '
    'Copying Hα adds no independent detail and can give little red/green separation. '
    'Label the result “synthetic SHO from Hα/O III”. '
    'HOO (R = Hα, G = O III, B = O III) uses the two captured line estimates more directly. '
    'For genuine SHO, add separately captured S II data using an additional compatible S II filter '
    'or S II/O III dual-band filter; those data must be registered to your existing stack.'
)

@dataclass(frozen=True)
class CaptureGuidance:
    mode: str
    reason: str
    broadband: str
    dualband: str
    lines: tuple[str, str, str]  # S II, Hα, O III; not flux ratios
    basis: str
    sources: tuple[tuple[str, str], ...] = ()

HORSEHEAD = CaptureGuidance(
    'Both',
    'For the Horsehead / IC 434 field: prioritise DB2 for the hydrogen emission backdrop; '
    'add broadband for reflected light, dust and star colours. DB2 alone is a useful first project.',
    'Capture broadband on a dark, moonless night for NGC 2023, surrounding dust and natural star colours. '
    'The Horsehead itself is an absorbing dust silhouette, not a source of SHO emission.',
    'Use the DB2 to emphasise IC 434’s Hα backdrop. Do not expect a balanced three-line SHO dataset.',
    ('Not assessed here; no target-specific strength measurement',
     'Prominent in the IC 434 backdrop',
     'No target-specific strength assessment; do not assume strong O III'),
    'Target-specific guidance for the surrounding field; line percentages are not supplied.',
    (('ESO: Horsehead and IC 434', 'https://www.eso.org/public/news/eso0202/'),
     ('NASA: emission and reflection in the Horsehead field', 'https://apod.nasa.gov/rjn/apod/ap211103.html')),
)
REFLECTION = CaptureGuidance(
    'Broadband',
    'NGC 2023’s visible reflection nebulosity is scattered starlight; broadband is the priority.',
    'Capture without the DB2 to preserve the reflection nebulosity and star colours.',
    'Optional for emission elsewhere in a wider Horsehead field; not a replacement for broadband on NGC 2023.',
    ('Not assessed', 'Not assessed; reflection light is the main imaging objective', 'Not assessed'),
    'Target-specific guidance; an emission component does not make this reflection target a three-line SHO target.',
    (('ESA/Hubble: NGC 2023', 'https://esahubble.org/images/potw1130a/'),),
)
EAGLE = CaptureGuidance(
    'Dual-band',
    'The Eagle Nebula has documented S II, Hα and O III emission. Your DB2 captures two of these bands.',
    'Optional broadband data for natural star colours and the star cluster.',
    'Prioritise DB2 data for the nebula. Genuine SHO additionally needs separately captured S II.',
    ('Documented; relative flux not supplied', 'Documented; relative flux not supplied', 'Documented; relative flux not supplied'),
    'Target-specific line presence, not an estimate of whole-nebula proportions.',
    (('NASA: Eagle Nebula emission lines', 'https://science.nasa.gov/asset/hubble/gas-pillars-in-the-eagle-nebula-m16-pillars-of-creation-in-a-star-forming-region/'),),
)
VEIL = CaptureGuidance(
    'Dual-band',
    'The Veil has documented hydrogen, sulphur and oxygen emission, tracing different filaments.',
    'Optional broadband for natural star colours and the wider stellar field.',
    'Prioritise DB2 for emission filaments; an additional S II dataset is needed for genuine SHO.',
    ('Documented in filaments; relative flux not supplied', 'Documented in filaments; relative flux not supplied', 'Documented in filaments; relative flux not supplied'),
    'Regional Veil guidance; emission morphology and line ratios vary across the remnant.',
    (('ESA/Hubble: Veil emission lines', 'https://esahubble.org/images/potw2508a/'),),
)
PROFILES = {
    **dict.fromkeys(('IC434', 'B33', 'BARNARD33', 'HORSEHEAD', 'HORSEHEADNEBULA'), HORSEHEAD),
    'NGC2023': REFLECTION,
    'M16': EAGLE, 'NGC6611': EAGLE,
    **dict.fromkeys(('NGC6960', 'NGC6992', 'NGC6995'), VEIL),
}


def capture_guidance(identifier):
    key = normalise_id(identifier)
    if key in PROFILES:
        return PROFILES[key]
    kind = filters.catalogue_types().get(key)
    unknown_lines = ('Not assessed for this target',) * 3
    if kind in filters.EMISSION_TYPES:
        return CaptureGuidance(
            'Dual-band',
            'An emission-line object: DB2 is a sensible starting point, subject to its actual line spectrum.',
            'Optional broadband for star colours, reflected light or continuum structure where present.',
            'Use DB2 for Hα/O III imaging; object type alone does not establish either line’s strength.',
            unknown_lines, f'Class-based recommendation from OpenNGC type {kind}; no verified target-specific SHO profile.')
    if kind in filters.BROADBAND_TYPES:
        return CaptureGuidance(
            'Broadband',
            'Prioritise broadband for the main starlight, reflected-light or dust structure.',
            'Capture without the DB2, preferably with low Moon interference.',
            'Only add DB2 for separately identified emission regions; it suppresses much of the main broadband signal.',
            unknown_lines, f'Class-based recommendation from OpenNGC type {kind}; no claim that emission lines are absent.')
    return CaptureGuidance(
        'Needs assessment',
        'The classification is unknown or mixed. Check which parts of this target are emission, reflection, dust or stars before choosing.',
        'Needed if reflected light, dust or stars are the main objective.',
        'Useful if Hα/O III emission is a significant part of the intended field; verify first.',
        unknown_lines, 'Insufficient target-specific evidence; no automatic capture choice or line proportions.')


def guidance_markdown(identifier, heading='###'):
    advice = capture_guidance(identifier)
    line_rows = '\n'.join(f'| {name} | {value} |' for name, value in zip(('S II — sulphur', 'Hα — hydrogen', 'O III — oxygen'), advice.lines))
    sources = (*advice.sources, DB2_SOURCE)
    links = ' · '.join(f'[{title}]({url})' for title, url in sources)
    return (
        f'{heading} Capture guidance — {advice.mode}\n\n{advice.reason}\n\n'
        f'**Broadband:** {advice.broadband}\n\n**Dual-band / narrowband:** {advice.dualband}\n\n'
        '**S II, Hα and O III emission**\n\n'
        '| Line | Evidence / expected signal |\n|---|---|\n' + line_rows + '\n\n'
        + RATIO_NOTE + '\n\n**With your DB2 filter**\n\n' + SYNTHETIC_NOTE
        + '\n\n**Synthetic S II / SHO-style colour**\n\n' + SYNTHETIC_STEPS
        + '\n\n**Capture conditions:** Broadband benefits most from dark, moonless conditions. '
        'DB2 reduces some sky background but does not remove Moon interference. '
        'Choose sub-exposure length from trial frames, star saturation and guiding; '
        'broadband versus narrowband does not by itself specify short versus long exposures.'
        + f'\n\n*Evidence: {advice.basis}*\n\nSources: {links}'
    )
