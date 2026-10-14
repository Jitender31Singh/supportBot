from trackobit_assistant.schemas.models import CommandSpec
from trackobit_assistant.services.command_selector import select_next_command

def spec(cid, order, next_ids=None):
    return CommandSpec(id=cid,order=order,command=cid.upper()+'#',purpose='check',how_to_send='send it',next_if_inconclusive=next_ids or [])

def test_skips_executed_commands_and_honors_inconclusive_order():
    commands=[spec('status',1,['param']),spec('param',2),spec('other',3)]
    history=[{'command_id':'status','next_if_inconclusive':['param']}]
    assert select_next_command(commands,history).id=='param'
    history.append({'command_id':'param'})
    assert select_next_command(commands,history).id=='other'
