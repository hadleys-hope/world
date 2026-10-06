/** Drain cheap construction steps within one idle slice; always yield after expensive work. */
export function drainBuildQueue(
  queue,
  recordCost,
  deadline,
  now = () => performance.now(),
) {
  const start = now();
  const budget = Math.min(6, Math.max(1, deadline?.timeRemaining?.() ?? 6));
  let count = 0;
  do {
    const step = queue.shift();
    if (!step) break;
    const before = now();
    step();
    recordCost(now() - before);
    count++;
  } while (queue.length && count < 32 && now() - start < budget);
  // The count cap also lets pending network promises settle when a waiting step requeues itself.
  return queue.length > 0;
}
