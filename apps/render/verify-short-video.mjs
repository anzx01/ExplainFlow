// Reproduce the reported six-scene video using its local artwork and narration.
import { readFileSync, writeFileSync } from "fs";
import { resolve } from "path";
import { buildRasterRevealFromBuffer } from "./trace.mjs";
import { writeGeneratedProject } from "./codegen.mjs";
import { bundleAndRender } from "./render-core.mjs";
import { continuousNarration } from "./continuous-narration.mjs";
import { timedRevealPaths } from "./reveal-timing.mjs";
import { upgradeScenesWithGlyphOutlines } from "./glyph.mjs";
import sharp from "sharp";

const started = Date.now();
const original = "429bcfd5-b2ef-42d4-905c-f804bc4f3c99";
const jobId = "short-video-handdraw-v8";
const source = readFileSync(`generated/${original}/GeneratedVideo.tsx`, "utf8");
const match = source.match(/const scenes = (.*?) as SceneSpec\[\];/s);
if (!match) throw new Error("Original scene specifications missing");
const scenes = JSON.parse(match[1]);
const scripts = [
  "你是否只想刷五分钟，抬头却发现半小时过去了？这期我们讲清楚，频繁刷短视频可能怎样影响注意力、睡眠和情绪，以及怎样拿回主动权。问题不是偶尔看一条，而是长时间、停不下来的使用。",
  "短视频不断切换内容，让人持续期待下一条。习惯了快速刺激后，读书和学习这些反馈较慢的任务，就可能显得没那么有吸引力。这不代表大脑坏了，而是提醒我们，专注需要练习，也需要减少干扰。",
  "信息看过，不等于真正学会。知识要留下来，需要理解、回忆和实际运用。快速划过大量内容，容易产生我已经懂了的感觉，却没有时间深入思考。想把有用内容变成知识，不妨停下来，用自己的话复述，再做一次练习。",
  "当平台不断推荐你感兴趣的内容，你看到的信息可能越来越相似。反复接触夸张的成功、外貌和消费展示，也可能带来比较和焦虑。但这些影响因人而异，不能把所有情绪问题都归因于短视频。",
  "睡前刷视频，最直接的影响是挤占睡眠时间。内容带来的兴奋，也可能让人更难停下来。反复比较还可能加重情绪负担。这些影响因人而异。判断是否需要调整，不只看分钟数，更要看它有没有影响睡眠、学习和现实生活。",
  "不必立刻彻底戒掉。先关闭自动播放和非必要通知，打开应用前就定好结束时间。学习时把手机放远一点，用散步或聊天替代一部分刷屏。如果已经明显影响生活，而且多次尝试仍控制不住，可以向专业人士求助。",
  "第一是保护注意力。第二是不让刷屏挤占睡眠。第三是给真实生活留下完整时间。今天就关掉自动播放并在睡前半小时停止刷屏。"
];
const keywords = [["频繁刷屏", "拿回主动权"], ["快速刺激", "专注练习"], ["深度加工", "回忆练习"], ["信息单一", "比较焦虑"], ["睡眠时间", "情绪负担"], ["关闭自动播放", "定时结束"], ["保护注意力", "保证睡眠", "完整时间"]];
scripts.splice(0,6,
  "看左边的手机。你是否只想刷五分钟，却刷了半小时？再看右边的大脑。不断出现的新内容，让人期待下一条。问题不是偶尔看一条，而是刷屏开始挤占睡眠、学习和生活。接下来，我们看它的几种影响。",
  "先看左边平稳的曲线，它代表持续专注。再看中间的闪电，频繁打断会打乱任务节奏。右边的手机代表不断切换的诱惑。回到学习任务时，需要重新找回思路。可以把手机放远，先完成一小段专注练习。",
  "从左边的信息输入开始。看过内容，不等于学会。再看中间的记忆环节，知识需要理解、回忆和运用。右边的手机提醒我们，快速划过可能挤掉深入加工的时间。遇到有用内容，停下来，用自己的话复述，再做一次练习。",
  "先看左侧不断循环的箭头。推荐系统会根据观看行为，继续推送相似内容。再看中间被包围的人，看到的信息可能越来越单一。右侧的循环提醒我们，要主动寻找不同来源，而不是只接受下一条推荐。",
  "先看左边起伏的情绪曲线。反复比较可能增加情绪负担，但影响因人而异。再看右边的睡眠循环。睡前刷屏会挤占睡眠时间，兴奋的内容也可能让人更难停下来。今天可以先试试，睡前半小时不刷视频。",
  "看左边的甜食，把它当作被动刷屏的比喻。偶尔放松可以，但不能代替生活的正餐。再看右边的蔬菜，它代表学习、运动和真实交流。让两边重新平衡：关闭自动播放，定好结束时间，给现实生活留下完整时间。"
);
const beats = [
  [{untilX:.45,phrase:"手机"},{untilX:1,phrase:"大脑"}],
  [{untilX:.4,phrase:"平稳"},{untilX:.65,phrase:"闪电"},{untilX:1,phrase:"右边的手机"}],
  [{untilX:.34,phrase:"信息输入"},{untilX:.65,phrase:"记忆环节"},{untilX:1,phrase:"右边的手机"}],
  [{untilX:.35,phrase:"循环的箭头"},{untilX:.65,phrase:"被包围的人"},{untilX:1,phrase:"右侧的循环"}],
  [{untilX:.5,phrase:"情绪曲线"},{untilX:1,phrase:"睡眠循环"}],
  [{untilX:.5,phrase:"甜食"},{untilX:1,phrase:"蔬菜"}],
];
const noteStarts = ["问题不是", "回到学习任务时", "遇到有用内容", "要主动寻找不同来源", "今天可以先试试", "让两边重新平衡"];
beats.forEach((items, index) => { items.at(-1).endBefore = noteStarts[index]; });
// Legacy fixtures predate text-free image validation. Remove only inspected
// label rectangles on derived copies; leave the original artwork untouched.
const labelRects = {
  1: [[0,0,260,315],[400,0,230,278]],
  2: [[260,110,150,65],[45,235,82,20],[50,267,82,38],[205,266,90,40],[348,254,102,111],[505,356,75,32],[0,450,630,60]],
  4: [[0,0,630,83],[100,83,440,45],[30,160,41,330],[80,210,60,28],[70,503,238,22],[518,410,62,45],[40,528,260,28],[420,528,170,28]],
};
scenes.push({...scenes[5], title: "要点总结：把主动权拿回来", summaryPoints: ["① 保护注意力，减少频繁切换", "② 不用刷屏挤占睡眠", "③ 给学习、运动和陪伴留整段时间", "今天行动：关自动播放，定时看，睡前停"]});
const storyboard = await continuousNarration({scenes: scenes.map((s,i)=>({id:`scene_${i}`,title:s.title,narration:scripts[i]}))});
scenes.forEach((scene,i)=>{
  Object.assign(scene, storyboard.scenes[i], {duration:storyboard.scenes[i].timingPlan.durationFrames, keywords:keywords[i], transitionFrames:0});
  scene.drawOps=[]; scene.glyphPaths=[]; scene.texts=[]; scene.strokes=[];
  scene.renderElements=[];
});
for (const [index, scene] of scenes.entries()) {
  if (scene.summaryPoints) {
    scene.rasterReveal = null;
    scene.referenceImageAsset = null;
    scene.handUsage = "trace";
    // The board is written from the actual spoken cues, with no static recap
    // overlay covering the pen and no repeated decorative marks.
    scene.summaryPoints = [];
    scene.texts = scene.subtitleCues.map((cue, cueIndex) => {
      const id = `s${index}_recap_${cueIndex}`;
      scene.drawOps.push({id, kind: "text", startFrame: cue.startFrame, endFrame: cue.endFrame, points: []});
      return {opId: id, text: cue.text, x: 112, y: 112 + cueIndex * 68, fontSize: 28, maxWidth: 740, color: "#1D1D1F"};
    });
    continue;
  }
  let image = readFileSync(resolve("public", scene.referenceImageAsset));
  if (labelRects[index]) {
    const {width,height} = await sharp(image).metadata();
    const rects = labelRects[index].map(([x,y,w,h]) => `<rect x="${x / 630 * width}" y="${y / 630 * height}" width="${w / 630 * width}" height="${h / 630 * height}" fill="white"/>`).join("");
    image = await sharp(image).flatten({background:"white"}).composite([{input:Buffer.from(`<svg width="${width}" height="${height}">${rects}</svg>`)}]).png().toBuffer();
  }
  image = await sharp(image).flatten({background:"white"}).trim({background:"white",threshold:10}).png().toBuffer();
  const raster = await buildRasterRevealFromBuffer(image, jobId, { id: `scene_${index}` }, { forceTrace: true });
  if (!raster.rasterReveal.strokes.length) throw new Error(`No drawable strokes: scene ${index}`);
  const {imageWidth,imageHeight} = raster.rasterReveal;
  const scale = Math.min(580 / imageWidth, 250 / imageHeight);
  const old = { x: (960 - imageWidth * scale) / 2, y: 88, width: imageWidth * scale, height: imageHeight * scale };
  const paths = timedRevealPaths(raster.rasterReveal.strokes, scene.subtitleCues, beats[index], scene.duration);
  scene.referenceImageAsset = raster.referenceImageAsset;
  scene.handUsage = "trace";
  scene.drawOps = scene.drawOps.filter(op => !op.id.includes("_raster_"));
  scene.rasterReveal = { ...raster.rasterReveal, ...old, renderMode: "trace", strokes: paths.map((path, i) => {
    const points = path.points.map(p => ({ x: old.x + p.x * old.width, y: old.y + p.y * old.height }));
    const id = `s${index}_raster_${i}`;
    for (const [phase, from, to] of [["ink", path.inkStart, path.inkEnd], ["color", path.colorStart, path.colorEnd]]) {
      scene.drawOps.push({ id: phase === "ink" ? id : `${id}_color`, kind: "path", phase,
        startFrame: from, endFrame: to, points });
    }
    const d = points.map((p, j) => `${j ? "L" : "M"} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(" ");
    const length = points.slice(1).reduce((sum, p, j) => sum + Math.hypot(p.x - points[j].x, p.y - points[j].y), 0);
    return { opId: id, colorOpId: `${id}_color`, d, dashLength: length, revealWidth: Math.max(8, path.revealWidth * Math.max(old.width, old.height)) };
  }) };
  const firstNote = scene.subtitleCues.findIndex(cue => cue.text.includes(noteStarts[index]));
  if (firstNote < 0) throw new Error(`Missing spoken action: scene ${index}`);
  scene.subtitleCues.slice(firstNote).forEach((cue, cueIndex) => {
    const id = `s${index}_note_${cueIndex}`;
    scene.drawOps.push({id,kind:"text",startFrame:cue.startFrame,endFrame:cue.endFrame,points:[],beatId:`cue_${firstNote + cueIndex}`});
    scene.texts.push({opId:id,text:cue.text,x:70 + cueIndex % 2 * 430,y:345 + Math.floor(cueIndex / 2) * 34,fontSize:18,maxWidth:410,color:"#1D1D1F"});
  });
  console.log(`Scene ${index + 1}: ${paths.length} pen strokes`);
}
const templateFile = readFileSync("../../services/api/src/planner/fallback/_tsx_template_string.py", "utf8");
const templateStart = templateFile.indexOf('import React');
let template = templateFile.slice(templateStart, templateFile.lastIndexOf("'''"));
if (!template.includes("__SCENES_JSON__")) throw new Error("Template could not be loaded");
const outlined = upgradeScenesWithGlyphOutlines(scenes).scenes;
for (const scene of outlined) {
  if (scene.subtitleCues.map(cue => cue.text).join("") !== scene.narration) throw new Error("Spoken text and subtitles differ");
  for (let frame = 0; frame < scene.duration; frame++) {
    if (!scene.drawOps.some(op => op.startFrame <= frame && op.endFrame > frame)) throw new Error(`No drawing at spoken frame ${frame}: ${scene.title}`);
  }
}
template = template.replace("__SCENES_JSON__", JSON.stringify(outlined)).replaceAll("__VIDEO_WIDTH__", "960").replaceAll("__VIDEO_HEIGHT__", "540")
  .replaceAll("__BACKGROUND_MUSIC_URL__", "null").replaceAll("__BACKGROUND_MUSIC_VOLUME__", "0.12").replaceAll("__SUBTITLES_ENABLED__", "true");
const generated = { tsx: template, width: 960, height: 540, fps: 24, durationInFrames: scenes.reduce((sum, s) => sum + s.duration, 0) };
const { entryPath } = writeGeneratedProject(jobId, generated, storyboard, { subtitlesEnabled: true });
await bundleAndRender(jobId, entryPath, resolve("../../outputs/short-video-harms-v8.mp4"));
const report = { elapsedSeconds: (Date.now() - started) / 1000, videoSeconds: generated.durationInFrames / 24, sceneCount: scenes.length, width: 960, height: 540, fps: 24 };
writeFileSync(resolve("../../outputs/short-video-harms-v8-test.json"), JSON.stringify(report, null, 2));
console.log(report);
