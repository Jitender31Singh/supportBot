from trackobit_assistant.services.conversation_memory import update_conversation_summary


def test_summary_only_compacts_older_messages():
    messages = [
        {'role': ('user' if i % 2 == 0 else 'assistant'), 'content': f'message-{i}'}
        for i in range(16)
    ]
    summary, count = update_conversation_summary(messages, '', 0, keep_recent=10)
    assert count == 6
    assert 'message-5' in summary
    assert 'message-6' not in summary


def test_summary_does_not_repeat_already_summarized_messages():
    messages = [
        {'role': ('user' if i % 2 == 0 else 'assistant'), 'content': f'message-{i}'}
        for i in range(20)
    ]
    summary, count = update_conversation_summary(messages, '', 0, keep_recent=10)
    summary2, count2 = update_conversation_summary(messages + [{'role': 'user', 'content': 'message-20'}], summary, count, keep_recent=10)
    assert count2 > count
    assert summary2.count('message-5') == 1
