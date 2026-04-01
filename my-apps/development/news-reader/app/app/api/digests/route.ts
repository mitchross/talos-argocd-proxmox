import { getDigests } from "@/app/lib/temporal";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const digests = await getDigests();
    return Response.json(digests);
  } catch (error) {
    return Response.json(
      { error: String(error) },
      { status: 500 }
    );
  }
}
