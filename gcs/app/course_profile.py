"""Reference diagram, not final event rules or a surveyed placement tolerance."""

PROFILE = {
    'id': 'aimm-course-concepts',
    'version': 1,
    'source': 'Course and Competition Details.pdf, course map and Dodge/Evade diagrams',
    'slalom_spacing_m': 30 * .3048,
    'channel_width_m': 40 * .3048,
    'channel_length_m': 60 * .3048,
    'connection_gap_m': 15 * .3048,
    'distance_scale_fraction': .30,
    'gate_width_m': None,
}

SLALOM = ('slalom.entrance.red', 'slalom.entrance.green',
          'slalom.turn.1', 'slalom.turn.2', 'slalom.turn.3', 'slalom.turn.4',
          'slalom.exit.red', 'slalom.exit.green')
CHANNEL = tuple(f'channel.{colour}.{i}' for i in range(1, 4) for colour in ('red', 'green'))
GATE = SLALOM[:2]  # Starting gate is an explicit alias, never a second pair.
ROLE_COLOURS = dict(zip(SLALOM, ('red', 'green', 'red', 'green', 'red', 'green', 'red', 'green')))
ROLE_COLOURS.update({role: role.split('.')[1] for role in CHANNEL})


def identity():
    return {key: PROFILE[key] for key in ('id', 'version')}
