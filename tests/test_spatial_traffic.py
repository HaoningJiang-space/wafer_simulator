"""Payload padding, nonuniform flit paths and directed cut accounting."""
import unittest
from wafer_sim.analysis.spatial_traffic import project


def fixture():
    links=[dict(src=a,dst=b,bandwidth=32,bidirectional=True) for a,b in ((0,1),(0,2),(2,1))]
    exported=dict(endpoints=[dict(node=i,router=i) for i in range(3)],inputs=dict(links=links,
        placement=dict(chiplets=[dict(name="c",rotation=0,position=dict(x=x,y=0)) for x in (-2,1,-2)]),
        chiplets=dict(c=dict(dimensions=dict(x=1,y=1)))))
    flits=[]
    for i,path in enumerate(((0,1),(0,2,1))):
        flits.append(dict(id=i,message=0,source=0,destination=1,generated=0,injected=i,
            injection_router_arrival=i+2,ejected=i+10,hops=len(path),router_path=path,
            link_arrivals=[dict(source=a,destination=b,cycle=i+4+j) for j,(a,b) in enumerate(zip(path,path[1:]))]))
    message=dict(id=0,token="m",source=0,destination=1,bytes=5,flit_bytes=4,expected_flits=2,
        ready=0,generated=0,first_inject=0,last_inject=1,first_eject=10,last_eject=11,finish=12,flits=flits)
    return exported,[message]


class SpatialTrafficTests(unittest.TestCase):
    def test_wow_positions_are_centers_not_bottom_left_corners(self):
        export,messages=fixture()
        export["inputs"]["placement"]["chiplets"][0]["position"]["x"]=-0.25
        result=project(export,messages,[0,1])
        self.assertEqual(result["cut"]["router_x"][0],-0.25)
        self.assertEqual(result["cut"]["directions"]["left_to_right"]["payload_bytes"],5)

    def test_short_last_flit_and_divergent_paths_are_not_full_message_copies(self):
        export,messages=fixture();result=project(export,messages,[0,1])
        self.assertEqual(result["total_payload_bytes"],5);self.assertEqual(result["total_wire_bytes"],8)
        self.assertEqual(result["payload_byte_hops"],6);self.assertEqual(result["wire_byte_hops"],12)
        self.assertEqual(result["max_directed_link_payload_bytes"],4)
        cut=result["cut"]["directions"]
        self.assertEqual(cut["left_to_right"]["payload_bytes"],5)
        self.assertEqual(cut["left_to_right"]["wire_bytes"],8)
        self.assertEqual(cut["left_to_right"]["capacity_bytes_per_cycle"],8)
        self.assertEqual(cut["right_to_left"]["payload_bytes"],0)
        self.assertEqual(result["cut"]["wire_service_lower_bound_cycles"],1)

    def test_each_cut_traversal_is_counted_including_return_crossing(self):
        export,messages=fixture()
        export["inputs"]["placement"]["chiplets"][1]["position"]["x"]=-2
        export["inputs"]["placement"]["chiplets"][2]["position"]["x"]=1
        result=project(export,messages,[0,1])
        self.assertEqual(result["cut"]["directions"]["left_to_right"]["payload_bytes"],1)
        self.assertEqual(result["cut"]["directions"]["right_to_left"]["payload_bytes"],1)

    def test_active_endpoint_denominator_includes_zero_traffic(self):
        export,messages=fixture();r=project(export,messages,[0,1,2])
        self.assertEqual(r["max_endpoint_payload_bytes"],5)
        self.assertAlmostEqual(r["endpoint_max_over_mean"],1.5)
        self.assertEqual(r["endpoint_rows"][2]["total_payload_bytes"],0)
        with self.assertRaises(ValueError):project(export,messages,[0,0,1])
