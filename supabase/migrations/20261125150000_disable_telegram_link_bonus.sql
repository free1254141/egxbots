-- Permanently disable automatic +10 chat bonus credits on Telegram link.
-- Free accounts strictly receive 10 lifetime messages shared across Website + Telegram.

CREATE OR REPLACE FUNCTION public.trg_grant_telegram_link_bonus()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
  RETURN new;
END;
$$;

DELETE FROM public.chat_bonus_credits
WHERE source = 'telegram_link';
