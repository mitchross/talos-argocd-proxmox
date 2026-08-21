(() => {
  const formatNumber = (value, maximumFractionDigits = 0) =>
    new Intl.NumberFormat(undefined, { maximumFractionDigits }).format(value);

  const parseUsage = (text) => {
    const usage = {};

    for (const line of text.split('\n')) {
      const match = line.trim().match(/^([A-Za-z_][A-Za-z0-9_]*):\s*(-?\d+(?:\.\d+)?)$/);
      if (match) usage[match[1]] = Number(match[2]);
    }

    if (!Number.isFinite(usage.prompt_n) || !Number.isFinite(usage.predicted_n)) return null;
    return usage;
  };

  const formatUsage = (usage) => {
    const inputTokens = usage.input_tokens ?? usage.prompt_n;
    const outputTokens = usage.output_tokens ?? usage.predicted_n;
    const totalTokens = usage.total_tokens ?? inputTokens + outputTokens;
    const promptSeconds = usage.prompt_ms / 1000;
    const outputSeconds = usage.predicted_ms / 1000;
    const lines = [];

    lines.push(
      `Input:  ${formatNumber(inputTokens)} tokens · ${formatNumber(promptSeconds, 2)} s` +
        (Number.isFinite(usage.prompt_per_second)
          ? ` · ${formatNumber(usage.prompt_per_second, 1)} tok/s`
          : '')
    );
    lines.push(
      `Output: ${formatNumber(outputTokens)} tokens · ${formatNumber(outputSeconds, 2)} s` +
        (Number.isFinite(usage.predicted_per_second)
          ? ` · ${formatNumber(usage.predicted_per_second, 1)} tok/s`
          : '')
    );

    if (Number.isFinite(usage.draft_n) && usage.draft_n > 0) {
      const accepted = usage.draft_n_accepted ?? 0;
      lines.push(
        `MTP:    ${formatNumber(accepted)}/${formatNumber(usage.draft_n)} accepted · ${formatNumber(
          (accepted / usage.draft_n) * 100,
          1
        )}%`
      );
    }

    const totalSeconds =
      Number.isFinite(usage.prompt_ms) && Number.isFinite(usage.predicted_ms)
        ? (usage.prompt_ms + usage.predicted_ms) / 1000
        : null;
    lines.push(
      `Total:  ${formatNumber(totalTokens)} tokens` +
        (totalSeconds !== null ? ` · ${formatNumber(totalSeconds, 2)} s` : '') +
        (Number.isFinite(usage.cache_n)
          ? ` · ${usage.cache_n > 0 ? `${formatNumber(usage.cache_n)} cached` : 'uncached'}`
          : '')
    );

    return lines.join('\n');
  };

  const formatPre = (pre) => {
    if (pre.dataset.friendlyUsageMetrics === 'true') return;

    const usage = parseUsage(pre.textContent ?? '');
    if (!usage) return;

    pre.textContent = formatUsage(usage);
    pre.dataset.friendlyUsageMetrics = 'true';
  };

  const scan = (node) => {
    if (!(node instanceof Element)) return;
    if (node.matches('pre')) formatPre(node);
    node.querySelectorAll('pre').forEach(formatPre);
  };

  new MutationObserver((records) => {
    for (const record of records) record.addedNodes.forEach(scan);
  }).observe(document.documentElement, { childList: true, subtree: true });

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => scan(document.body), { once: true });
  } else {
    scan(document.body);
  }
})();
