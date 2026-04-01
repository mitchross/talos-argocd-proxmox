import { Client, Connection } from "@temporalio/client";

const TEMPORAL_ADDRESS =
  process.env.TEMPORAL_ADDRESS ||
  "temporal-frontend.temporal.svc.cluster.local:7233";

let clientPromise: Promise<Client> | null = null;

function getClient(): Promise<Client> {
  if (!clientPromise) {
    clientPromise = Connection.connect({
      address: TEMPORAL_ADDRESS,
    }).then((connection) => new Client({ connection, namespace: "default" }));
  }
  return clientPromise;
}

export interface Article {
  title: string;
  link: string;
  source: string;
  summary: string;
}

export interface DigestResult {
  categories: Record<string, Article[]>;
  headline: string;
  total_articles: number;
}

export interface DigestInfo {
  workflowId: string;
  runId: string;
  status: string;
  startTime: string;
  result: DigestResult | null;
}

export async function getDigests(): Promise<DigestInfo[]> {
  const client = await getClient();
  const digests: DigestInfo[] = [];

  const workflows = client.workflow.list({
    query: `WorkflowType = "NewsDigestWorkflow" ORDER BY StartTime DESC`,
  });

  for await (const wf of workflows) {
    const info: DigestInfo = {
      workflowId: wf.workflowId,
      runId: wf.runId ?? "",
      status: wf.status.name,
      startTime: wf.startTime?.toISOString() ?? "",
      result: null,
    };

    if (wf.status.name === "COMPLETED") {
      try {
        const handle = client.workflow.getHandle(wf.workflowId, wf.runId);
        info.result = await handle.result();
      } catch {
        // skip if result unavailable
      }
    }

    digests.push(info);
    if (digests.length >= 10) break;
  }

  return digests;
}

export async function triggerDigest(
  categories: string[],
  maxArticles: number = 3
): Promise<{ workflowId: string; runId: string }> {
  const client = await getClient();
  const workflowId = `digest-${Date.now()}`;

  const handle = await client.workflow.start("NewsDigestWorkflow", {
    taskQueue: "news-digest",
    workflowId,
    args: [{ categories, max_articles: maxArticles }],
  });

  return { workflowId, runId: handle.firstExecutionRunId };
}
