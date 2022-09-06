# Copyright (c) 2019 fieldOfView
# Cura is released under the terms of the LGPLv3 or higher.
# 
# Format reference
# https://desktop.arcgis.com/en/arcmap/latest/manage-data/raster-and-images/esri-ascii-raster-format.htm


from . import ASCReader

from UM.i18n import i18nCatalog
i18n_catalog = i18nCatalog("uranium")


def getMetaData():
    return {
        "mesh_reader": [
            {
                "extension": "asc",
                "description": i18n_catalog.i18nc("@item:inlistbox", "ESRI ASCII File (DataElevationMap)")
            }
        ]
    }

def register(app):
    return {"mesh_reader": ASCReader.ASCReader()}
