"""Unit tests for the package."""

# use agg backend so you don't need a display on travis-ci
# do this first before pyplot is imported by anything
import matplotlib as mpl

mpl.use("Agg")

import bz2
import json
import logging as lg
import os
import shutil
import tempfile
from collections import OrderedDict

import folium
import networkx as nx
import numpy as np
import pandas as pd
import pytest
from shapely import wkt
from shapely.geometry import LineString
from shapely.geometry import MultiLineString
from shapely.geometry import MultiPoint
from shapely.geometry import MultiPolygon
from shapely.geometry import Point
from shapely.geometry import Polygon

import osmnx as ox


# remove the .temp folder and .coverage file if they already
# exist so we start fresh with these tests
if os.path.exists(".temp"):
    shutil.rmtree(".temp")
if os.path.exists(".coverage"):
    os.remove(".coverage")

ox.config(
    log_console=True,
    log_file=True,
    use_cache=True,
    data_folder=".temp/data",
    logs_folder=".temp/logs",
    imgs_folder=".temp/imgs",
    cache_folder=".temp/cache",
)


# define queries to use throughout tests
location_point = (37.791427, -122.410018)
address = "600 Montgomery St, San Francisco, California, USA"
place1 = "Piedmont, California, USA"
place2 = {"neighborhood": "Financial District", "city": "Los Angeles", "state": "California"}
p = (
    "POLYGON ((-122.262 37.869, -122.255 37.869, -122.255 37.874,"
    "-122.262 37.874, -122.262 37.869))"
)
polygon = wkt.loads(p)


def test_logging():
    # test OSMnx's logger
    ox.log("test a fake debug", level=lg.DEBUG)
    ox.log("test a fake info", level=lg.INFO)
    ox.log("test a fake warning", level=lg.WARNING)
    ox.log("test a fake error", level=lg.ERROR)

    ox.citation()
    ox.ts(style="date")
    ox.ts(style="time")


def test_geometry_coords_rounding():
    # test the rounding of geometry coordinates
    precision = 3

    shape1 = Point(1.123456, 2.123456)
    shape2 = ox.utils_geo.round_geometry_coords(shape1, precision)

    shape1 = MultiPoint([(1.123456, 2.123456), (3.123456, 4.123456)])
    shape2 = ox.utils_geo.round_geometry_coords(shape1, precision)

    shape1 = LineString([(1.123456, 2.123456), (3.123456, 4.123456)])
    shape2 = ox.utils_geo.round_geometry_coords(shape1, precision)

    shape1 = MultiLineString(
        [
            [(1.123456, 2.123456), (3.123456, 4.123456)],
            [(11.123456, 12.123456), (13.123456, 14.123456)],
        ]
    )
    shape2 = ox.utils_geo.round_geometry_coords(shape1, precision)

    shape1 = Polygon([(1.123456, 2.123456), (3.123456, 4.123456), (6.123456, 5.123456)])
    shape2 = ox.utils_geo.round_geometry_coords(shape1, precision)

    shape1 = MultiPolygon(
        [
            Polygon([(1.123456, 2.123456), (3.123456, 4.123456), (6.123456, 5.123456)]),
            Polygon([(16.123456, 15.123456), (13.123456, 14.123456), (12.123456, 11.123456)]),
        ]
    )
    shape2 = ox.utils_geo.round_geometry_coords(shape1, precision)


def test_geocode_to_gdf():
    # test loading spatial boundaries and plotting
    city = ox.geocode_to_gdf(place1, which_result=1, buffer_dist=100)
    city_projected = ox.project_gdf(city, to_crs="epsg:3395")


def test_graph_from_xml():
    # test loading a graph from a local .osm xml file
    node_id = 53098262
    neighbor_ids = 53092170, 53060438, 53027353, 667744075

    with bz2.BZ2File("tests/input_data/West-Oakland.osm.bz2") as input:
        handle, temp_filename = tempfile.mkstemp(suffix=".osm")
        os.write(handle, input.read())
        os.close(handle)

    for filename in ("tests/input_data/West-Oakland.osm.bz2", temp_filename):
        G = ox.graph_from_xml(filename)
        assert node_id in G.nodes

        for neighbor_id in neighbor_ids:
            edge_key = (node_id, neighbor_id, 0)
            assert neighbor_id in G.nodes
            assert edge_key in G.edges
            assert G.edges[edge_key]["name"] in ("8th Street", "Willow Street")

    os.remove(temp_filename)


def test_routing():

    G = ox.graph_from_address(address=address, dist=500, dist_type="bbox", network_type="bike")

    # give each node a random elevation then calculate edge grades
    randm = np.random.random(size=len(G))
    elevs = {n: e for n, e in zip(G.nodes(), randm)}
    nx.set_node_attributes(G, name="elevation", values=elevs)
    G = ox.add_edge_grades(G, add_absolute=True)

    # give each edge speed and travel time attributes
    G = ox.add_edge_speeds(G)
    G = ox.add_edge_travel_times(G)

    orig_node = list(G.nodes())[5]
    dest_node = list(G.nodes())[-5]
    orig_pt = (G.nodes[orig_node]["y"], G.nodes[orig_node]["x"])
    dest_pt = (G.nodes[dest_node]["y"], G.nodes[dest_node]["x"])
    route = ox.shortest_path(G, orig_node, dest_node, weight="travel_time")

    attributes = ox.utils_graph.get_route_edge_attributes(G, route, "travel_time")

    fig, ax = ox.plot_graph_route(G, route, save=True)

    fig, ax = ox.plot_graph_route(G, route, save=True)

    # test multiple routes
    routes = ox.k_shortest_paths(G, orig_node, dest_node, k=2, weight="travel_time")
    fig, ax = ox.plot_graph_routes(G, list(routes))

    # test folium
    gm = ox.plot_graph_folium(G, popup_attribute="name")
    rm = ox.plot_route_folium(G, route)

    # test calling folium plotters with FeatureGroup instead of Map, and extra kwargs
    fg = folium.FeatureGroup(name="legend name", show=True)
    gm = ox.plot_graph_folium(G, graph_map=fg)
    assert isinstance(gm, folium.FeatureGroup)

    rm = ox.plot_route_folium(G, route, route_color="g", route_map=fg, tooltip="x")
    assert isinstance(rm, folium.FeatureGroup)


def test_plots():
    G = ox.graph_from_point(location_point, dist=500, network_type="drive")

    # test getting colors
    co = ox.plot.get_colors(n=5, return_hex=True)
    nc = ox.plot.get_node_colors_by_attr(G, "osmid")
    ec = ox.plot.get_edge_colors_by_attr(G, "length", num_bins=5)

    # plot and save to disk
    filepath = os.path.join(ox.settings.data_folder, "test.svg")
    fig, ax = ox.plot_graph(G, show=False, save=True, close=True, filepath=filepath)
    fig, ax = ox.plot_graph(
        G,
        figsize=(5, 5),
        bgcolor="y",
        dpi=180,
        node_color="k",
        node_size=5,
        node_alpha=0.1,
        node_edgecolor="b",
        node_zorder=5,
        edge_color="r",
        edge_linewidth=2,
        edge_alpha=0.1,
        show=False,
        save=True,
        close=True,
    )

    # figure-ground plots
    fig, ax = ox.plot_figure_ground(G=G)
    fig, ax = ox.plot_figure_ground(point=location_point, dist=500, network_type="drive")
    fig, ax = ox.plot_figure_ground(address=address, dist=500, network_type="bike")


def test_find_nearest():

    # get graph
    G = ox.graph_from_point(location_point, dist=500, network_type="drive")

    # convert graph to node/edge GeoDataFrames and back again
    gdf_nodes, gdf_edges = ox.graph_to_gdfs(
        G, nodes=True, edges=True, node_geometry=True, fill_edge_geometry=True
    )
    assert len(gdf_nodes) == len(G)
    assert len(gdf_edges) == len(G.edges(keys=True))
    G = ox.graph_from_gdfs(gdf_nodes, gdf_edges)
    assert len(gdf_nodes) == len(G)
    assert len(gdf_edges) == len(G.edges(keys=True))

    # get nearest node
    nn, d = ox.get_nearest_node(G, location_point, method="euclidean", return_dist=True)

    # get nearest nodes: haversine, kdtree, balltree
    X = gdf_nodes["x"].head()
    Y = gdf_nodes["y"].head()
    nn1 = ox.get_nearest_nodes(G, X, Y)
    nn2 = ox.get_nearest_nodes(G, X, Y, method="kdtree")
    nn3 = ox.get_nearest_nodes(G, X, Y, method="balltree")

    # get nearest edge
    u, v, k, g, d = ox.get_nearest_edge(G, location_point, return_geom=True, return_dist=True)

    # get nearest edges: haversine, kdtree, balltree
    ne1 = ox.get_nearest_edges(G, X, Y)
    ne2 = ox.get_nearest_edges(G, X, Y, method="kdtree")
    ne3 = ox.get_nearest_edges(G, X, Y, method="balltree", dist=0.0001)


def test_pois():

    tags = {"amenity": True, "landuse": ["retail", "commercial"], "highway": "bus_stop"}
    gdf = ox.pois_from_place(place1, tags=tags)
    gdf = ox.pois_from_address(address, tags={"amenity": "school"})


def test_api_endpoints():

    params = OrderedDict()
    params["format"] = "json"
    params["address_details"] = 0

    # Bad Address - should return an empty response
    params["q"] = "AAAAAAAAAAA"
    response_json = ox.downloader.nominatim_request(params=params, request_type="search")

    # Good Address - should return a valid response with a valid osm_id
    params["q"] = "Newcastle A186 Westgate Rd"
    response_json = ox.downloader.nominatim_request(params=params, request_type="search")

    # Lookup
    params = OrderedDict()
    params["format"] = "json"
    params["address_details"] = 0
    params["osm_ids"] = "W68876073"

    response_json = ox.downloader.nominatim_request(params=params, request_type="lookup")

    # Invalid nominatim query type
    with pytest.raises(ValueError):
        response_json = ox.downloader.nominatim_request(params=params, request_type="xyz")

    default_key = ox.settings.nominatim_key
    default_nominatim_endpoint = ox.settings.nominatim_endpoint
    default_overpass_endpoint = ox.settings.overpass_endpoint

    # Searching on public nominatim should work even if a key was provided
    ox.settings.nominatim_key = "NOT_A_KEY"
    response_json = ox.downloader.nominatim_request(params=params, request_type="search")

    # Test changing the endpoint.
    # It should fail because we didn't provide a valid key
    ox.settings.nominatim_endpoint = "http://open.mapquestapi.com/nominatim/v1/"
    with pytest.raises(Exception):
        response_json = ox.downloader.nominatim_request(params=params, request_type="search")

    # Test changing the endpoint.
    # This should fail because we didn't provide a valid endpoint
    ox.settings.overpass_endpoint = "http://NOT_A_VALID_ENDPOINT/api/"
    with pytest.raises(Exception):
        G = ox.graph_from_place(place1, network_type="drive")

    ox.settings.nominatim_key = default_key
    ox.settings.nominatim_endpoint = default_nominatim_endpoint
    ox.settings.overpass_endpoint = default_overpass_endpoint


def test_network_saving_loading():

    # save graph as shapefile and geopackage
    G = ox.graph_from_place(place1, network_type="drive")
    ox.save_graph_shapefile(G)
    ox.save_graph_geopackage(G)

    # save/load graph as graphml file
    ox.save_graphml(G, gephi=True)
    ox.save_graphml(G, gephi=False)
    filepath = os.path.join(ox.settings.data_folder, "graph.graphml")
    G = ox.load_graphml(filepath, node_type=str)

    # test osm xml output
    default_all_oneway = ox.settings.all_oneway
    ox.settings.all_oneway = True
    G = ox.graph_from_point(location_point, dist=500, network_type="drive")
    ox.save_graph_xml(G, merge_edges=False)

    # test osm xml output merge edges
    ox.save_graph_xml(G, merge_edges=True, edge_tag_aggs=[("length", "sum")])

    # test osm xml output from gdfs
    nodes, edges = ox.graph_to_gdfs(G)
    ox.save_graph_xml([nodes, edges])

    # test ordered nodes from way
    df = pd.DataFrame({"u": [54, 2, 5, 3, 10, 19, 20], "v": [76, 3, 8, 10, 5, 20, 15]})
    ordered_nodes = ox.io._get_unique_nodes_ordered_from_way(df)
    assert ordered_nodes == [2, 3, 10, 5, 8]

    ox.settings.all_oneway = default_all_oneway


def test_get_network_methods():

    # graph from bounding box
    _ = ox.utils_geo.bbox_from_point(location_point, project_utm=True, return_crs=True)
    north, south, east, west = ox.utils_geo.bbox_from_point(location_point, dist=500)
    G = ox.graph_from_bbox(north, south, east, west, network_type="drive")
    G = ox.graph_from_bbox(
        north, south, east, west, network_type="drive_service", truncate_by_edge=True
    )

    # truncate graph by bounding box
    north, south, east, west = ox.utils_geo.bbox_from_point(location_point, dist=400)
    G = ox.truncate.truncate_graph_bbox(G, north, south, east, west)

    # graph from address
    G = ox.graph_from_address(address=address, dist=500, dist_type="bbox", network_type="bike")

    # graph from list of places
    G = ox.graph_from_place([place1], network_type="drive", clean_periphery=False)

    # graph from polygon
    G = ox.graph_from_polygon(polygon, network_type="walk", truncate_by_edge=True)

    # test custom query filter
    cf = (
        '["highway"]'
        '["area"!~"yes"]'
        '["highway"!~"motor|proposed|construction|abandoned|platform|raceway"]'
        '["foot"!~"no"]'
        '["service"!~"private"]'
        '["access"!~"private"]'
    )
    G = ox.graph_from_point(
        location_point, dist=500, custom_filter=cf, dist_type="bbox", network_type="all"
    )

    G = ox.graph_from_point(
        location_point, dist=500, dist_type="network", network_type="all_private",
    )


def test_stats():
    # create graph, add bearings, project it
    G = ox.graph_from_point(location_point, dist=500, network_type="drive")
    G = ox.add_edge_bearings(G)
    G_proj = ox.project_graph(G)

    # calculate stats
    stats = ox.basic_stats(G)
    stats = ox.basic_stats(G, area=1000)
    stats = ox.basic_stats(
        G_proj, area=1000, clean_intersects=True, tolerance=15, circuity_dist="euclidean"
    )

    # calculate extended stats
    stats = ox.extended_stats(G, connectivity=True, anc=False, ecc=True, bc=True, cc=True)

    # test cleaning and rebuilding graph
    G_clean = ox.consolidate_intersections(G_proj, tolerance=10, rebuild_graph=True, dead_ends=True)


def test_footprints():

    # download footprints and plot them
    ox.settings.overpass_settings = '[out:json][timeout:200][date:"2019-10-28T19:20:00Z"]'
    gdf = ox.footprints_from_place(place2)
    gdf = ox.footprints_from_polygon(polygon)
    gdf = ox.footprints_from_address(address, dist=300)
    fig, ax = ox.plot_footprints(gdf)

    # new_river_head.json contains a relation with 1 outer closed way and 2
    # inner closed ways inner way 665593284 is directly tagged as a building
    # and should create its own polygon
    with open("tests/input_data/new_river_head.json", "r") as read_file:
        new_river_head_responses = [json.load(read_file)]
    new_river_head_gdf = ox.footprints._create_footprints_gdf(responses=new_river_head_responses)
    assert 665593284 in new_river_head_gdf.index
    assert new_river_head_gdf.loc[9246394]["geometry"].type == "Polygon"
    assert len(new_river_head_gdf.loc[9246394, "geometry"].interiors) == 2

    # clapham_common.json contains a relation with 5 outer rings and 1
    # inner ring. One of the outer rings is a chain of open ways
    with open("tests/input_data/clapham_common.json", "r") as read_file:
        clapham_common_responses = [json.load(read_file)]
    clapham_common_gdf = ox.footprints._create_footprints_gdf(
        footprint_type="leisure", responses=clapham_common_responses
    )
    assert clapham_common_gdf.loc[1290065]["geometry"].type == "MultiPolygon"

    # relation_no_outer.json contains a relation with 0 outer rings and 1
    # inner ring
    with open("tests/input_data/relation_no_outer.json", "r") as read_file:
        relation_no_outer_responses = [json.load(read_file)]
    ox.footprints._create_footprints_gdf(responses=relation_no_outer_responses)

    # inner_chain.json contains a relation with 1 outer rings and several
    # inner rings one of which is a chain of open ways
    with open("tests/input_data/inner_chain.json", "r") as read_file:
        inner_chain_responses = [json.load(read_file)]
    ox.footprints._create_footprints_gdf(responses=inner_chain_responses)

    # mis_tagged_bus_route.json contains a relation with out 'inner' or
    # 'inner' rings
    with open("tests/input_data/mis_tagged_bus_route.json", "r") as read_file:
        mis_tagged_bus_route_responses = [json.load(read_file)]
    ox.footprints._create_footprints_gdf(responses=mis_tagged_bus_route_responses)

    # test plotting multipolygon
    fig, ax = ox.plot_footprints(clapham_common_gdf)

    # should raise an exception: polygon or responses must be provided
    with pytest.raises(ValueError):
        ox.footprints._create_footprints_gdf(polygon=None, responses=None)


def test_geometries():

    # gdf_from_bbox - bounding box query that should return an empty GeoDataFrame
    gdf = ox.gdf_from_bbox(50.5912, 50.5786, -2.4293, -2.4544, tags={"building": True})

    # gdf_from_bbox - succesful
    north, south, east, west = ox.utils_geo.bbox_from_point(location_point, dist=500)
    gdf = ox.gdf_from_bbox(
        north, south, east, west, tags={"landuse": True, "building": True, "highway": True}
    )

    # gdf_from_point - tests multipolygon creation
    gdf = ox.gdf_from_point((48.15, 10.02), tags={"landuse": True}, dist=2000)

    # gdf_from_address
    gdf = ox.gdf_from_address(address, tags={"amenity": "school"})

    # gdf_from_place - includes test of list of places
    tags = {
        "amenity": True,
        "landuse": ["retail", "commercial"],
        "highway": "primary",
        "power": "substation",
    }
    gdf = ox.gdf_from_place([place1], tags=tags)

    # gdf_from_xml - tests error handling of clipped XMLs with incomplete geometry
    gdf = ox.gdf_from_xml("tests/input_data/planet_10.068,48.135_10.071,48.137.osm")


def test_gdf_from_xml():
    # test loading a geodataframe from a local .osm xml file

    with bz2.BZ2File("tests/input_data/West-Oakland.osm.bz2") as input:
        handle, temp_filename = tempfile.mkstemp(suffix=".osm")
        os.write(handle, input.read())
        os.close(handle)

    for filename in ("tests/input_data/West-Oakland.osm.bz2", temp_filename):
        GDF = ox.gdf_from_xml(filename)
        assert "Willow Street" in GDF["name"].values

    os.remove(temp_filename)
