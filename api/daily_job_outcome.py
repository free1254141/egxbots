"""Report execution health without changing the market-data completion contract."""

WITHHELD_RECOVERY = {
    'Price sync incomplete; dependent recovery withheld',
    'Indicators incomplete; dependent recovery withheld',
}


def effective_daily_steps(steps):
    """Preserve actual results when a recovery did not execute the operation.

    Keep the full append-only audit separately. Failed subset price retries
    cannot replace the original full-universe coverage used for readiness.
    """
    latest = {}
    for step in steps:
        if not isinstance(step, dict) or not step.get('step'):
            continue
        name = step['step']
        previous = latest.get(name)
        if step.get('recovery_attempt'):
            if step.get('status') == 'started' and previous:
                continue
            if (step.get('status') == 'failed' and previous
                    and step.get('details') in WITHHELD_RECOVERY):
                continue
            if (name == 'sync_prices' and step.get('status') == 'failed' and previous
                    and str(step.get('details', '')).startswith('Recovered ')
                    and str(previous.get('details', '')).startswith('Synced ')):
                continue
        latest[name] = step
    return list(latest.values())


def summarise_daily_steps(steps):
    latest = {step.get('step'): step for step in effective_daily_steps(steps)}
    failed = [step for step in latest.values() if step.get('status') in ('failed', 'started')]
    return {
        'outcome': 'partial' if failed else 'completed',
        'failed_steps': [step['step'] for step in failed],
        'error': '; '.join(f"{step['step']}: {step.get('details') or 'Stage did not finish'}" for step in failed)[:1500] or None,
    }


def social_reports_outcome(result):
    if result.get('skipped'):
        return True, 'Skipped - ' + result.get('reason', 'Not eligible'), 0
    reports = result.get('reports') or {}
    images = result.get('images') or {}
    ready = [kind for kind, report in reports.items() if report.get('status') == 'ready']
    failures = [f"{kind}: {report.get('error') or report.get('reason') or report.get('status')}"
                for kind, report in reports.items() if report.get('status') not in ('ready', 'skipped')]
    if not reports:
        failures.append('No report results returned')
    failures.extend(f"{kind} image: {state}" for kind, state in images.items() if state not in ('ready', 'cached', 'skipped'))
    return not failures, '; '.join(failures) if failures else f"{len(ready)} verified reports ready", len(ready)


def scheduler_result_status(result):
    if isinstance(result, dict) and result.get('outcome') in ('completed', 'partial', 'failed'):
        return result['outcome']
    return 'completed'
