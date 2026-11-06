import LandingClient from "./LandingClient";

/**
 * The landing page is marketing content plus client-side data widgets, so the
 * document itself only needs to be regenerated when the copy or the build
 * changes — at most once a day. Every visitor is served the same prerendered
 * HTML from the Edge CDN, and the widgets below fetch their own daily-cached
 * endpoints.
 */
export const revalidate = 86400;

export default function HomePage() {
  return <LandingClient />;
}
