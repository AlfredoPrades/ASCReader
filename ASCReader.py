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
        Logger.log("i","DEBUG ASCREADER")
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
        Logger.log("i","DEBUG Read start")
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
                self.header[field_name] = field_value
                Logger.log("i","Header field '%s' found with value '%s'"%(field_name,field_value))
    

        Logger.log("i","Header processed successfully")
        

        max_elevation = 0
        min_elevation = 10000000
        cellsize = int(self.header["CELLSIZE"])
        nodata = self.header["NODATA_VALUE"]
        y = 0
        asc_mesh = []
        for line in raw_file:
            x = 0
            Logger.log("i",line)
            for elev_point in line.split(' '):
                vertex = [0.0, 0.0, 0.0]
                vertex[0] = x * cellsize
                vertex[1] = y * cellsize
                if elev_point == nodata:
                    vertex[2] = 0.0  #O base elevation
                else:
                    try:
                        vertex[2] = float(elev_point)
                        if vertex[2] > max_elevation: 
                            max_elevation = vertex[2]
                        elif vertex[2] < min_elevation:
                            min_elevation = vertex[2]
                    except:
                        continue


                #Logger.log("i",str(vertex))        
                asc_mesh.append(vertex)
                x+=1
            y+=1

        raw_file.close()

        elevation_range = (max_elevation - min_elevation)  / 5.0 
        base_z = 0.0
        if min_elevation > elevation_range:
            base_z = min_elevation - elevation_range
        

        ncols = int(self.header['NCOLS'])
        nrows = int(self.header['NROWS'])
        Logger.log("i","NROWS'%s'"%nrows)



        elevation_factor = 1
        ok_cellsize = elevation_factor * cellsize
        # top
        for x in range(0,ncols):
            vertex = [x * ok_cellsize, 0.0, base_z]
            asc_mesh.append(vertex)
            #Logger.log("d","TOP vertex %s %s currenLen: %s"%(x,vertex,len(asc_mesh)))

        # right
        right_x = (ncols -1) * ok_cellsize
        for y in range(0,nrows):
            vertex = [right_x, y * ok_cellsize, base_z]
            asc_mesh.append(vertex)
            #Logger.log("d","RIGHT vertex %s %s currenLen: %s"%(y,vertex,len(asc_mesh)))
            
        # bottom    
        bottom_y = (nrows -1) * ok_cellsize
        for x in range(0,ncols):
            vertex= [x * ok_cellsize, bottom_y, base_z]
            asc_mesh.append(vertex)
            #Logger.log("d","BOTTOM vertex %s %s currenLen: %s"%(x,vertex,len(asc_mesh)))

        # left 
        for y in range(0,nrows):
            vertex= [0 , y * ok_cellsize, base_z]
            asc_mesh.append(vertex)
            #Logger.log("d","LEFT vertex %s %s currenLen: %s"%(y,vertex,len(asc_mesh)))


        
        Logger.log("i","POINTS")
        #Logger.log("i",str(asc_mesh))

        

        asc_mesh_triangles = []
        offset = ncols * nrows 
        offset_last_row = offset - ncols
        offset_bottom  = offset + ncols + nrows
        
        #Top vertex
        for j in range(1,nrows):   
            id_behind = (j -1) * ncols
            for i in range(0,ncols-1):
                my_id = id_behind + i
                #Logger.log("d","i j  vertex %s %s - myid: %s"%(i,j,my_id))
                asc_mesh_triangles.append([my_id , my_id + 1 , my_id + 1 + ncols])
                asc_mesh_triangles.append([my_id , my_id + 1 + ncols ,my_id + ncols])
        


        Logger.log("d","triangles top end")
        for i in range(0,ncols-1):
            #Logger.log("d","top bottom i vertex %s"%(i))
            #top wall
            asc_mesh_triangles.append([i, i + offset,i + 1])
            asc_mesh_triangles.append([i +1 , i + offset, i + offset + 1])

            #bottom wall    
            asc_mesh_triangles.append([i + offset_last_row + 1 , i + offset_bottom, i + offset_last_row])
            asc_mesh_triangles.append([i + offset_bottom + 1 , i + offset_bottom, i + offset_last_row + 1])

        Logger.log("i","VERTEX walls half")    
        start_right = offset + ncols 
        start_left = offset + ncols * 2 + nrows
        for j in range(0,nrows-1):
            #Logger.log("d","right left  j vertex %s"%(j))
            #right wall
            asc_mesh_triangles.append([ncols * ( j + 2 ) -1 , ncols * (j + 1) -1 , start_right + j ])
            asc_mesh_triangles.append([ncols * ( j + 2 ) -1, start_right + j , start_right + j +1 ])
            #left wall
            asc_mesh_triangles.append([start_left + j, ncols * j , ncols * (j + 1)])
            asc_mesh_triangles.append([start_left + j + 1, start_left + j , ncols * (j + 1)])

         
        # Bottom triangles
        p1 = offset 
        p2 = p1 + ncols
        p3 = p2 + nrows 
        p4 = p3 + ncols -1

        asc_mesh_triangles.append([p3,p2,p1])
        asc_mesh_triangles.append([p3,p4,p2])
        Logger.log("i","VERTEX end")
        #Logger.log("i",str(asc_mesh_triangles))
        
        mesh = trimesh.base.Trimesh(vertices = numpy.array(asc_mesh, dtype = numpy.float32), faces = numpy.array(asc_mesh_triangles, dtype = numpy.int32))
        Logger.log("i","Mesh built")
        mesh.merge_vertices()
        Logger.log("i","merge_vertices")
        mesh.remove_unreferenced_vertices()
        Logger.log("i","remove unreferenced")
        mesh.fix_normals()
        Logger.log("i","fix_normals")
        mesh_data = self._toMeshData(mesh, file_name)

        nodes=[]
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
        Logger.log("i","calculate Normals")
        normals = calculateNormalsFromIndexedVertices(vertices, indices, face_count)
        Logger.log("i","calculate Normals end")

        mesh_data = MeshData(vertices = vertices, indices = indices, normals = normals,file_name = file_name)
        return mesh_data
