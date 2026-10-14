from typing import Any
import re


def _numeric(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def condition_matches(actual: Any, expression: str) -> bool:
    """Evaluate one safe comparator; it never evaluates Python expressions."""
    match = re.fullmatch(r'\s*(<=|>=|==|!=|<|>)\s*(.*?)\s*', expression)
    if not match:
        return False
    operator, raw = match.groups()
    lowered = raw.strip().casefold()
    if lowered in {'true', 'false'}:
        expected: Any = lowered == 'true'
    else:
        number = _numeric(raw)
        expected = number if number is not None else raw.strip().strip("\\\"'")
    if operator in {'<', '>', '<=', '>='}:
        left = _numeric(actual)
        right = _numeric(expected)
        if left is None or right is None:
            return False
        return {'<': left < right, '>': left > right, '<=': left <= right, '>=': left >= right}[operator]
    if isinstance(expected, bool):
        if isinstance(actual, str):
            actual = actual.strip().casefold() in {'true', 'yes', 'connected', '1'}
        return actual == expected if operator == '==' else actual != expected
    if isinstance(actual, str) and isinstance(expected, str):
        actual, expected = actual.strip().casefold(), expected.strip().casefold()
    return (actual == expected) if operator == '==' else (actual != expected)


def analyze_command_output(command: dict[str, Any], parsed: dict[str, Any]) -> dict[str, Any]:
    analysis = command.get('analysis') or {}
    schema = command.get('output_schema') or {}
    missing = [field for field in schema if parsed.get(field) is None]
    if missing:
        return {
            'verdict': 'inconclusive', 'finding': 'Required output fields are missing',
            'advice': 'The output did not show all fields required for a reliable check. Continue with the next configured command or ask support to review it.',
            'evidence': [f'missing fields: {", ".join(missing)}'],
        }
    rules = analysis.get('rules') or []
    for rule in rules:
        field = rule.get('field')
        if field in parsed and condition_matches(parsed.get(field), str(rule.get('condition', ''))):
            return {
                'verdict': 'issue_found', 'finding': rule.get('finding', f'Issue detected in {field}'),
                'advice': rule.get('advice', 'Contact support.'), 'evidence': [f'{field}={parsed.get(field)}'],
            }
    # Without explicit machine-checkable rules, presence of fields is not evidence they are correct.
    if not rules:
        return {
            'verdict': 'inconclusive', 'finding': 'No verified rules are configured for these output fields',
            'advice': 'The command output was readable, but the configuration does not contain verified comparison rules. Ask support to compare it with the approved device settings.',
            'evidence': [f'{field}={parsed.get(field)}' for field in schema],
        }
    return {
        'verdict': 'ok', 'finding': 'No configured fault rule matched',
        'advice': 'The checked fields look normal under the configured rules. Confirm whether tracking is working; if not, continue with the next diagnostic step.',
        'evidence': [f'{field}={parsed.get(field)}' for field in schema],
    }
