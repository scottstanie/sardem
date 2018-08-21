def rsc_bounds(rsc_data):
    """Uses the x/y and step data from a .rsc file to generate LatLonBox for .kml"""
    north = rsc_data['Y_FIRST']
    west = rsc_data['X_FIRST']
    east = west + rsc_data['WIDTH'] * rsc_data['X_STEP']
    south = north + rsc_data['FILE_LENGTH'] * rsc_data['Y_STEP']
    return {'north': north, 'south': south, 'east': east, 'west': west}


def create_kml(rsc_data, tif_filename, title="Title", desc="Description"):
    """Make a simply kml file to display a tif in Google Earth from rsc_data"""
    template = """\
<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://earth.google.com/kml/2.2">
<GroundOverlay>
    <name> {title} </name>
    <description> {description} </description>
    <Icon>
          <href> {tif_filename} </href>
    </Icon>
    <LatLonBox>
        <north> {north} </north>
        <south> {south} </south>
        <east> {east} </east>
        <west> {west} </west>
    </LatLonBox>
</GroundOverlay>
</kml>
"""
    output = template.format(
        title=title, description=desc, tif_filename=tif_filename, **rsc_bounds(rsc_data))

    return output
