from workers import WorkerEntrypoint, Response

class Default(WorkerEntrypoint):
    async def fetch(self, request):
        try:
            result = await self.env.DB.prepare(
                "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
            ).run()
            return Response.json({
                "ok": True,
                "service": "simone-cloudflare",
                "database": "connected",
                "tables": result.results,
            })
        except Exception as error:
            print(f"D1 connection error: {error}")
            return Response.json({
                "ok": False,
                "service": "simone-cloudflare",
                "database": "error",
            }, status=500)
