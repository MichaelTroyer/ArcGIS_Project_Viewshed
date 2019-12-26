# -*- coding: utf-8 -*-

import os
import traceback
import arcpy



def deleteInMemory():
    """
    Delete in memory tables and feature classes
    reset to original worksapce when done
    """

    # get the original workspace
    orig_workspace = arcpy.env.workspace

    # Set the workspace to in_memory
    arcpy.env.workspace = "in_memory"
    # Delete all in memory feature classes
    for fc in arcpy.ListFeatureClasses():
        try:
            arcpy.Delete_management(fc)
        except: pass
    # Delete all in memory tables
    for tbl in arcpy.ListTables():
        try:
            arcpy.Delete_management(tbl)
        except: pass
    # Reset the workspace
    arcpy.env.workspace = orig_workspace


class Toolbox(object):

    def __init__(self):
        self.label = "Project Viewshed"
        self.alias = "Project_Viewshed"

        # List of tool classes associated with this toolbox
        self.tools = [ProjectViewshed]



class ProjectViewshed(object):

    def __init__(self):
        self.label = "Project_Viewshed"
        self.description = "Compute the visible areas within a given distance from a project.."
        self.canRunInBackground = True

    def getParameterInfo(self):
        """
        Define parameter definitions
        """

        # Input Feature
        inFeatures=arcpy.Parameter(
            displayName="Input Project Feature(s)",
            name="Input_Feature",
            datatype="DEFeatureClass",
            parameterType="Required",
            direction="Input",
            )
        # Output Name
        outputName=arcpy.Parameter(
            displayName="Output Name",
            name="Output_Name",
            datatype="String",
            parameterType="Required",
            direction="Input",
            )
        # Output Location
        workspace=arcpy.Parameter(
            displayName="Output Workspace",
            name="Workspace",
            datatype="DEWorkspace",
            parameterType="Required",
            direction="Input",
            )
        # Analysis Distance
        distance=arcpy.Parameter(
            displayName="Maximum Analysis Distance (Miles)",
            name="Analysis_Distance_miles",
            datatype="Double",
            parameterType="Required",
            direction="Input",
            )
        # Analysis Distance
        nBndPoints=arcpy.Parameter(
            displayName="Number of Project Boundary Observer Points",
            name="N_Boundary_Points",
            datatype="Long",
            parameterType="Optional",
            direction="Input",
            enabled=False,
            )
        # Analysis Distance
        nIntPoints=arcpy.Parameter(
            displayName="Number of Project Interior Observer Points",
            name="N_Interior_Points",
            datatype="Long",
            parameterType="Optional",
            direction="Input",
            enabled=False,
            )
        keepData=arcpy.Parameter(
            displayName="Keep Interim Data",
            name="Keep_Data",
            datatype="Boolean",
            parameterType="Optional",
            direction="Input",
            )

        return [inFeatures, outputName, workspace, distance, nBndPoints, nIntPoints, keepData]

    def isLicensed(self):
        return True

    def updateParameters(self, parameters):
        """
        Modify the values and properties of parameters before internal
        validation is performed.  This method is called whenever a parameter
        has been changed.
        """
        inFeatures, outputName, workspace, distance, nBndPoints, nIntPoints, keepData = parameters

        desc = arcpy.Describe(inFeatures)

        # Polygons can have boundary or interior points
        # Lines can have boundary points
        # Points can have neither
        if desc.shapeType == 'Polyline':
            nBndPoints.enabled = True
            nIntPoints.value = None; nIntPoints.enabled = False
        elif desc.shapeType == 'Polygon':
            nBndPoints.enabled = True
            nIntPoints.enabled = True
        else:
            nBndPoints.value = None; nBndPoints.enabled = False
            nIntPoints.value = None; nIntPoints.enabled = False

        # Default to 1 mile
        if not distance.altered:
            distance.value = 1.0

        return

    def updateMessages(self, parameters):
        """
        Modify the messages created by internal validation for each tool
        parameter.  This method is called after internal validation.
        """
        inFeatures, outputName, workspace, distance, nBndPoints, nIntPoints, keepData = parameters
                
        if workspace.value:
            if not workspace.valueAsText.strip().endswith('gdb'):
                workspace.setErrorMessage('Output workspace must be a geodatabase..')
        return

    def execute(self, parameters, messages):
        """
        Main program.
        """
        deleteInMemory()

        inFeatures, outputName, workspace, distance, nBndPoints, nIntPoints, keepData = parameters

        inFeatures = inFeatures.value
        outputName = outputName.valueAsText.replace(' ', '_')
        workspace = workspace.valueAsText
        distance = distance.value
        nBndPoints = nBndPoints.value
        nIntPoints = nIntPoints.value
        keepData = keepData.value
    
        arcpy.AddMessage('\n[+] Creating Project Viewshed..')
        arcpy.AddMessage('[+] Input Features: [{}]'.format(inFeatures))
        arcpy.AddMessage('[+] Output Name: [{}]'.format(outputName))
        arcpy.AddMessage('[+] Output Workspace: [{}]'.format(workspace))
        arcpy.AddMessage('[+] Analysis Distance: [{} Miles]'.format(distance))
        arcpy.AddMessage('[+] Interior Observer Points: [{}]'.format(nBndPoints))
        arcpy.AddMessage('[+] Boundary Observer Points: [{}]'.format(nIntPoints))
        if not nIntPoints and not nBndPoints:
            arcpy.AddMessage(
                '[+] No boundary or interior points - defaulting to feature vertices..'
                )
        arcpy.AddMessage('[+] Keeping Interim Data' if keepData else '')      
        arcpy.AddMessage('\n')

        #NOTE: Update viewshed z-factor if choosing a different DEM
        dem = r'\\blm\dfs\loc\EGIS\ReferenceState\CO\CorporateData\topography\dem\Elevation 10 Meter.lyr'

        try:
            # Manage workspaces
            orig_workspace = arcpy.env.workspace
            # Scratch holds interim data - set to output workspace to keep interim data
            # Program will clean up 'in_memory' on close
            scratch = workspace if keepData else 'in_memory'
            arcpy.env.workspace = scratch

            # Buffer input features
            buffer = os.path.join(scratch, '{}_Buffer'.format(outputName))
            arcpy.Buffer_analysis(
                in_features=inFeatures,
                out_feature_class=buffer,
                buffer_distance_or_field='{} Mile'.format(distance),
                )
            arcpy.AddMessage('Buffered input..')

            # Clip DEM by buffer
            dem_clip = os.path.join(scratch, '{}_DEM'.format(outputName))
            arcpy.Clip_management(
                in_raster=dem,
                out_raster=dem_clip,
                in_template_dataset=buffer,
                clipping_geometry="ClippingGeometry",
                )
            arcpy.AddMessage('Clipped DEM..')

            # Render observer points
            shapeType = arcpy.Describe(inFeatures).shapeType
            points = []

            if shapeType == 'Polygon':
                # Polygons can have boundary and/or interior points
                if nIntPoints:
                    pts = arcpy.CreateRandomPoints_management(
                        out_path=scratch,
                        out_name='{}_Observer_Points_interior'.format(outputName),
                        constraining_feature_class=inFeatures,
                        number_of_points_or_field=nIntPoints,
                        )
                    points.append(pts)
                if nBndPoints:
                    # Convert polygon to line boundary and scatter points along line feature
                    bnd = arcpy.FeatureToLine_management(inFeatures, r'in_memory/bnd')
                    pts = arcpy.CreateRandomPoints_management(
                        out_path=scratch,
                        out_name='{}_Observer_Points_boundary'.format(outputName),
                        constraining_feature_class=bnd,
                        number_of_points_or_field=nBndPoints,
                        )
                    points.append(pts)
            elif shapeType == 'Polyline':
                # Lines can have boundary points only
                if nBndPoints:
                    pts = arcpy.CreateRandomPoints_management(
                        out_path='in_memory',  # These will always be identical to Observer_Points_All - toss
                        out_name='{}_Observer_Points_boundary'.format(outputName),
                        constraining_feature_class=inFeatures,
                        number_of_points_or_field=nBndPoints,
                        )
                    points.append(pts)

            vs_points = os.path.join(workspace, '{}_Observer_Points'.format(outputName))
            if len(points) == 2:
                # User selected boundary and interior points
                arcpy.Merge_management(points, vs_points)
            elif len(points) == 1:
                # User selected one or the other
                arcpy.CopyFeatures_management(points[0], vs_points)
            else:
                # User selected none (or input is point), use feature vertices (or source points)
                arcpy.FeatureVerticesToPoints_management(
                    in_features=inFeatures,
                    out_feature_class=vs_points,
                    point_location="ALL",
                    )
            arcpy.AddMessage('Created observer points..')

            # Viewshed - raw viewshed encodes counts - binarzie and delete raw viewshed
            viewshed = os.path.join('in_memory', '{}_Viewshed_raw'.format(outputName))
            arcpy.Viewshed_3d(
                in_raster=dem_clip,
                in_observer_features=vs_points,
                out_raster=viewshed,
                z_factor="0.3048",  #NOTE: This needs to be updated if a different DEM is selected
                )
            arcpy.AddMessage('Calculated viewshed..')

            # Extract visible areas ( value >= 1 )
            visible = os.path.join(workspace, '{}_Viewshed'.format(outputName))
            arcpy.gp.GreaterThanEqual_sa(viewshed, 1, visible)

            # Convert to polygons
            polygons = os.path.join(workspace, '{}_Viewshed_Polygons'.format(outputName))
            arcpy.RasterToPolygon_conversion(
                in_raster=visible,
                out_polygon_features=polygons,
                simplify="SIMPLIFY",
                raster_field="Value"
                )

            arcpy.AddField_management(polygons, "VISIBILITY", "TEXT", field_length=15)
            codeblock = """def visible(gridcode):\n    return "Visible" if gridcode == 1 else "Not Visible" """
            arcpy.CalculateField_management(polygons, "VISIBILITY", "visible(!gridcode!)", "PYTHON_9.3", codeblock)

            arcpy.AddMessage('Created viewshed polygons..\n')

        except Exception as e:
            err = str(traceback.format_exc())
            arcpy.AddError(err)
            raise e

        finally:
            deleteInMemory()
            # Reset the workspace
            arcpy.env.workspace = orig_workspace

        return
