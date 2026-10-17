// Keep each object's paths inside the narration window that introduces it.
export function timedRevealPaths(paths, cues, beats, duration) {
  if (!cues.length) throw new Error("No subtitle cues for timed drawing");
  const windows = beats.map((beat, index) => {
    const cueIndex = cues.findIndex(cue => cue.text.includes(beat.phrase));
    if (cueIndex < 0) throw new Error(`No spoken cue for visual object: ${beat.phrase}`);
    const endCueIndex = beat.endBefore ? cues.findIndex(cue => cue.text.includes(beat.endBefore)) : -1;
    if (beat.endBefore && endCueIndex < 0) throw new Error(`No spoken cue for visual boundary: ${beat.endBefore}`);
    return {...beat, start: index === 0 ? cues[0].startFrame : cues[cueIndex].startFrame,
      end: endCueIndex < 0 ? null : cues[endCueIndex].startFrame};
  });
  if (!windows.length || windows.some((window, i) => i > 0 && window.start <= windows[i - 1].start)) {
    throw new Error("Visual objects must follow spoken order");
  }
  const groups = windows.map(() => []);
  for (const path of paths) {
    const centerX = path.points.reduce((sum, p) => sum + p.x, 0) / path.points.length;
    const index = windows.findIndex(window => centerX < window.untilX);
    if (index < 0) throw new Error("Drawing lies outside visual object regions");
    groups[index].push(path);
  }
  return groups.flatMap((group, i) => {
    if (!group.length) throw new Error(`No drawing for visual object: ${windows[i].phrase}`);
    const start = windows[i].start;
    const end = Math.min(duration, windows[i].end ?? windows[i + 1]?.start ?? cues.at(-1).endFrame ?? duration);
    if (end <= start) throw new Error("Visual beat has no drawing time");
    return group.map((path, j) => ({...path,
      inkStart: start + (end - start) * j / group.length,
      inkEnd: start + (end - start) * (j + 0.72) / group.length,
      colorStart: start + (end - start) * (j + 0.72) / group.length,
      colorEnd: start + (end - start) * (j + 1) / group.length,
    }));
  });
}
