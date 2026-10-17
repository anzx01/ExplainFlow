// Render actual local-model paintings; never substitute procedural icons.
import assert from "node:assert/strict";
import {createHash} from "node:crypto";
import {readFileSync,writeFileSync,mkdirSync} from "node:fs";
import {resolve,join} from "node:path";
import sharp from "sharp";
import {continuousNarration} from "./continuous-narration.mjs";
import {buildRasterRevealFromBuffer} from "./trace.mjs";
import {timedRevealPaths} from "./reveal-timing.mjs";
import {upgradeScenesWithGlyphOutlines} from "./glyph.mjs";
import {writeGeneratedProject} from "./codegen.mjs";
import {bundleAndRender} from "./render-core.mjs";
import {jobs,saveJobsSync} from "./jobs.mjs";

const jobId="sugar-harms-local-flux-v4";
const artDir=resolve("../../image/sugar-local-art-v3");
const scriptSource=readFileSync("generated/sugar-harms-handdraw-v2/GeneratedVideo.tsx","utf8");
const original=JSON.parse(scriptSource.match(/const scenes = (.*?) as SceneSpec\[\];/s)[1]);
const selected=JSON.parse(readFileSync(join(artDir,"selected.json"),"utf8"));
const replacementFiles={"1_0_1":"tooth-enamel-replacement.png","3_1_0":"sugar-cube-replacement.png"};
const replacements=Object.values(replacementFiles).map(name=>{
  const file=join(artDir,name),meta=JSON.parse(readFileSync(file.replace(/\.png$/,".json"),"utf8"));
  assert.equal(meta.provider,"local");
  assert.equal(createHash("sha256").update(readFileSync(file)).digest("hex"),meta.sha256);
  return {file,meta};
});
const labels=[
  ["不必禁糖","游离糖","甜食来源","完整水果"],
  ["细菌产酸","牙釉质受损","频繁吃甜","含氟牙膏"],
  ["额外热量","饱腹感较弱","长期增重","总量与习惯"],
  ["代谢健康","风险关联","不等于必然","整体饮食"],
  ["10g / 100mL","500mL = 50g","2000kcal：少于50g","少于25g"],
  ["换成白水","看整瓶容量","完整水果","逐步减糖"],
];
const sources=original.map((_,index)=>{
  const name=selected[String(index)];
  assert(name?.startsWith(`scene-${index}-`) && !name.includes("/"),`Missing selected local artwork for scene ${index}`);
  const meta=JSON.parse(readFileSync(join(artDir,name.replace(/\.png$/,".json")),"utf8"));
  assert.equal(meta.provider,"local");
  const file=join(artDir,name);
  assert.equal(createHash("sha256").update(readFileSync(file)).digest("hex"),meta.sha256);
  return {file,meta};
});
const narration=original.flatMap((scene,index)=>[0,1].map(pair=>({
  id:`local_${index}_${pair}`,title:scene.title,
  narration:scene.subtitleCues.slice(pair*2,pair*2+2).map(cue=>cue.text).join(""),
})));
const storyboard=await continuousNarration({topic:"多吃糖的坏处",scenes:narration});
mkdirSync(resolve("../../outputs"),{recursive:true});
const cropDir=join(artDir,"panels");
mkdirSync(cropDir,{recursive:true});
const scenes=[];
for(const [index,spoken] of storyboard.scenes.entries()) {
  const sourceIndex=Math.floor(index/2), pair=index%2;
  const {width,height}=await sharp(sources[sourceIndex].file).metadata();
  const w=Math.floor(width/2), h=Math.floor(height/2);
  const panels=[];
  for(let column=0;column<2;column++) {
    const replacement=replacementFiles[`${sourceIndex}_${pair}_${column}`];
    const source=replacement?join(artDir,replacement):sources[sourceIndex].file;
    const cropped=replacement?readFileSync(source):await sharp(source).extract({left:column*w,top:pair*h,width:w,height:h}).png().toBuffer();
    const panel=await sharp(cropped)
      .flatten({background:"white"}).trim({background:"white",threshold:12})
      .resize(386,288,{fit:"inside"}).png().toBuffer();
    writeFileSync(join(cropDir,`scene-${sourceIndex}-cue-${pair*2+column}.png`),panel);
    const meta=await sharp(panel).metadata();
    panels.push({input:panel,left:column*420+17+Math.round((386-meta.width)/2),top:Math.round((320-meta.height)/2)});
  }
  const plate=await sharp({create:{width:840,height:320,channels:3,background:"white"}}).composite(panels).png().toBuffer();
  const raster=await buildRasterRevealFromBuffer(plate,jobId,{id:`local_${index}`},{forceTrace:true});
  assert(raster.rasterReveal.strokes.length>10,"Local artwork did not produce a usable drawing");
  const duration=spoken.timingPlan.durationFrames;
  const paths=timedRevealPaths(raster.rasterReveal.strokes,spoken.subtitleCues,
    [{untilX:.5,phrase:spoken.subtitleCues[0].text},{untilX:1,phrase:spoken.subtitleCues[1].text}],duration);
  const scale=Math.min(850/raster.rasterReveal.imageWidth,310/raster.rasterReveal.imageHeight);
  const bounds={width:raster.rasterReveal.imageWidth*scale,height:raster.rasterReveal.imageHeight*scale};
  Object.assign(bounds,{x:(960-bounds.width)/2,y:95+(310-bounds.height)/2});
  const scene={...spoken,duration,boardMode:"whiteboard",videoStyle:"whiteboard",visualStyle:"teacher_whiteboard",
    handUsage:"trace",transitionFrames:0,accent:"#39856E",keywords:[],summaryPoints:[],renderElements:[],
    drawOps:[],texts:[],strokes:[],glyphPaths:[],referenceImageAsset:raster.referenceImageAsset,assetContract:raster.assetContract};
  scene.rasterReveal={...raster.rasterReveal,...bounds,renderMode:"trace",strokes:paths.map((path,i)=>{
    const cueIndex=path.inkStart>=spoken.subtitleCues[1].startFrame?1:0;
    const cue=spoken.subtitleCues[cueIndex];
    const time=frame=>cue.startFrame+(frame-cue.startFrame)*.85;
    const points=path.points.map(p=>({x:bounds.x+p.x*bounds.width,y:bounds.y+p.y*bounds.height}));
    const id=`s${index}_raster_${i}`;
    for(const [phase,from,to] of [["ink",path.inkStart,path.inkEnd],["color",path.colorStart,path.colorEnd]]) {
      scene.drawOps.push({id:phase==="ink"?id:`${id}_color`,kind:"path",phase,startFrame:time(from),endFrame:time(to),points,beatId:`cue_${cueIndex}`});
    }
    const length=points.slice(1).reduce((sum,p,k)=>sum+Math.hypot(p.x-points[k].x,p.y-points[k].y),0);
    return {opId:id,colorOpId:`${id}_color`,d:points.map((p,k)=>`${k?"L":"M"} ${p.x} ${p.y}`).join(" "),dashLength:length,
      revealWidth:Math.max(8,path.revealWidth*Math.max(bounds.width,bounds.height))};
  })};
  spoken.subtitleCues.forEach((cue,i)=>{
    const id=`s${index}_label_${i}`;
    scene.drawOps.push({id,kind:"text",startFrame:cue.startFrame+(cue.endFrame-cue.startFrame)*.85,endFrame:cue.endFrame,points:[],beatId:`cue_${i}`});
    scene.texts.push({opId:id,text:labels[sourceIndex][pair*2+i],x:130+i*430,y:414,fontSize:22,maxWidth:360,color:"#39856E"});
  });
  scenes.push(scene);
  console.log(`Local painting ${index+1}/12: ${paths.length} drawn paths`);
}
const outlined=upgradeScenesWithGlyphOutlines(scenes).scenes;
for(const scene of outlined) {
  assert.equal(scene.subtitleCues.map(c=>c.text).join(""),scene.narration);
  assert(scene.texts.every(text=>text.text!==scene.narration));
  for(let frame=0;frame<scene.duration;frame++) assert(scene.drawOps.some(op=>op.startFrame<=frame&&op.endFrame>frame),`No drawing during speech: ${scene.title} frame ${frame}`);
  for(const [i,cue] of scene.subtitleCues.entries()) {
    assert(scene.drawOps.filter(op=>op.beatId===`cue_${i}`).every(op=>op.startFrame>=cue.startFrame-.02&&op.endFrame<=cue.endFrame+.2));
  }
}
const templateFile=readFileSync("../../services/api/src/planner/fallback/_tsx_template_string.py","utf8");
const template=templateFile.slice(templateFile.indexOf("import React"),templateFile.lastIndexOf("'''"))
  .replace("__SCENES_JSON__",JSON.stringify(outlined)).replaceAll("__VIDEO_WIDTH__","960").replaceAll("__VIDEO_HEIGHT__","540")
  .replaceAll("__BACKGROUND_MUSIC_URL__","null").replaceAll("__BACKGROUND_MUSIC_VOLUME__","0.12").replaceAll("__SUBTITLES_ENABLED__","true");
const generated={tsx:template,width:960,height:540,fps:24,durationInFrames:scenes.reduce((sum,s)=>sum+s.duration,0)};
const {entryPath}=writeGeneratedProject(jobId,generated,storyboard,{subtitlesEnabled:true});
const output=resolve(`../../outputs/${jobId}.mp4`);
await bundleAndRender(jobId,entryPath,output);
writeFileSync(resolve(`../../outputs/${jobId}-provenance.json`),JSON.stringify({
  output,durationSeconds:generated.durationInFrames/24,provider:"local",artwork:sources,replacements,
  shots:outlined.map(s=>({title:s.title,narration:s.narration,subtitleCues:s.subtitleCues,assetContract:s.assetContract})),
},null,2));
console.log(JSON.stringify({output,durationSeconds:generated.durationInFrames/24}));
jobs[jobId]={status:"done",phase:"done",progress:100,outputPath:output,
  topic:"多吃糖的坏处（本地彩色插画·正常语速有声版）",createdAt:new Date().toISOString(),
  actualDurationSeconds:generated.durationInFrames/24};
saveJobsSync();
assert.equal(JSON.parse(readFileSync(resolve("../../outputs/jobs.json"),"utf8"))[jobId].outputPath,output);
