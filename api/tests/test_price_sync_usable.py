from api.price_sync_policy import price_sync_usable


def test_partial_sync_is_usable_above_threshold():
    assert price_sync_usable({'status': 'failed', 'details': 'Synced 235/284 symbols'})


def test_partial_sync_unusable_below_threshold_or_unparsed():
    assert not price_sync_usable({'status': 'failed', 'details': 'Synced 100/284 symbols'})
    assert not price_sync_usable({'status': 'failed', 'details': 'Recovered 1/49 prices'})
    assert not price_sync_usable(None)


def test_success_always_usable():
    assert price_sync_usable({'status': 'success'})
