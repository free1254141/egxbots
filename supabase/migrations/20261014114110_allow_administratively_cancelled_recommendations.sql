-- Applied remotely with this version; cancellation is not a simulated win/loss.
alter table public.scan_results drop constraint scan_results_status_check;
alter table public.scan_results add constraint scan_results_status_check
    check (status in ('open', 'win', 'loss', 'cancelled'));
