"""Report execution health without changing the market-data completion contract."""

WITHHELD_RECOVERY = {
    'Price sync incomplete; dependent recovery withheld',
    'Indicators incomplete; dependent recovery withheld',
}


def is_withheld_recovery(step):
    return bool(step and (step.get('status') == 'blocked' or (
        step.get('recovery_attempt') and step.get('details') in WITHHELD_RECOVERY)))


def executed_recovery_stages(steps):
    """A blocked/audit-only attempt is not execution; ambiguous starts are."""
    executed, pending = set(), set()
    for step in steps:
        if not step.get('recovery_attempt') or not step.get('step'):
            continue
        name = step['step']
        if is_withheld_recovery(step) or step.get('execution_started') is False:
            pending.discard(name)
        elif step.get('status') == 'started':
            pending.add(name)
        else:
            pending.discard(name)
            executed.add(name)
    return executed | pending


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
            if is_withheld_recovery(step):
                if previous and not (previous.get('status') == 'started' and previous.get('recovery_attempt')):
                    continue
                latest[name] = {**step, 'status': 'blocked', 'execution_started': False}
                continue
            if (name == 'sync_prices' and not step.get('coverage') and previous
                    and str(step.get('details', '')).startswith('Recovered ')
                    and str(previous.get('details', '')).startswith('Synced ')):
                continue
        latest[name] = step
    return list(latest.values())


def summarise_daily_steps(steps):
    latest = {step.get('step'): step for step in effective_daily_steps(steps)}
    failed = [step for step in latest.values() if step.get('status') in ('failed', 'started', 'blocked')]
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
