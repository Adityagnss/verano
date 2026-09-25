/** Liveness probe for the container health check. */
export function GET() {
  return Response.json({ status: "ok" })
}
