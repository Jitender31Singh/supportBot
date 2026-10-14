from trackobit_assistant.services.retry_policy import next_retry

def test_retry_is_per_step_and_bounded():
    counters, allowed, count=next_retry({},'vehicle_no',3)
    assert allowed and count==1
    counters, allowed, count=next_retry(counters,'vehicle_no',3)
    assert allowed and count==2
    counters, allowed, count=next_retry(counters,'vehicle_no',3)
    assert not allowed and count==3
    assert next_retry(counters,'screenshot',2)[2]==1
