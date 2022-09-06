# Copyright (c) 2019 fieldOfView, Ultimaker B.V.
# Cura is released under the terms of the LGPLv3 or higher.

# This AMF ASC parser is based on the AMF ASC parser in legacy cura:
# https://github.com/daid/LegacyCura/blob/ad7641e059048c7dcb25da1f47c0a7e95e7f4f7c/Cura/util/meshLoaders/asc.py
from UM.MimeTypeDatabase import MimeTypeDatabase, MimeType
from cura.CuraApplication import CuraApplication
from UM.Logger import Logger

from UM.Mesh.MeshData import MeshData, calculateNormalsFromIndexedVertices
from UM.Mesh.MeshReader import MeshReader

from cura.Scene.CuraSceneNode import CuraSceneNode
from cura.Scene.SliceableObjectDecorator import SliceableObjectDecorator
from cura.Scene.BuildPlateDecorator import BuildPlateDecorator
from cura.Scene.ConvexHullDecorator import ConvexHullDecorator
from UM.Scene.GroupDecorator import GroupDecorator

import numpy
import trimesh
import os.path
import zipfile

MYPY = False
try:
    if not MYPY:
        import xml.etree.cElementTree as ET
except ImportError:
    import xml.etree.ElementTree as ET

from typing import Dict


class ASCReader(MeshReader):
    def __init__(self) -> None:
        super().__init__()
        self._supported_extensions = [".asc"]
        self._namespaces = {}   # type: Dict[str, str]

        MimeTypeDatabase.addMimeType(
            MimeType(
                name = "application/x-asc",
                comment = "ASC",
                suffixes = ["asc"]
            )
        )

    def getHeaderField(self, line, expected_name):
        # Logger.log("i", "getHeader field. line  %s expected %s" % (line, expected_name))
        l1 = line.split(" ")
        if l1[0] != expected_name:
            return None
        else:
            return l1[1]


    # Main entry point
    # Reads the file, returns a SceneNode (possibly with nested ones), or None
    def _read(self, file_name):
        base_name = os.path.basename(file_name)
        raw_file = open(file_name, "r")


        
        """ NCOLS 20
            NROWS 20
            XLLCENTER 724980
            YLLCENTER 4449560
            CELLSIZE 10
            NODATA_VALUE -9999.0"""

        self.header_fields = ["NCOLS", "NROWS","XLLCENTER","YLLCENTER","CELLSIZE","NODATA_VALUE"]
        self.header = {}
        for field_name in self.header_fields:
            field_value = self.getHeaderField(raw_file.readline(),field_name)
            if field_value == None:
                Logger.log("e", "Header field %s not found in %s" % (field_name, file_name))
                raw_file.close()
                return None
            else:
                self.header[file_name] = field_value
                Logger.log("i","Header field %s found with value %s"%(field_name,field_value))
    

        Logger.log("i","Header processed successfully")
        
        
        try:
            asc_document = ET.fromstring(xml_document)
        except ET.ParseError:
            Logger.log("e", "Could not parse XML in file %s" % base_name)
            return None

        if "unit" in asc_document.attrib:
            unit = asc_document.attrib["unit"].lower()
        else:
            unit = "millimeter"
        if unit == "millimeter":
            scale = 1.0
        elif unit == "meter":
            scale = 1000.0
        elif unit == "inch":
            scale = 25.4
        elif unit == "feet":
            scale = 304.8
        elif unit == "micron":
            scale = 0.001
        else:
            Logger.log("w", "Unknown unit in asc: %s. Using mm instead." % unit)
            scale = 1.0

        nodes = []
        for asc_object in asc_document.iter("object"):
            for asc_mesh in asc_object.iter("mesh"):
                asc_mesh_vertices = []
                for vertices in asc_mesh.iter("vertices"):
                    for vertex in vertices.iter("vertex"):
                        for coordinates in vertex.iter("coordinates"):
                            v = [0.0, 0.0, 0.0]
                            for t in coordinates:
                                if t.tag == "x":
                                    v[0] = float(t.text) * scale
                                elif t.tag == "y":
                                    v[2] = -float(t.text) * scale
                                elif t.tag == "z":
                                    v[1] = float(t.text) * scale
                            asc_mesh_vertices.append(v)
                if not asc_mesh_vertices:
                    continue

                indices = []
                for volume in asc_mesh.iter("volume"):
                    for triangle in volume.iter("triangle"):
                        f = [0, 0, 0]
                        for t in triangle:
                            if t.tag == "v1":
                                f[0] = int(t.text)
                            elif t.tag == "v2":
                                f[1] = int(t.text)
                            elif t.tag == "v3":
                                f[2] = int(t.text)
                        indices.append(f)

                    mesh = trimesh.base.Trimesh(vertices = numpy.array(asc_mesh_vertices, dtype = numpy.float32), faces = numpy.array(indices, dtype = numpy.int32))
                    mesh.merge_vertices()
                    mesh.remove_unreferenced_vertices()
                    mesh.fix_normals()
                    mesh_data = self._toMeshData(mesh, file_name)

                    new_node = CuraSceneNode()
                    new_node.setSelectable(True)
                    new_node.setMeshData(mesh_data)
                    new_node.setName(base_name if len(nodes) == 0 else "%s %d" % (base_name, len(nodes)))
                    new_node.addDecorator(BuildPlateDecorator(CuraApplication.getInstance().getMultiBuildPlateModel().activeBuildPlate))
                    new_node.addDecorator(SliceableObjectDecorator())

                    nodes.append(new_node)

        if not nodes:
            Logger.log("e", "No meshes in file %s" % base_name)
            return None

        if len(nodes) == 1:
            return nodes[0]

        # Add all scenenodes to a group so they stay together
        group_node = CuraSceneNode()
        group_node.addDecorator(GroupDecorator())
        group_node.addDecorator(ConvexHullDecorator())
        group_node.addDecorator(BuildPlateDecorator(CuraApplication.getInstance().getMultiBuildPlateModel().activeBuildPlate))

        for node in nodes:
            node.setParent(group_node)

        return group_node

    def _toMeshData(self, tri_node: trimesh.base.Trimesh, file_name: str = "") -> MeshData:
        """Converts a Trimesh to Uranium's MeshData.

        :param tri_node: A Trimesh containing the contents of a file that was just read.
        :param file_name: The full original filename used to watch for changes
        :return: Mesh data from the Trimesh in a way that Uranium can understand it.
        """
        tri_faces = tri_node.faces
        tri_vertices = tri_node.vertices

        indices_list = []
        vertices_list = []

        index_count = 0
        face_count = 0
        for tri_face in tri_faces:
            face = []
            for tri_index in tri_face:
                vertices_list.append(tri_vertices[tri_index])
                face.append(index_count)
                index_count += 1
            indices_list.append(face)
            face_count += 1

        vertices = numpy.asarray(vertices_list, dtype = numpy.float32)
        indices = numpy.asarray(indices_list, dtype = numpy.int32)
        normals = calculateNormalsFromIndexedVertices(vertices, indices, face_count)

        mesh_data = MeshData(vertices = vertices, indices = indices, normals = normals,file_name = file_name)
        return mesh_data
