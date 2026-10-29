
from astroquery.simbad import Simbad
from astropy.coordinates import SkyCoord


def resolve_object(name: str):
    """Resolve an astronomical object using SIMBAD."""
    result = Simbad.query_object(name)

    if result is None:
        raise ValueError(f"Object not found: {name}")

    coord = SkyCoord(
        result["ra"][0],
        result["dec"][0],
        unit=("deg", "deg"),
        frame="icrs",
    )

    return {
        "name": result["main_id"][0],
        "ra_deg": coord.ra.deg,
        "dec_deg": coord.dec.deg,
    }

if __name__ == "__main__":
    name = input("Object name or ID: ")
    print(resolve_object(name))
