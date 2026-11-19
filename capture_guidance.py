"""Evidence-backed capture advice; unknown line strengths remain unknown.

SHO describes a colour mapping, not an object class or an elemental abundance.
No image-derived or invented emission percentages are used here.
"""
from dataclasses import dataclass
from object_sizes import normalise_id
import filter_recommendations as filters

DB2_SOURCE = ('ZWO DB2 transmission bands', 'https://www.zwoastro.com/product/duo-band-filters/')
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


def concise_answers(identifier):
    """Four practical answers; strength estimates are never invented from type."""
    advice = capture_guidance(identifier)
    if advice is HORSEHEAD:
        return (
            'Both — DB2 for the red emission; broadband for dust, reflection nebulosity and star colours. Prioritise DB2 if time is limited.',
            'Stack separately and align the masters. Use broadband RGB as the base; blend continuum-subtracted Hα from DB2 into red, keeping broadband stars and reflection nebulosity.',
            'Hα is prominent in the backdrop. Relative S II and O III strengths are not verified; no reliable ratio is supplied.',
            'Not needed here: use Hα + broadband RGB rather than synthetic SHO.',
        )
    if advice is REFLECTION:
        return (
            'Broadband — preserve NGC 2023’s reflected starlight and blue colour.',
            'Not needed for NGC 2023 alone. For a wider Horsehead field, use broadband RGB as the base and add Hα only to emission regions.',
            'Reflected starlight dominates the visible target; SHO line strengths are not verified.',
            'Not needed for this reflection-nebula image.',
        )
    if advice is EAGLE:
        emissions = 'Hα, O III and S II are documented. Their relative strengths are not verified here; no reliable ratio is supplied.'
    elif advice is VEIL:
        emissions = 'Hα, O III and S II are documented; their relative strengths vary between filaments. No reliable ratio is supplied.'
    elif advice.mode == 'Broadband':
        emissions = 'Broadband starlight, reflection or dust is the main imaging objective. SHO line strengths are not assessed.'
    else:
        emissions = 'Target-specific Hα, O III and S II strengths are unknown; object type alone cannot establish their proportions.'
    if advice.mode == 'Dual-band':
        return (
            'Narrowband with your DB2. Optional broadband for natural star colours.',
            'If adding broadband: align the separate stacks, process the DB2 nebula starless, then replace its stars with broadband RGB stars.',
            emissions,
            'Not needed for HOO. For synthetic SHO only: S* = 0.8 × Hα + 0.2 × O III; map R=S*, G=Hα, B=O III. This is artistic colour mixing, not measured S II. Genuine S II needs extra filtered exposures.',
        )
    if advice.mode == 'Broadband':
        return ('Broadband — capture without the DB2.',
                'Not needed unless you deliberately add separately identified emission regions.',
                emissions, 'Not needed for broadband processing.')
    return ('Needs assessment — the target classification is unknown or mixed.',
            'Choose the capture type first; no target-specific combination is recommended yet.',
            emissions, 'No target-specific need established. DB2 data cannot recover real S II.')


def guidance_markdown(identifier, heading='###'):
    capture, combine, emissions, sulphur = concise_answers(identifier)
    return (
        f'{heading} Capture guidance\n\n'
        f'- **Capture:** {capture}\n'
        f'- **Combine:** {combine}\n'
        f'- **Emissions:** {emissions}\n'
        f'- **Simulate S II:** {sulphur}'
    )


def guidance_sources(identifier):
    """Evidence is available separately without expanding the practical guidance."""
    advice = capture_guidance(identifier)
    links = ' · '.join(f'[{title}]({url})' for title, url in (*advice.sources, DB2_SOURCE))
    return f'{advice.basis} Sources: {links}'
