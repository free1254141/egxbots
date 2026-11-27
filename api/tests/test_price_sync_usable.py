from api.cache_invalidation import select_cache_tags
from api.price_sync_policy import price_sync_usable


def test_partial_sync_is_usable_above_threshold():
    assert price_sync_usable({'status': 'failed', 'details': 'Synced 235/284 symbols'})


def test_morning_coverage_override_allows_209_of_275():
    step = {'step': 'sync_prices', 'status': 'failed', 'details': 'Synced 209/275 symbols'}
    assert not price_sync_usable(step)
    assert price_sync_usable(step, min_coverage=0.65)
    assert not price_sync_usable({'step': 'sync_prices', 'status': 'failed', 'details': 'Synced 100/275 symbols'}, min_coverage=0.65)

    tags = select_cache_tags(
        [
            step,
            {'step': 'calculate_indicators', 'status': 'success'},
            {'step': 'short_swings_daily', 'status': 'success'},
        ],
        min_coverage=0.65,
    )
    assert 'daily-market-data' in tags
    assert 'daily-short-swings' in tags


def test_partial_sync_unusable_below_threshold_or_unparsed():
    assert not price_sync_usable({'status': 'failed', 'details': 'Synced 100/284 symbols'})
    assert not price_sync_usable({'status': 'failed', 'details': 'Recovered 1/49 prices'})
    assert not price_sync_usable(None)


def test_success_always_usable():
    assert price_sync_usable({'status': 'success'})
