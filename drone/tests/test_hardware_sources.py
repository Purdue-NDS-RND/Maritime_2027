from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import sys
from types import SimpleNamespace as NS

import pytest
import yaml

from maritime_perception.adapters.camera_settings import parse_settings
from maritime_perception.adapters.hardware_topics import load_profile, profile_assessment, recorder_arguments
from maritime_perception.adapters.hardware_source_check import SourceMonitor, run_live
from maritime_perception.adapters.rosbag_audit import audit_bag
from maritime_perception.validation import Unavailable


class Message(NS):
    def get_fields_and_field_types(self):
        return dict.fromkeys(vars(self))


def samples(profile, stamp=1_000_000_000):
    def header(frame):
        sec, ns = divmod(stamp, 10**9)
        return Message(stamp=Message(sec=sec, nanosec=ns), frame_id=frame)
    camera_frame = profile['roles']['image']['frame_id']
    meta = dict(id=f'capture_test_{stamp}', capture_session_id='capture_test',
        ros_header_stamp_ns=stamp, stamp_ns=stamp//2, clock_id='camera_pts', frame_id=camera_frame,
        image_domain='rectified', input_image_size=[2, 1], calibration_id='historical_candidate',
        stamp_semantics='gstreamer_running_time_unverified', exposure_time_verified=False, synthetic=False)
    result = {role:Message(header=header('')) for role in profile['roles']}
    result.update(image=Message(header=header(camera_frame), width=2, height=1, encoding='bgr8', step=6, data=bytes(6)),
        camera_info=Message(header=header(camera_frame), width=2, height=1, distortion_model='plumb_bob',
            d=[0.]*5,k=[1.,0.,0.,0.,1.,0.,0.,0.,1.],r=[1.,0.,0.,0.,1.,0.,0.,0.,1.],p=[0.]*12,
            binning_x=0,binning_y=0,roi=Message(x_offset=0,y_offset=0,width=0,height=0,do_rectify=False)),
        frame_metadata=Message(data=json.dumps(meta)),
        odometry=Message(header=header('map'), child_frame_id='base_link',
            pose=Message(covariance=[0.]*36),twist=Message(covariance=[0.]*36)),
        imu=Message(header=header('base_link'),orientation=Message(x=0.,y=0.,z=0.,w=1.)),
        gnss=Message(header=header('base_link'),status=Message(status=0)),
        gps_origin=Message(header=header('earth'),position=Message(latitude=40.,longitude=-86.,altitude=200.)),
        fcu_state=Message(header=header(''), connected=True),
        tf=Message(transforms=[]),tf_static=Message(transforms=[Message(child_frame_id='map_ned')]))
    return result


def test_observed_topic_bindings_recording_qos_and_command_are_consistent():
    profile=load_profile()
    assert len(profile['roles'])==13
    assert profile['roles']['odometry']['frame_id']=='map'
    assert profile['roles']['odometry']['child_frame_id']=='base_link'
    qos=yaml.safe_load(Path('drone/maritime_perception/config/rosbag_qos.yaml').read_text())
    for item in profile['roles'].values():
        assert qos[item['topic']]==dict(history='keep_last',**item['qos'])
    assert profile['roles']['gps_origin']['qos']['durability']=='transient_local'
    assert profile['roles']['imu']['qos']['reliability']=='best_effort'
    command=recorder_arguments(profile,'recordings/with spaces')
    assert command[command.index('-o')+1]=='recordings/with spaces'
    assert command[-13:]==[x['topic'] for x in profile['roles'].values()]
    assert '/drone/perception/input' not in command


def test_monitor_uses_known_frames_but_retains_unknown_geometry_and_uncertainty():
    profile=load_profile();monitor=SourceMonitor(profile)
    for role,message in samples(profile).items():monitor.observe(role,message,2_000_000_000)
    report=monitor.summary(2_100_000_000)
    assert report['topic_profile']['all_required_topics_seen']
    assert report['topic_profile']['topic_contract_matches']
    assert report['camera_recent']['exact_triplet_count']==1
    assert report['quality']['zero_pose_covariance']==1
    assert report['quality']['zero_twist_covariance']==1
    assert report['gps_origin']['header']['frame_id']=='earth'
    assert report['normalized_events_emitted']==0 and not report['geolocation_ready']
    assert not report['topic_profile']['physical_conventions_verified']
    assert not report['camera_recent']['odometry_brackets_evaluated']
    assert monitor.camera.metadata[(1_000_000_000,'arducam_optical_frame')][0]['stamp_ns']==500_000_000
    assert report['topics']['/mavros/local_position/odom']['frame_ids']==['map']


@pytest.mark.parametrize('fault',['frame','child','publisher_type','missing_imu'])
def test_source_contract_reports_mismatch_and_missing_data(fault):
    profile=load_profile();monitor=SourceMonitor(profile);messages=samples(profile)
    if fault=='frame':messages['odometry'].header.frame_id='NED'
    if fault=='child':messages['odometry'].child_frame_id='another_body'
    for role,message in messages.items():
        if fault!='missing_imu' or role!='imu':monitor.observe(role,message,2_000_000_000)
    types={profile['roles']['odometry']['topic']:['std_msgs/msg/String']} if fault=='publisher_type' else None
    report=monitor.summary(2_000_000_000,types)
    assert not report['topic_profile']['topic_contract_matches']
    reasons={i['reason'] for i in report['topic_profile']['issues']}
    assert {'frame':'source_frame_mismatch','child':'source_child_frame_mismatch',
            'publisher_type':'topic_type_mismatch','missing_imu':'required_topic_empty'}[fault] in reasons
    assert not report['geolocation_ready']


def test_live_camera_matching_is_bounded_and_records_validation_failures():
    profile=load_profile();monitor=SourceMonitor(profile,max_camera_keys=2)
    for ns in range(1,6):
        messages=samples(profile,stamp=ns)
        for role in ['frame_metadata','camera_info','image']:monitor.observe(role,messages[role],ns)
    monitor.observe('frame_metadata',Message(data='bad JSON'),7)
    report=monitor.summary(8)
    assert report['topics']['/camera/image_rect']['count']==5
    assert report['camera_recent']['exact_triplet_count']==2
    assert report['camera_recent']['invalid_metadata_count']==1
    assert report['camera_cache_evictions']==9
    assert all(len(index)<=2 for index in [monitor.camera.images,monitor.camera.infos,monitor.camera.metadata])
    assert all('data' not in value[0] for value in monitor.camera.images.values())


def test_bench_preset_preserves_cli_resolution_shutter_and_rate_choices():
    config='drone/maritime_perception/config/imx519_bench.json'
    settings,_,_=parse_settings(['--config',config,'--publish-hz','1','--output-width','640',
                                '--output-height','360','--shutter-speed','500','--dry-run'])
    assert settings.width==3840 and settings.height==2160 and settings.sensor_mode==1
    assert settings.output_size==[640,360] and settings.publish_hz==1 and settings.shutter_speed==500
    assert settings.preview_width==settings.preview_height==0
    assert settings.ros_topic_profile=='builtin:mavros_imx519'


def test_bag_export_uses_profile_bindings_instead_of_topic_name_prefixes(tmp_path):
    profile=load_profile();messages=samples(profile)
    for role in profile['roles']:
        profile['roles'][role]['topic']='/renamed/'+role
    path=tmp_path/'recording.db3'
    selected=['image','camera_info','frame_metadata','odometry']
    with sqlite3.connect(path) as connection:
        connection.execute('CREATE TABLE topics(id INTEGER PRIMARY KEY,name TEXT,type TEXT,serialization_format TEXT)')
        connection.execute('CREATE TABLE messages(id INTEGER PRIMARY KEY,topic_id INTEGER,timestamp INTEGER,data BLOB)')
        for i,role in enumerate(selected,1):
            item=profile['roles'][role]
            connection.execute('INSERT INTO topics VALUES(?,?,?,?)',(i,item['topic'],item['type'],'cdr'))
            connection.execute('INSERT INTO messages(topic_id,timestamp,data) VALUES(?,?,?)',(i,i,role.encode()))
    report=audit_bag(path,profile=profile,decoder=lambda raw,kind:messages[raw.decode()],export_directory=tmp_path/'export')
    assert report['camera']['exact_triplet_count']==1
    assert report['export']['exported_frames']==1
    navigation=json.loads((tmp_path/'export/navigation.jsonl').read_text())
    assert navigation['topic']=='/renamed/odometry'
    assert report['topic_profile']['bindings']['odometry']['count']==1


def fake_ros(monkeypatch,profile,*,fail_subscription=False):
    state=NS(now=0.,shutdown=0,destroyed=0,subscriptions=[])
    messages=samples(profile)
    by_topic={item['topic']:(role,item) for role,item in profile['roles'].items()}
    class Node:
        def __init__(self,name):assert name=='perception_hardware_source_check'
        def create_subscription(self,kind,topic,callback,qos):
            if fail_subscription:raise RuntimeError('subscription failed')
            role,item=by_topic[topic]
            assert kind==item['type'] and qos.depth==item['qos']['depth']
            state.subscriptions.append((role,callback))
            return callback
        def get_publishers_info_by_topic(self,topic):return [NS(topic_type=by_topic[topic][1]['type'])]
        def destroy_node(self):state.destroyed+=1
    def spin_once(node,timeout_sec):
        if state.now==0:
            for role,callback in reversed(state.subscriptions):callback(messages[role])
        state.now+=.02
    monkeypatch.setattr('maritime_perception.adapters.hardware_source_check.time.monotonic',lambda:state.now)
    monkeypatch.setattr('maritime_perception.adapters.hardware_source_check.time.time_ns',lambda:2_000_000_000+round(state.now*1e9))
    monkeypatch.setitem(sys.modules,'rclpy',NS(init=lambda **kw:None,ok=lambda:True,spin_once=spin_once,
        shutdown=lambda:setattr(state,'shutdown',state.shutdown+1)))
    monkeypatch.setitem(sys.modules,'rclpy.node',NS(Node=Node))
    monkeypatch.setitem(sys.modules,'rclpy.qos',NS(QoSProfile=lambda **kw:NS(**kw),
        HistoryPolicy=NS(KEEP_LAST='keep_last'),ReliabilityPolicy=NS(RELIABLE='reliable',BEST_EFFORT='best_effort'),
        DurabilityPolicy=NS(TRANSIENT_LOCAL='transient_local',VOLATILE='volatile')))
    monkeypatch.setitem(sys.modules,'rosidl_runtime_py.utilities',NS(get_message=lambda kind:kind))
    return state


def test_native_source_endpoint_subscribes_all_observed_topics_and_closes(tmp_path,monkeypatch):
    profile=load_profile();state=fake_ros(monkeypatch,profile)
    output=tmp_path/'source-check'
    result=run_live(profile,output,.03,[])
    assert len(state.subscriptions)==13 and state.shutdown==state.destroyed==1
    assert result['topic_profile']['all_required_topics_seen']
    assert result['camera_recent']['exact_triplet_count']==1
    assert json.loads((output/'summary.json').read_text())['normalized_events_emitted']==0
    assert (output/'source_checks.jsonl').exists()
    with pytest.raises(Unavailable,match='output_must_be_new'):run_live(profile,output,.03,[])


def test_native_source_endpoint_cleans_up_on_startup_failure(tmp_path,monkeypatch):
    profile=load_profile();state=fake_ros(monkeypatch,profile,fail_subscription=True)
    with pytest.raises(RuntimeError,match='subscription failed'):run_live(profile,tmp_path/'source-check',.03,[])
    assert state.shutdown==state.destroyed==1
    assert not (tmp_path/'source-check').exists()


def test_repeated_camera_header_retains_ambiguity_without_unbounded_storage():
    profile=load_profile();monitor=SourceMonitor(profile,max_camera_keys=2)
    messages=samples(profile)
    for _ in range(20):
        for role in ['image','camera_info','frame_metadata']:
            monitor.observe(role,messages[role],2_000_000_000)
    result=monitor.summary(2_000_000_000)
    assert result['camera_duplicate_records_discarded']==54
    assert result['camera_recent']['exact_triplet_count']==0
    assert all(len(values)==2 for index in [monitor.camera.images,monitor.camera.infos,monitor.camera.metadata]
               for values in index.values())
    assert result['topics']['/camera/image_rect']['count']==20


def test_ctrl_c_still_writes_a_source_summary_and_closes_ros(tmp_path,monkeypatch):
    profile=load_profile();state=fake_ros(monkeypatch,profile)
    def stop(node,timeout_sec):
        raise KeyboardInterrupt
    monkeypatch.setattr(sys.modules['rclpy'],'spin_once',stop)
    result=run_live(profile,tmp_path/'interrupted',15,[])
    assert result['interrupted']
    assert not result['topic_profile']['all_required_topics_seen']
    assert (tmp_path/'interrupted/summary.json').exists()
    assert state.shutdown==state.destroyed==1


def test_hardware_profile_does_not_accept_a_synthetic_camera_triplet():
    profile=load_profile();monitor=SourceMonitor(profile);messages=samples(profile)
    metadata=json.loads(messages['frame_metadata'].data)
    metadata['synthetic']=True
    messages['frame_metadata'].data=json.dumps(metadata)
    for role in ['image','camera_info','frame_metadata']:
        monitor.observe(role,messages[role],2_000_000_000)
    result=monitor.summary(2_000_000_000)
    assert result['camera_recent']['exact_triplet_count']==0
    assert result['camera_recent']['conflicting_geometry_count']==1
    assert not result['geolocation_ready']
