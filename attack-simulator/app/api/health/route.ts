export const dynamic = "force-dynamic";

export function GET(): Response {
  const configuredProvider = process.env.VOICE_PROVIDER?.trim() || "mock";
  const fishConfigured = Boolean(process.env.FISH_AUDIO_API_KEY?.trim());
  const ready = configuredProvider === "mock" || fishConfigured;

  return Response.json(
    {
      status: ready ? "ok" : "configuration_required",
      provider: configuredProvider,
      fishConfigured,
    },
    {
      status: ready ? 200 : 503,
      headers: { "Cache-Control": "no-store" },
    },
  );
}
