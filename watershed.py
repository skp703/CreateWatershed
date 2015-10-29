from __future__ import print_function
import os
import arcpy
import time
__author__ = 'saurav'
# Copyright:   (c) Saurav Kumar (kumar.saurav@gmail.com)
# ArcGIS Version:   10.3
# Python Version:   2.7

arcpy.env.overwriteOutput = True
sr = arcpy.SpatialReference(4326)  # decimal degree coordinate system used by most GPS systems
sr_p = arcpy.SpatialReference(3395)  # projection we used in m


def create_watershed(grid, coordinates, play_folder, stage=0, out_geo="merge.gdb", type_of_raster="GRID",
                     mosaic_name="combine", stream_accumulation_number=5000, snapping_tolerance=2):

    """create's watershed from given grid and coordinates

       grid: a folder that contains other raster folders (tiles) from http://viewer.nationalmap.gov/viewer/ that when
       combined covers all the watersheds area

       coordinate: a list of dictionaries each dictionary has stname, lat and lng keys (lat and lng in decimal degree).
       See the example at the end for format

       play_folder: an EXISTING folder for all output files, a file geodatabase is created in step 0 inside the folder.

       stage:  0 executes everything; 1 does not combine raster, everything afterwards in on; 2 does not fill,
       everything afterwards in on; 3 does not do flow direction, everything afterwards in on; 4 does not do flow
       accumulation, everything afterwards in on; 5 does not do stream creation, everything afterwards in on.
       Stage is useful in restarting program without repeating old timeconsuming steps, if something  fails.

       out_geo: name of file geodatabase where everything happen created in the play_folder

       type_of_raster: type of raster downloaded form NED ... ESRI GRID, IMG etc

       mosaic_name: what to call the combined raster

       stream_accumulation_number: is used to find streams; essentially a accumulation volume anything over the volume
       will be marked 1.. signifying stream/waterbody ... this is just for later analysis

       snapping_tolerance: is the number of raster cells the points (for which watersheds are being delineated) may be
       moved to lie on the deepest point nearby. A simple way to fix GPS uncertainties.
    """
    try:

        combined = os.path.join(play_folder,out_geo,mosaic_name)
        arcpy.env.workspace = os.path.join(play_folder, out_geo)
        # Check out the ArcGIS Spatial Analyst extension license
        arcpy.CheckOutExtension("Spatial")
        if stage < 1:
            start = time.clock()
            print("Step 0: calling combine_raster...........creating", combined)
            combine_rasters(grid, play_folder, out_geo, type_of_raster, mosaic_name)
            print("Combining took {} min".format((time.clock() - start)/60))
        else:
            print("NOT calling combine_raster........... using", combined)

        if stage < 2:
            start = time.clock()
            print("Step 1: Fill combined raster...........creating", combined+"_fill")
            out_fill = arcpy.sa.Fill(mosaic_name)
            print("Saving filled raster as ", combined+"_fill")
            out_fill.save(combined+"_fill")  # saving just it things go wrong..could have directly gone to flow
            # direction
            print("FILL took {} min".format((time.clock() - start)/60))
        else:
            print("NOT filling")

        if stage < 3:
            start = time.clock()
            print("Step 2: Building flow direction...........creating", combined+"_fd")
            out_fd = arcpy.sa.FlowDirection(combined+"_fill")
            print("Saving flow direction raster as ", combined+"_fd")
            out_fd.save(combined+"_fd")
            print("FD took {} min".format((time.clock() - start)/60))
        else:
            print("NOT computing flow direction")

        if stage < 4:
            start = time.clock()
            print("Step 3: Building flow accumulation...........creating. This takes a LOT more time.", combined+"_fa")
            out_fd = arcpy.sa.FlowAccumulation(combined+"_fd")
            print("Saving flow accumulation raster as ", combined+"_fa")
            out_fd.save(combined+"_fa")
            print("FA took {} min".format((time.clock() - start)/60))
        else:
            print("NOT computing flow accumulation")

        if stage < 5:
            start = time.clock()
            print("Step 4: Building streams...........creating", combined+"_stream")
            arcpy.gp.RasterCalculator_sa(""""combine_fa" > {}""".format(stream_accumulation_number), combined+"_stream")
            print("Stream building took {} min".format((time.clock() - start)/60))
        else:
            print("NOT building stream")

        start = time.clock()
        print("Step 5: watershed building..........")

        points = "points"  # multipoint file that will save all points for which watershed is created
        arcpy.CreateFeatureclass_management(out_path=arcpy.env.workspace, out_name=points, geometry_type="MULTIPOINT",
                                            spatial_reference=sr_p)
        arcpy.AddField_management(points, "name", "TEXT")
        cursor = arcpy.da.InsertCursor(points, ["name",  "SHAPE@"])  # will insert points here
        for coord in coordinates:
            print("Point {stname} -- lat:{lat} , lng:{lng}".format(**coord))
            pnt = arcpy.Point(coord["lng"], coord["lat"])
            pnt_geometry = arcpy.PointGeometry(pnt, sr)
            print ("snapping ...")
            tol = arcpy.Describe(combined+"_fa").children[0].meanCellHeight * snapping_tolerance  # snapping_tolerance
            # times the mean cell height of the raster
            out_ras = arcpy.sa.SnapPourPoint(pnt_geometry, combined+"_fa", tol)  # snapping_tolerance
            out_ras.save("snapped"+coord["stname"])
            # is likely in decimal degrees
            print("building shed ...")
            shed = arcpy.sa.Watershed(combined+"_fd", out_ras)
            print("saving as polygon ...")
            #shed.save(os.path.join(play_folder,out_geo,shed+coord["stname"]))
            arcpy.RasterToPolygon_conversion(shed, "shed"+coord["stname"])

            cursor.insertRow([coord["stname"], arcpy.Geometry("multipoint", pnt, sr)])  # add point to the multipoint
            # shape

        del cursor
        print("Watershed building took {} min".format((time.clock() - start)/60))
        pass
    except arcpy.ExecuteError:
        print(arcpy.GetMessages(2))
    except Exception as e:
        print(e.args[0])
# End function


def combine_rasters(grid, play_folder, out_geo, type_of_raster, mosaic_name):

    """ combines rasters it the folder grid

        The grid folder is assumed to have other folders that have the raster(s) in them that should be joined
    """
    old_wkspace = arcpy.env.workspace
    rasters_to_add = []
    for (dirpath, dirnames, filenames) in os.walk(grid):  # loop through folder
        for subdirname in dirnames:  # only concerned with directory that might have raster
            curdir = os.path.join(dirpath, subdirname)
            #print("looking in ", curdir)
            arcpy.env.workspace = curdir  # Set the current workspace
            for raster in arcpy.ListRasters("*", type_of_raster):  # Get and print a list of rasters from the workspace
                print("Adding ---",raster)
                rasters_to_add.append(os.path.join(curdir, raster))

    if arcpy.Exists(os.path.join(play_folder, out_geo)):  # delete if the geodatabase exists
        arcpy.Delete_management(os.path.join(play_folder, out_geo))
    geodb = arcpy.CreateFileGDB_management(play_folder, out_geo)  # create geodatabase to store mosaic
    print("Creating mosaic.....")
    mos = arcpy.MosaicToNewRaster_management(rasters_to_add, geodb, mosaic_name, number_of_bands=1,
                                             pixel_type="32_BIT_FLOAT", mosaic_method="LAST",
                                             coordinate_system_for_the_raster=sr_p)
    print("Mosaic created.....", mos)
    arcpy.env.workspace = old_wkspace  # reset workspace
    return mos

if __name__ == '__main__':  # True when script is run directly

    grid = r"C:\createWatershed\grid"  # folder that contains subfolder with data(rasters) downloded from NED
#     This is what my grid directory looks like

# * C:\createWatershed\grid
#     ** n40w079
#     ** USGS_NED_1_n39w077_ArcGrid
#     ** USGS_NED_1_n39w078_ArcGrid
#     ** USGS_NED_1_n39w079_ArcGrid
#     ** USGS_NED_1_n40w077_ArcGrid
#     ** USGS_NED_1_n40w078_ArcGrid
#     * C:\createWatershed\grid\n40w079
#         - grdn40w079_1_thumb.jpg
#         - my-directory-list.txt
#         - n40w079_1_meta.dbf
#         - n40w079_1_meta.html
#         - n40w079_1_meta.prj
#         - n40w079_1_meta.sbn
#         - n40w079_1_meta.sbx
#         - n40w079_1_meta.shp
#         - n40w079_1_meta.shp.xml
#         - n40w079_1_meta.shx
#         - n40w079_1_meta.txt
#         - n40w079_1_meta.xml
#         - ned_1arcsec_g.dbf
#         - ned_1arcsec_g.prj
#         - ned_1arcsec_g.sbn
#         - ned_1arcsec_g.sbx
#         - ned_1arcsec_g.shp
#         - ned_1arcsec_g.shx
#         - NED_DataDictionary.url
#         - readme.pdf
#         ** grdn40w079_1
#         ** info
# #   ..... and other raster folders

    play_folder = r"C:\createWatershed"
    coordinates = [
        {"stname": "BL28", "lat": 39.0362, "lng": -77.4347},
        {"stname": "BL29", "lat": 39.03048333, "lng": -77.43745},
        {"stname": "BL30", "lat": 39.02461667, "lng": -77.43942},
        {"stname": "BL31", "lat": 39.02098333,"lng": -77.43978}
]
    create_watershed(grid, coordinates, play_folder, stage=0)
