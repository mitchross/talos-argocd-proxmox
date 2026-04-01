import { triggerDigest } from "@/app/lib/temporal";

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const categories = body.categories || ["tech", "security"];
    const maxArticles = body.maxArticles || 3;

    const result = await triggerDigest(categories, maxArticles);
    return Response.json(result);
  } catch (error) {
    return Response.json(
      { error: String(error) },
      { status: 500 }
    );
  }
}
