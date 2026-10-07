"""Independent expected service sequence from declared byte work and policy."""


def quantum_from_result(result):
    quantum = result['policy'].get('memory_quantum_bytes')
    if quantum is not None and (type(quantum) is not int or quantum <= 0):
        raise ValueError('Invalid recorded memory quantum')
    return quantum


def expected_demands(demands, category, quantum):
    if quantum is None or category != 'memory':
        return list(demands)
    expected = []
    for resource, unit, amount in demands:
        if unit != 'bytes':
            raise ValueError('Memory burst demand must be bytes')
        full, tail = divmod(amount, quantum)
        expected.extend([(resource, unit, quantum)] * full)
        if tail:
            expected.append((resource, unit, tail))
    return expected
