from pathlib import Path
from trackobit_assistant.adapters.command_registry import YamlCommandRegistry

def test_yaml_command_registry_loads_all_devices():
    commands_dir = Path(__file__).parents[1] / 'data' / 'commands'
    registry = YamlCommandRegistry(commands_dir)
    devices = registry.list_supported_devices()
    assert len(devices) >= 23
    assert 'Concox' in devices or 'Concox V5' in devices
    assert 'Teltonika' in devices
    assert 'ET-300' in devices

def test_all_excel_commands_included_in_commands_list():
    commands_dir = Path(__file__).parents[1] / 'data' / 'commands'
    registry = YamlCommandRegistry(commands_dir)

    concox_cmds = {c.id: c.command for c in registry.get_commands('Concox')}
    assert 'status' in concox_cmds
    assert 'param' in concox_cmds
    assert 'server' in concox_cmds
    assert 'apn' in concox_cmds
    assert 'timezone' in concox_cmds
    assert 'timer' in concox_cmds

    assert concox_cmds['status'] == 'STATUS#'
    assert concox_cmds['param'] == 'PARAM#'
    assert 'SERVER,0,52.74.44.145,8505,0#' in concox_cmds['server']
    assert 'APN,airtelgprs.com#' in concox_cmds['apn']
    assert 'GMT,E,0,00#' in concox_cmds['timezone']
    assert 'TIMER,20,20#' in concox_cmds['timer']

def test_alias_and_fuzzy_matching():
    commands_dir = Path(__file__).parents[1] / 'data' / 'commands'
    registry = YamlCommandRegistry(commands_dir)

    assert len(registry.get_commands('Concox')) > 0
    assert len(registry.get_commands('ET-300')) > 0
    assert len(registry.get_commands('Teltonika')) > 0

    assert len(registry.get_commands('Concox GT06F')) > 0
    assert len(registry.get_commands('GT06F')) > 0
    assert len(registry.get_commands('Teltonika_CAN')) > 0
    assert len(registry.get_commands('TMT250')) > 0
    assert len(registry.get_commands('BW-602')) > 0

    assert len(registry.get_commands('et300')) > 0
    assert len(registry.get_commands('et 300')) > 0
    assert len(registry.get_commands('bw09')) > 0
    assert len(registry.get_commands('wetrack800')) > 0

def test_configuration_retrieval():
    commands_dir = Path(__file__).parents[1] / 'data' / 'commands'
    registry = YamlCommandRegistry(commands_dir)

    concox_cfg = registry.get_configuration('Concox')
    assert concox_cfg is not None
    assert 'SERVER,0,52.74.44.145,8505,0#' in concox_cfg.get('server', '')
    assert concox_cfg.get('port') == 8505

    et_cfg = registry.get_configuration('ET-300')
    assert et_cfg is not None
    assert '#6666#IP#52.74.44.145#5023#' in et_cfg.get('server', '')
    assert et_cfg.get('port') == 5023

    teltonika_cfg = registry.get_configuration('Teltonika')
    assert teltonika_cfg is not None
    assert 'setparam 2004:52.74.44.145' in teltonika_cfg.get('server', '')
    assert teltonika_cfg.get('port') == 8501

def test_teltonika_command_sequence():
    commands_dir = Path(__file__).parents[1] / 'data' / 'commands'
    registry = YamlCommandRegistry(commands_dir)
    cmds = registry.get_commands('Teltonika')
    cmd_names = [c.command for c in cmds]
    assert 'getstatus' in cmd_names
    assert 'getgps' in cmd_names
    assert 'getver' in cmd_names
    assert 'setparam 2004:52.74.44.145' in cmd_names
    assert 'cpureset' in cmd_names
