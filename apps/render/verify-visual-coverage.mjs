// Inspect actual exported pixels at every spoken cue, not just three whole-video frames.
import assert from "node:assert/strict";
import {readFileSync,writeFileSync,mkdirSync} from "node:fs";
import {join} from "node:path";
import {execFile} from "node:child_process";
import {promisify} from "node:util";
import sharp from "sharp";
import {FFMPEG_BINARY,GENERATED_DIR,OUTPUT_DIR} from "./config.mjs";

const run=promisify(execFile);
const id=process.argv[2];
assert(id,"Pass a completed job ID");
const job=JSON.parse(readFileSync(join(OUTPUT_DIR,"jobs.json"),"utf8"))[id];
assert.equal(job.status,"done");
const tsx=readFileSync(join(GENERATED_DIR,id,"GeneratedVideo.tsx"),"utf8");
const scenes=JSON.parse(tsx.match(/const scenes[^=]*= ([\s\S]*?) as SceneSpec\[\]/)[1]);
const input=JSON.parse(readFileSync(join(GENERATED_DIR,id,"render-input.json"),"utf8"));
const dir=join(OUTPUT_DIR,"qa",id,"cue-coverage");
mkdirSync(dir,{recursive:true});
const checks=[],tiles=[];
let start=0;
for(const [index,scene] of scenes.entries()) {
  assert(scene.rasterReveal,`No image for scene ${index}`);
  assert.equal(scene.subtitleCues.map(c=>c.text).join("").replace(/\s/g,""),
    input.storyboard.scenes[index].narration.replace(/\s/g,""),`Spoken captions changed in scene ${index}`);
  const reveal=scene.rasterReveal;
  for(const [cueIndex,cue] of scene.subtitleCues.entries()) {
    const local=(cue.startFrame+cue.endFrame)/2;
    assert(scene.drawOps.some(op=>op.startFrame<=local+1&&op.endFrame>=local-1),
      `Narration without drawing: scene ${index}, ${cue.text}`);
    const file=join(dir,`${index}-${cueIndex}.png`);
    await run(FFMPEG_BINARY,["-hide_banner","-loglevel","error","-y","-ss",String((start+local)/24),"-i",job.outputPath,"-frames:v","1",file],{windowsHide:true});
    const {data,info}=await sharp(file).extract({left:Math.round(reveal.x),top:Math.round(reveal.y),width:Math.floor(reveal.width),height:Math.floor(reveal.height)}).removeAlpha().raw().toBuffer({resolveWithObject:true});
    let colored=0;
    for(let p=0;p<data.length;p+=info.channels) {
      const rgb=[data[p],data[p+1],data[p+2]];
      if(Math.max(...rgb)-Math.min(...rgb)>30&&Math.min(...rgb)<200) colored++;
    }
    const fraction=colored/(info.width*info.height);
    checks.push({scene:index,cue:cue.text,timeSeconds:(start+local)/24,localSeconds:local/24,coloredFraction:fraction});
    // Allow the initial pen stroke, but never accept a blank illustration area thereafter.
    if(local>=24*1.5) assert(fraction>.012,`Missing picture: scene ${index}, ${cue.text}, coverage ${fraction}`);
    tiles.push(await sharp(file).resize(480,270).png().toBuffer());
  }
  start+=scene.duration;
}
for(let page=0;page*16<tiles.length;page++) {
  const group=tiles.slice(page*16,(page+1)*16);
  await sharp({create:{width:1920,height:Math.ceil(group.length/4)*270,channels:3,background:"white"}})
    .composite(group.map((input,i)=>({input,left:i%4*480,top:Math.floor(i/4)*270})))
    .png().toFile(join(dir,`contact-${page}.png`));
}
writeFileSync(join(dir,"checks.json"),JSON.stringify(checks,null,2));
console.log(JSON.stringify({scenes:scenes.length,cues:checks.length,minCoverageAfterOpening:Math.min(...checks.filter(c=>c.localSeconds>=1.5).map(c=>c.coloredFraction)),dir}));
