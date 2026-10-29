Add one .txt file per location, for example Garden.txt. Files appear in the
sidebar; select None to disable the horizon. Each non-empty line contains:

    altitude azimuth

Angles are in degrees, north=0°, east=90°, south=180°, west=270°.
Blank lines and # comments are allowed. Points may be in any order.
Use at least two distinct azimuths. Conflicting duplicate azimuths are rejected.

The horizon is linearly interpolated between points and around north (360° to
0°). Add points around the full compass for a realistic profile; large gaps
are interpolated, not assumed clear. Example.txt contains the supplied example
points, not a measured horizon for your site.

Selecting a file changes the obstruction profile only. Set geographic
latitude, longitude and height separately in the sidebar or config.toml.
The chart shows the horizon altitude in the target's direction at each time.
